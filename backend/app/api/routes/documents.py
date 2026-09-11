from datetime import datetime, timezone
import time
from enum import Enum
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db

from app.repositories.document_repository import (
    save_document,
    get_document_by_name,
    get_all_documents,
)

from app.services.document_validation_service import (
    DocumentValidationError,
    validate_document,
)

from app.services.ocr_service import extract_text
from app.services.extraction_service import extract_document

from app.services.financial_validation_service import (
    validate_invoice,
    validate_balance_sheet,
    validate_profit_and_loss,
    validate_cash_flow_statement,
)

from app.schemas.document import DocumentProcessResponse


class DocumentType(str, Enum):
    INVOICE = "invoice"
    BALANCE_SHEET = "balance_sheet"
    PROFIT_AND_LOSS = "profit_and_loss"
    CASH_FLOW_STATEMENT = "cash_flow_statement"


router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("")
def list_documents(
    db: Session = Depends(get_db),
):
    documents = get_all_documents(db)

    return {
        "documents": [
            {
                "document_name": document.document_name,
                "document_type": document.document_type,
                "processing_status": document.processing_status,
                "processed_at": document.processed_at.isoformat() + "Z",
                "page_count": document.page_count,
            }
            for document in documents
        ]
    }


@router.get("/{document_name}")
def get_document(
    document_name: str,
    db: Session = Depends(get_db),
):
    document = get_document_by_name(db, document_name)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "DOCUMENT_NOT_FOUND",
                    "message": f"No processed document found: {document_name}",
                }
            },
        )

    return json.loads(document.result_json)


def check_extraction_completeness(
    document_type: DocumentType,
    extracted_data: dict,
) -> tuple[bool, list[str]]:

    fields = extracted_data.get("fields", [])
    line_items = extracted_data.get("line_items", [])
    tables = extracted_data.get("tables", [])

    issues = []

    # There must be some extracted content.
    if not fields and not line_items and not tables:
        issues.append(
            "No meaningful fields, line items, or tables were extracted."
        )
        return False, issues

    # Create lookup of extracted top-level fields.
    field_values = {
        str(field.get("name", "")).strip().lower(): field.get("value")
        for field in fields
    }

    if document_type == DocumentType.INVOICE:

        required_fields = [
            "invoice_number",
            "invoice_date",
            "vendor_name",
            "customer_name",
            "currency",
            "subtotal",
            "tax_amount",
            "total_amount",
        ]

        for field_name in required_fields:
            value = field_values.get(field_name)

            if field_name in field_values and value is None:
                issues.append(
                    f"Invoice field '{field_name}' was present "
                    "but could not be extracted."
                )

        if not line_items and len(field_values) == 0:
            issues.append(
                "No invoice fields or line items were extracted."
            )

    elif document_type == DocumentType.BALANCE_SHEET:

        if not tables:
            issues.append(
                "No balance sheet table or financial statement "
                "rows were extracted."
            )

    elif document_type == DocumentType.PROFIT_AND_LOSS:

        if not tables:
            issues.append(
                "No profit and loss table or financial statement "
                "rows were extracted."
            )

    elif document_type == DocumentType.CASH_FLOW_STATEMENT:

        if not tables:
            issues.append(
                "No cash flow table or financial statement "
                "rows were extracted."
            )

    return len(issues) == 0, issues


@router.post(
    "/process",
    response_model=DocumentProcessResponse,
)
async def process_document(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(DocumentType.INVOICE),
    db: Session = Depends(get_db),
):
    start_time = time.perf_counter()

    # ---------------------------------------------------------
    # DOCUMENT VALIDATION
    # ---------------------------------------------------------

    try:
        file_validation = await validate_document(file)

    except DocumentValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                }
            },
        )

    await file.seek(0)

    # ---------------------------------------------------------
    # OCR + EXTRACTION + FINANCIAL VALIDATION
    # ---------------------------------------------------------

    try:
        extracted_text = await extract_text(file)

        extracted_data = await extract_document(
            document_type=document_type.value,
            pages=extracted_text["pages"],
            document_content=extracted_text["content"],
            mime_type=extracted_text["mime_type"],
        )

        financial_validation = {
            "checks": [],
            "overall_status": "NOT_APPLICABLE",
            "issues": [],
        }

        if document_type == DocumentType.INVOICE:
            financial_validation = validate_invoice(extracted_data)

        elif document_type == DocumentType.BALANCE_SHEET:
            financial_validation = validate_balance_sheet(extracted_data)

        elif document_type == DocumentType.PROFIT_AND_LOSS:
            financial_validation = validate_profit_and_loss(extracted_data)

        elif document_type == DocumentType.CASH_FLOW_STATEMENT:
            financial_validation = validate_cash_flow_statement(
                extracted_data
            )

    except Exception as exc:
        print(f"Processing error: {exc}")

        error_text = str(exc).lower()

        if (
            "resource_exhausted" in error_text
            or "quota exceeded" in error_text
            or "429" in error_text
        ):
            raise HTTPException(
                status_code=429,
                detail={
                    "error": {
                        "code": "GEMINI_QUOTA_EXCEEDED",
                        "message": (
                            "Gemini API daily limit reached. "
                            "Please try again after the quota resets."
                        ),
                    }
                },
            )

        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "PROCESSING_FAILED",
                    "message": "Document processing failed.",
                }
            },
        )

    # ---------------------------------------------------------
    # EXTRACTION COMPLETENESS
    # ---------------------------------------------------------

    extraction_ok, extraction_issues = check_extraction_completeness(
        document_type,
        extracted_data,
    )

    # ---------------------------------------------------------
    # PROCESSING STATUS
    # ---------------------------------------------------------

    validation_status = financial_validation.get(
        "overall_status",
        "NOT_APPLICABLE",
    )

    if not extraction_ok or validation_status == "FAIL":
        processing_status = "FAILED"
    else:
        processing_status = "PASS"

    # ---------------------------------------------------------
    # FINAL RESULT
    # ---------------------------------------------------------

    result = {
        "document_name": file.filename,
        "document_type": document_type.value,
        "processing_status": processing_status,
        "file_validation": file_validation,
        "extracted_data": extracted_data,
        "validation": financial_validation,
        "extraction_issues": extraction_issues,
        "processing_metadata": {
            "ocr_used": extracted_text["ocr_used"],
            "multimodal_extraction": True,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "processing_time_ms": round(
                (time.perf_counter() - start_time) * 1000,
                2,
            ),
        },
    }

    # ---------------------------------------------------------
    # PERSIST RESULT
    # ---------------------------------------------------------

    save_document(db, result)

    return result