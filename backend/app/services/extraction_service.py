import asyncio
import json
import logging

from io import BytesIO

from google import genai
from google.genai import types

from app.core.config import settings
from app.schemas.extraction import ExtractionResponse

logger = logging.getLogger(__name__)

def gemini_response_schema():
    """Return a Gemini-compatible JSON schema."""

    schema = ExtractionResponse.model_json_schema()

    def clean(value):
        if isinstance(value, dict):
            return {
                key: clean(item)
                for key, item in value.items()
                if key != "additionalProperties"
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(schema)


client = genai.Client(api_key=settings.gemini_api_key)



DOCUMENT_TYPES = {
    "invoice",
    "balance_sheet",
    "profit_and_loss",
    "cash_flow_statement",
}


def build_extraction_prompt(
    document_type: str,
    ocr_text: str,
) -> str:

    return f"""
You are a financial document extraction system.

The supplied document is the PRIMARY SOURCE OF TRUTH.

You have been given:

1. The original document as a visual input.
2. Supporting OCR/native extracted text.

Use the visual document to understand:

- page layout
- tables
- columns
- rows
- headings
- labels
- numbers
- currencies
- dates
- parentheses/brackets
- relationships between values

Use OCR/native text only as supporting information. If OCR conflicts with
what is visibly present, prefer the original document.

The supplied document type is: {document_type}

IMPORTANT EXTRACTION RULES:

1. Extract ALL meaningful information visibly present in the document.
2. Do not invent, infer, estimate, or calculate missing values.
3. If a value is missing or unreadable, use null.
4. Preserve the actual source values. Do not silently change their meaning.
5. Preserve negative values. Parentheses/brackets must remain negative where
   they represent negative accounting values.
6. Extract all meaningful header fields, dates, parties, currency, units,
   totals, line items, statement rows and comparative-period values.
7. Include evidence and page_number whenever available.
8. Do not summarize the document.

CRITICAL: OUTPUT SCHEMA IS FIXED.

The response schema supplied by the application is mandatory. Follow it
exactly. NEVER invent alternate keys or alternate nesting structures.

For EVERY financial table, use ONLY:

    tables -> rows -> values

A financial statement section MUST be represented as a row with:

    type = "section_header"
    label = section name
    values = []

A financial statement line item MUST be represented as:

    type = "line_item"
    label = the visible row label
    schedule = the schedule/reference if visible, otherwise null
    values = one object per reporting period

A reported total MUST be represented as:

    type = "total"
    label = "Total" (or the exact visible total label)
    values = one object per reporting period

Each table value MUST use:

    period = the exact reporting-period/header label
    value = the source value as text, or null
    evidence = supporting source text, or null
    page_number = source page number, or null

DO NOT use any of these alternate structures:

- sections
- section_name
- line_items inside a table section
- particulars
- as_at_31_mar_17
- as_at_31_mar_16
- year_ended_31_mar_17
- year_ended_31_mar_16

Those concepts belong in the canonical fields described above.

For invoices:

- Put invoice header information in fields.
- Put every invoice line item in line_items.
- Also represent the visible invoice table in tables using the same canonical
  rows/values structure when a table is present.
- For a line item, use description, quantity, unit_price, amount and tax_rate
  where those values are visibly present. Put any other visible line-item
  columns into additional_fields.

For financial statements:

- Put statement-level information such as entity, date, currency and unit in fields.
- Preserve every visible statement row in tables.
- Preserve every visible section heading.
- Preserve every comparative period separately.
- Preserve every reported total exactly as shown.
- Do not calculate a total that is not explicitly reported.

Missing required fields are represented with null; do not infer them.

SUPPORTING OCR / NATIVE TEXT

--------------------------------

{ocr_text}

--------------------------------
"""


def is_quota_error(exc: Exception) -> bool:
    error_text = str(exc).lower()

    return (
        "resource_exhausted" in error_text
        or "quota exceeded" in error_text
        or "429" in error_text
    )


async def generate_with_retry(
    contents,
    model: str,
    max_attempts: int = 3,
):
    for attempt in range(max_attempts):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=gemini_response_schema(),
                ),
            )

            if not response.text:
                raise ValueError("Gemini returned an empty response")

            return response

        except Exception as exc:

            # IMPORTANT:
            # Do not retry quota errors. 
            if is_quota_error(exc):
                logger.error(
                    "Gemini quota exhausted on model=%s",
                    model,
                )
                raise

            error_text = str(exc)

            is_temporary_error = (
                "503" in error_text
                or "UNAVAILABLE" in error_text
            )

            if not is_temporary_error:
                raise

            if attempt == max_attempts - 1:
                raise

            wait_seconds = 2 ** attempt

            logger.warning(
                "Gemini temporary error on model=%s. Retrying in %s seconds.",
                model,
                wait_seconds,
            )

            await asyncio.sleep(wait_seconds)

async def extract_document(
    document_type: str,
    pages: list[dict],
    document_content: bytes,
    mime_type: str,
) -> dict:

    if document_type not in DOCUMENT_TYPES:
        raise ValueError(
            f"Unsupported document type: {document_type}"
        )

    ocr_text = "\n\n".join(
        f"PAGE {page['page_number']}:\n{page['text']}"
        for page in pages
    )

    prompt = build_extraction_prompt(
        document_type=document_type,
        ocr_text=ocr_text,
    )

    # ---------------------------------------------------------
    # PRIMARY: GEMINI
    # ---------------------------------------------------------
    logger.info(
        "Uploading document to Gemini: mime_type=%s",
        mime_type,
    )

    uploaded_file = client.files.upload(
        file=BytesIO(document_content),
        config={"mime_type": mime_type},
    )

    logger.info("Document uploaded to Gemini successfully")

    contents = [uploaded_file, prompt]

    models_to_try = [
        settings.gemini_model,
        settings.gemini_fallback_model,
    ]

    last_error = None

    for model in models_to_try:

        if not model:
            continue

        try:

            logger.info(
                "Trying Gemini multimodal model: %s",
                model,
            )

            response = await generate_with_retry(
                contents=contents,
                model=model,
            )

            parsed = ExtractionResponse.model_validate_json(
                response.text
            )

            logger.info(
                "Gemini extraction succeeded: model=%s, document_type=%s",
                model,
                document_type,
            )

            return parsed.model_dump(
                exclude_none=False
            )

        except Exception as exc:

            last_error = exc

            logger.warning(
                "Gemini model failed: model=%s, error_type=%s, error=%s",
                model,
                type(exc).__name__,
                exc,
            )

            # If Gemini quota is exhausted, immediately
            # stop trying Gemini models.
            if is_quota_error(exc):
                break

    if last_error is not None:
        raise last_error

    raise RuntimeError("Gemini extraction failed.")

    