from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DocumentType = Literal[
    "invoice",
    "balance_sheet",
    "profit_and_loss",
    "cash_flow_statement",
]


class ExtractedField(BaseModel):
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
    additional_fields: list[ExtractedField] = Field(default_factory=list)
    evidence: str | None = None
    page_number: int | None = None


class TableValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str
    value: str | None = None
    evidence: str | None = None
    page_number: int | None = None


class TableRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["section_header", "line_item", "total", "other"]
    label: str | None = None
    schedule: str | None = None
    values: list[TableValue] = Field(default_factory=list)
    evidence: str | None = None
    page_number: int | None = None


class ExtractedTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    columns: list[str] = Field(default_factory=list)
    rows: list[TableRow] = Field(default_factory=list)


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    fields: list[ExtractedField] = Field(default_factory=list)
    line_items: list[InvoiceLineItem] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
