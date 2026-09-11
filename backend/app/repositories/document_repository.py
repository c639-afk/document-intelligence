import json

from sqlalchemy.orm import Session

from app.models.document import Document

from datetime import datetime, timezone


def save_document(db: Session, result: dict) -> Document:
    document_name = result["document_name"]

    # Keep the latest result for the same document name.
    existing = (
        db.query(Document)
        .filter(Document.document_name == document_name)
        .order_by(Document.processed_at.desc())
        .first()
    )

    file_validation = result.get("file_validation", {})

    if existing:
        existing.document_type = result["document_type"]
        existing.processing_status = result["processing_status"]
        existing.file_type = file_validation.get("file_type")
        existing.is_supported = str(
            file_validation.get("is_supported")
        )
        existing.is_readable = str(
            file_validation.get("is_readable")
        )
        existing.page_count = file_validation.get("page_count")
        existing.result_json = json.dumps(result)
        existing.processed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(existing)

        return existing

    document = Document(
        document_name=document_name,
        document_type=result["document_type"],
        processing_status=result["processing_status"],
        file_type=file_validation.get("file_type"),
        is_supported=str(
            file_validation.get("is_supported")
        ),
        is_readable=str(
            file_validation.get("is_readable")
        ),
        page_count=file_validation.get("page_count"),
        result_json=json.dumps(result),
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document


def get_document_by_name(
    db: Session,
    document_name: str,
) -> Document | None:
    return (
        db.query(Document)
        .filter(Document.document_name == document_name)
        .order_by(Document.processed_at.desc())
        .first()
    )


def get_all_documents(db: Session) -> list[Document]:
    return (
        db.query(Document)
        .order_by(Document.processed_at.desc())
        .all()
    )