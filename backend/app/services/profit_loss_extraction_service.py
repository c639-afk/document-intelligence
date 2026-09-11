import asyncio
import logging
from io import BytesIO
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


class PnLField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: str | None = None
    evidence: str | None = None
    page_number: int | None = None


class PnLValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str
    value: str | None = None
    evidence: str | None = None
    page_number: int | None = None


class PnLRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["section_header", "line_item", "total", "other"]
    label: str | None = None
    schedule: str | None = None
    values: list[PnLValue] = Field(default_factory=list)
    evidence: str | None = None
    page_number: int | None = None


class PnLTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    columns: list[str] = Field(default_factory=list)
    rows: list[PnLRow] = Field(default_factory=list)


class PnLExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["profit_and_loss"]
    fields: list[PnLField] = Field(default_factory=list)
    line_items: list = Field(default_factory=list)
    tables: list[PnLTable] = Field(default_factory=list)


client = genai.Client(api_key=settings.gemini_api_key)


def response_schema():
    schema = PnLExtractionResponse.model_json_schema()

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
You are a Profit and Loss Statement extraction system.

The ORIGINAL DOCUMENT is the primary source of truth.

Read the COMPLETE statement visually from top to bottom.

Do NOT summarize.

Do NOT infer missing values.

If a value is missing or unreadable, return null.

==================================================
HEADER
==================================================

Extract every visible:

- entity/company name
- statement name
- reporting date
- reporting periods
- currency
- unit
- accounting basis
- other statement-level information

==================================================
COMPLETE PROFIT AND LOSS TABLE
==================================================

Extract EVERY visible row.

Do not extract only the rows required for validation.

Preserve:

- section headings
- schedule/reference numbers
- every income row
- every expense row
- subtotals
- totals
- profit rows
- minority interest
- appropriations
- comparative periods
- zero values
- negative values
- parentheses

Every row must be represented.

For every row:

type:
    section_header
    line_item
    total
    other

label:
    exact visible row label

schedule:
    visible schedule/reference, otherwise null

values:
    one value for EACH reporting period

==================================================
IMPORTANT FINANCIAL ROWS
==================================================

Pay particular attention to:

- Revenue
- Interest Earned
- Other Income
- Total Income
- Cost of Sales
- Operating Expenses
- Interest Expended
- Provisions
- Total Expenditure
- Profit Before Tax
- Tax
- Consolidated Net Profit Before Minority Interest
- Minority Interest
- Consolidated Net Profit Attributable to Group
- Appropriations

These are examples of important rows.

Still extract ALL other visible rows.

Do not calculate values that are not explicitly reported.

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

    raise RuntimeError("P&L extraction failed")


async def extract_profit_and_loss(
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

    result = PnLExtractionResponse.model_validate_json(text)

    return result.model_dump(exclude_none=False)