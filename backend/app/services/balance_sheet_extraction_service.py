import asyncio
import logging
from io import BytesIO
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


class BalanceField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: str | None = None
    evidence: str | None = None
    page_number: int | None = None


class BalanceValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str
    value: str | None = None
    evidence: str | None = None
    page_number: int | None = None


class BalanceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["section_header", "line_item", "total", "other"]
    label: str | None = None
    schedule: str | None = None
    values: list[BalanceValue] = Field(default_factory=list)
    evidence: str | None = None
    page_number: int | None = None


class BalanceTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    columns: list[str] = Field(default_factory=list)
    rows: list[BalanceRow] = Field(default_factory=list)


class BalanceExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["balance_sheet"]
    fields: list[BalanceField] = Field(default_factory=list)
    line_items: list = Field(default_factory=list)
    tables: list[BalanceTable] = Field(default_factory=list)


client = genai.Client(api_key=settings.gemini_api_key)


def response_schema():
    schema = BalanceExtractionResponse.model_json_schema()

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


def is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()

    return (
        "resource_exhausted" in text
        or "quota exceeded" in text
        or "429" in text
    )


def build_prompt(ocr_text: str) -> str:
    return f"""
You are a Balance Sheet extraction system.

The ORIGINAL DOCUMENT is the primary source of truth.

Read the ENTIRE Balance Sheet visually from beginning to end.

Do NOT summarize.

Do NOT infer.

Do NOT calculate missing values.

If a value is missing or unreadable, return null.

==================================================
HEADER
==================================================

Extract all visible:

- entity/company name
- statement name
- statement date
- reporting periods
- currency
- unit
- accounting basis
- other statement-level information

==================================================
COMPLETE TABLE
==================================================

THIS IS CRITICAL.

Extract EVERY visible row in the Balance Sheet.

Do not extract only rows needed for validation.

Preserve:

- section headings
- schedules
- every line item
- subtotals
- totals
- zero values
- negative values
- parentheses
- every comparative period

Read from TOP TO BOTTOM.

For every statement row use:

type:
    section_header
    line_item
    total
    other

label:
    exact visible row label

schedule:
    visible schedule/reference number, otherwise null

values:
    one value for EACH reporting period shown

Each value must contain:

period:
    exact reporting-period header

value:
    exact source value

==================================================
IMPORTANT
==================================================

Preserve ALL rows.

Do not omit rows because they appear unimportant.

Pay particular attention to:

- Assets
- Current Assets
- Non-current Assets
- Capital
- Liabilities
- Current Liabilities
- Non-current Liabilities
- Equity
- Total Assets
- Total Liabilities
- Total Equity
- Total Capital and Liabilities

Do not calculate totals that are not reported.

Return ONLY the supplied JSON schema.

Missing = null.

Evidence and page_number whenever possible.

==================================================
OCR SUPPORT
==================================================

{ocr_text}
"""


async def generate(prompt: str, document_content: bytes, mime_type: str):

    uploaded = client.files.upload(
        file=BytesIO(document_content),
        config={"mime_type": mime_type},
    )

    for model in [
        settings.gemini_model,
        settings.gemini_fallback_model,
    ]:

        if not model:
            continue

        for attempt in range(3):

            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[uploaded, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=response_schema(),
                    ),
                )

                if not response.text:
                    raise ValueError("Gemini returned an empty response")

                return response.text

            except Exception as exc:

                if is_quota_error(exc):
                    raise

                if "503" not in str(exc) and "UNAVAILABLE" not in str(exc):
                    raise

                if attempt == 2:
                    raise

                await asyncio.sleep(2 ** attempt)

    raise RuntimeError("Balance Sheet extraction failed")


async def extract_balance_sheet(
    pages: list[dict],
    document_content: bytes,
    mime_type: str,
) -> dict:

    ocr_text = "\n\n".join(
        f"PAGE {page['page_number']}:\n{page['text']}"
        for page in pages
    )

    text = await generate(
        build_prompt(ocr_text),
        document_content,
        mime_type,
    )

    result = BalanceExtractionResponse.model_validate_json(text)

    return result.model_dump(exclude_none=False)