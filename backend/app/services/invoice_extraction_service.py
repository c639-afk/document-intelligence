import asyncio
import logging
from io import BytesIO
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings

logger = logging.getLogger(__name__)
# ============================================================
# SCHEMAS
# ============================================================

class InvoiceField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: str | None = None
    evidence: str | None = None
    page_number: int | None = None


class InvoiceLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    amount: str | None = None
    tax_rate: str | None = None

    # Any visible invoice columns that are not one of the
    # standard fields above are stored here.
    additional_fields: list[InvoiceField] = Field(
        default_factory=list
    )

    evidence: str | None = None
    page_number: int | None = None


class InvoiceTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str

    columns: list[str] = Field(
        default_factory=list
    )

    rows: list[list[str | None]] = Field(
        default_factory=list
    )


class InvoiceExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["invoice"]

    fields: list[InvoiceField] = Field(
        default_factory=list
    )

    line_items: list[InvoiceLineItem] = Field(
        default_factory=list
    )

    tables: list[InvoiceTable] = Field(
        default_factory=list
    )


client = genai.Client(
    api_key=settings.gemini_api_key
)


# ============================================================
# GEMINI RESPONSE SCHEMA
# ============================================================

def response_schema():
    schema = InvoiceExtractionResponse.model_json_schema()

    def clean(value):
        if isinstance(value, dict):
            return {
                key: clean(item)
                for key, item in value.items()
                if key != "additionalProperties"
            }

        if isinstance(value, list):
            return [
                clean(item)
                for item in value
            ]

        return value

    return clean(schema)


# ============================================================
# ERROR HANDLING
# ============================================================

def is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()

    return (
        "resource_exhausted" in text
        or "quota exceeded" in text
        or "429" in text
    )


# ============================================================
# PROMPT
# ============================================================

def build_prompt(ocr_text: str) -> str:
    return f"""
You are an invoice document extraction system.

The ORIGINAL DOCUMENT is the primary source of truth.

The document may be:
- a photograph
- a scanned image
- a native PDF
- a digitally generated invoice

Read the ENTIRE ORIGINAL DOCUMENT visually before producing
the JSON.

DO NOT summarize the invoice.

DO NOT infer information.

DO NOT calculate missing values.

If a value is not visibly present in the ORIGINAL DOCUMENT,
do NOT create that field.

If a visible value is present but unreadable, return null.

Every extracted value must be supported by the ORIGINAL DOCUMENT.

==================================================
CRITICAL: OPTIONAL INVOICE FIELDS
==================================================

Only return an invoice-level field when that information is
ACTUALLY VISIBLE in the ORIGINAL DOCUMENT.

Do NOT create null fields merely because they are listed
in the schema.

For example:

If there is no visible due date:
DO NOT return due_date.

If there is no visible payment terms:
DO NOT return payment_terms.

If there is no visible purchase order:
DO NOT return purchase_order.

If there is no visible account number:
DO NOT return account_number.

If there is no visible reference number:
DO NOT return reference_number.

If there is no visible discount:
DO NOT return discount.

If there is no visible round-off:
DO NOT return round_off.

If there is no visible shipping:
DO NOT return shipping.

If there is no visible freight:
DO NOT return freight.

==================================================
CRITICAL: CURRENCY
==================================================

Only extract currency when a currency symbol or currency code
is ACTUALLY VISIBLE in the ORIGINAL DOCUMENT.

Examples:

$
USD
EUR
GBP
INR
₹
€

Do NOT infer currency from:

- country
- seller address
- customer address
- numeric formatting
- invoice language
- value of the invoice

For example, if the document contains:

126,27
12,63
138,90

but no visible currency symbol or currency code,

DO NOT return "$".

==================================================
PRESERVE SOURCE VALUES EXACTLY
==================================================

Preserve visible values exactly, including:

- decimal formatting
- comma/decimal separators
- currencies when visibly present
- negative values
- parentheses
- dates
- quantities
- tax rates
- units
- invoice numbers
- product codes
- descriptions

Do not normalize visible values.

Do not convert commas to periods.

Do not add currency symbols.

Do not calculate values.

==================================================
INVOICE-LEVEL FIELDS
==================================================

Extract every meaningful invoice-level field that is ACTUALLY
VISIBLE in the ORIGINAL DOCUMENT.

Use these canonical names when visible:

invoice_number
invoice_date
due_date
vendor_name
vendor_address
vendor_contact
vendor_tax_id
vendor_iban
customer_name
customer_address
customer_tax_id
currency
payment_terms
purchase_order
account_number
reference_number
subtotal
discount
round_off
tax_amount
total_amount
amount_due
shipping
freight

You may also extract other visible invoice-level information
when present.

Only include fields that are actually visible.

Provide evidence and page_number whenever possible.

==================================================
LINE ITEMS — VERY IMPORTANT
==================================================

The invoice may contain MANY line items.

You MUST inspect the COMPLETE invoice table from TOP TO BOTTOM.

FIRST identify the actual product/service rows in the source.

THEN extract EVERY actual product/service row.

The "line_items" array must contain ONLY REAL PRODUCT OR
SERVICE ROWS.

Each actual product/service row must produce EXACTLY ONE
object in "line_items".

==================================================
DO NOT CREATE FAKE LINE ITEMS
==================================================

DO NOT create line_items entries for:

- blank rows
- empty rows
- whitespace-only rows
- visual spacing rows
- separator rows
- table headers
- column headers
- subtotal rows
- tax rows
- total rows
- footer rows
- rows containing only "Missing" values
- rows containing no actual product/service information
- continuation/formatting rows that do not represent a new item

NEVER create placeholder line items.

NEVER create a line item just because there is a blank
row between two products.

NEVER use "Missing" as a product description.

NEVER create an object where all meaningful fields are
missing.

For example, if the source visually contains:

Product A

[blank row]

Product B

[blank row]

Product C

return exactly:

line_items = [
    Product A,
    Product B,
    Product C
]

DO NOT return:

line_items = [
    Product A,
    Missing,
    Product B,
    Missing,
    Product C,
    Missing
]

If the source contains 7 actual products/services,
the "line_items" array MUST contain exactly 7 objects.

If the source contains 20 actual products/services,
the "line_items" array MUST contain exactly 20 objects.

The number of line_items must correspond to the number of
REAL visible product/service rows, NOT the number of visual
rows including blank spacing.

==================================================
LINE ITEM COMPLETENESS
==================================================

DO NOT stop after the first row.

DO NOT return only the first row.

DO NOT merge multiple actual product/service rows.

DO NOT omit actual product/service rows.

DO NOT invent additional rows.

DO NOT omit rows containing zero values.

After extracting the line items, visually re-check the
COMPLETE ORIGINAL invoice table from TOP TO BOTTOM.

Use the invoice subtotal ONLY as a completeness check.

If the extracted line-item amounts do not appear to cover
the reported subtotal, re-inspect the ORIGINAL DOCUMENT for
missed actual product/service rows.

Do NOT invent values merely to make the subtotal reconcile.

==================================================
FOR EACH LINE ITEM
==================================================

Extract EVERY visible column belonging to each actual
product/service row.

The standard structured fields are:

description
quantity
unit_price
amount
tax_rate

==================================================
IMPORTANT — QUANTITY AND UNIT OF MEASURE
==================================================

The "quantity" field must contain ONLY the numeric quantity.

Examples:

- "48 PCS" → quantity = "48"
- "6 PCS" → quantity = "6"
- "12 PCS" → quantity = "12"

Do NOT put the unit such as PCS, KG, EACH, etc. inside quantity.

The unit of measure MUST be stored separately in additional_fields:

name = "UM"
value = "PCS"

For example:

Visible source:
48 PCS

Extract as:

quantity = "48"

additional_fields:
name = "UM"
value = "PCS"

Preserve the visible unit exactly.

==================================================
ADDITIONAL LINE ITEM FIELDS
==================================================

All other visible columns MUST be placed in
"additional_fields".

Examples of additional fields include:

item number
product code
SKU
unit of measure
UM
discount
tax amount
gross amount
gross worth
rate including tax
HSN/SAC
any other visible column

Each additional field must contain:

name
value
evidence
page_number

IMPORTANT:

If the original row visibly contains:

No. | Description | Qty | UM | Net price | Net worth |
VAT [%] | Gross worth

then the corresponding line item must preserve:

item number
description
quantity
unit of measure
unit price
amount
tax rate
gross worth

Do NOT discard UM.

Do NOT discard Gross worth.

Do NOT calculate Gross worth when it is already visible.

Do NOT replace a visible value with null.

Do NOT truncate long descriptions.

==================================================
ACTUAL TABLE EXTRACTION — VERY IMPORTANT
==================================================

If the ORIGINAL DOCUMENT contains a visible invoice table,
extract that table DIRECTLY under "tables".

The "tables" representation must reproduce the actual
meaningful table content visible in the ORIGINAL DOCUMENT.

Do NOT reconstruct the table from memory.

Do NOT simplify the table.

Do NOT remove visible columns.

Do NOT invent columns.

Do NOT calculate values.

Do NOT change visible values.

The "columns" array must contain the actual visible column
names from the source table.

For example, if the source contains:

No.
Description
Qty
UM
Net price
Net worth
VAT [%]
Gross worth

then the table columns must contain those columns.

Each table row must contain the corresponding value for
EVERY visible column.

If the source has 7 actual product/service rows, the ITEMS
table must contain those 7 corresponding rows.

IMPORTANT:

The "tables" output preserves the source table.

The "line_items" output contains only actual product/service
rows.

Blank spacing rows may exist visually in the source table,
but they MUST NOT become fake line_items.

The ITEMS table and "line_items" must represent the SAME
actual product/service rows.

Do not create a different interpretation of the actual rows.

==================================================
SUMMARY TABLE
==================================================

If the ORIGINAL DOCUMENT contains a visible summary table,
extract that table DIRECTLY under "tables".

Preserve its actual visible:

- column names
- rows
- labels
- values
- totals

Do NOT create additional summary rows.

Do NOT duplicate totals.

Do NOT add currency symbols that are not visible.

Do NOT calculate summary values.

If the summary contains one data row, return one data row.

If the summary contains a total row, return that actual
visible total row.

==================================================
EVIDENCE
==================================================

For every extracted value, provide:

evidence
page_number

whenever possible.

Evidence MUST come from the ORIGINAL DOCUMENT.

Do not fabricate evidence.

==================================================
MISSING VALUES
==================================================

If a value is visibly present but unreadable:

"value": null

If an optional invoice-level field is completely absent:

DO NOT CREATE THE FIELD.

For an actual product/service row, if a specific value is
not visible, that field may be null.

However, DO NOT create an entire line item when there is no
actual product/service row.

Do not infer.

Do not calculate.

Do not guess.

==================================================
FINAL LINE ITEM CHECK
==================================================

Before returning the JSON, perform a final visual check:

1. Count the actual product/service rows in the ORIGINAL DOCUMENT.
2. Count the objects in "line_items".
3. These counts MUST match.
4. Make sure there are NO placeholder or blank line items.
5. Make sure every actual product/service row is represented.
6. Make sure the order matches the ORIGINAL DOCUMENT.

==================================================
OUTPUT
==================================================

Return ONLY valid JSON matching the supplied schema.

Do not add keys outside the schema.

Do not add explanations outside the JSON.

==================================================
SUPPORTING OCR / NATIVE TEXT
==================================================

The following OCR/native text is supporting context only.

The ORIGINAL DOCUMENT remains the primary source of truth.

------------------------------
{ocr_text}
------------------------------
"""


# ============================================================
# REMOVE UNWARRANTED NULL OPTIONAL FIELDS
# ============================================================

def remove_null_invoice_fields(
    data: dict,
) -> dict:
    """
    Remove invoice-level fields that Gemini created with null
    even though there is no evidence that the field exists.

    This prevents the frontend from showing:

        due_date: Missing

    when the source document does not contain a due date.

    A null field with actual evidence is retained because that
    means the field appears to exist in the source but could not
    be read reliably.
    """

    fields = data.get(
        "fields",
        [],
    )

    cleaned_fields = []

    for field in fields:
        if not isinstance(field, dict):
            continue

        value = field.get("value")

        # Keep fields with actual extracted values.
        if value not in (
            None,
            "",
        ):
            cleaned_fields.append(field)
            continue

        # Keep null only if Gemini supplied actual evidence
        # that something was visible but unreadable.
        evidence = field.get("evidence")

        if evidence not in (
            None,
            "",
        ):
            cleaned_fields.append(field)

    data["fields"] = cleaned_fields

    return data


# ============================================================
# GEMINI GENERATION
# ============================================================

async def generate(
    prompt: str,
    document_content: bytes,
    mime_type: str,
):
    uploaded = client.files.upload(
        file=BytesIO(document_content),
        config={
            "mime_type": mime_type,
        },
    )

    models = [
        settings.gemini_model,
        settings.gemini_fallback_model,
    ]

    for model in models:

        if not model:
            continue

        for attempt in range(3):

            try:
                logger.info(
                    "Trying Gemini invoice extraction model: %s",
                    model,
                )

                response = client.models.generate_content(
                    model=model,
                    contents=[
                        uploaded,
                        prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=response_schema(),
                    ),
                )

                if not response.text:
                    raise ValueError(
                        "Gemini returned an empty response"
                    )

                return response.text

            except Exception as exc:

                if is_quota_error(exc):
                    logger.error(
                        "Gemini invoice extraction quota error: %s",
                        exc,
                    )
                    raise

                error_text = str(exc)

                if (
                    "503" not in error_text
                    and "UNAVAILABLE" not in error_text
                ):
                    raise

                if attempt == 2:
                    raise

                wait_seconds = 2 ** attempt

                logger.warning(
                    "Gemini temporary error. "
                    "Retrying in %s seconds.",
                    wait_seconds,
                )

                await asyncio.sleep(
                    wait_seconds
                )

    raise RuntimeError(
        "Invoice extraction failed"
    )


# ============================================================
# MAIN EXTRACTION FUNCTION
# ============================================================

async def extract_invoice(
    pages: list[dict],
    document_content: bytes,
    mime_type: str,
) -> dict:

    logger.info(
        "Invoice extraction started"
    )

    ocr_text = "\n\n".join(
        f"PAGE {page['page_number']}:\n"
        f"{page['text']}"
        for page in pages
    )

    prompt = build_prompt(
        ocr_text
    )

    text = await generate(
        prompt=prompt,
        document_content=document_content,
        mime_type=mime_type,
    )

    result = InvoiceExtractionResponse.model_validate_json(
        text
    )

    data = result.model_dump(
        exclude_none=False
    )

    # Remove optional fields that Gemini may have created as
    # null even though they are completely absent from the
    # original document.
    data = remove_null_invoice_fields(
        data
    )

    # IMPORTANT:
    #
    # DO NOT rebuild the invoice tables here.
    #
    # The tables returned by Gemini are the actual extracted
    # tables from the original document.
    #
    # This preserves all visible columns such as:
    #
    # No.
    # Description
    # Qty
    # UM
    # Net price
    # Net worth
    # VAT [%]
    # Gross worth
    #
    # Nothing is calculated or reconstructed here.

    logger.info(
        "Invoice extraction completed: fields=%s, "
        "line_items=%s, tables=%s",
        len(
            data.get(
                "fields",
                [],
            )
        ),
        len(
            data.get(
                "line_items",
                [],
            )
        ),
        len(
            data.get(
                "tables",
                [],
            )
        ),
    )

    return data