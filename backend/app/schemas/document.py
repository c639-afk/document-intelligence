from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentProcessResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    document_name: str | None = None
    document_type: str
    processing_status: str
    file_validation: dict[str, Any]
    extracted_data: dict[str, Any]
    validation: dict[str, Any]
    extraction_issues: list[str]
    processing_metadata: dict[str, Any]