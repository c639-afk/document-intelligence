from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)

    document_name = Column(String, index=True, nullable=False)
    document_type = Column(String, nullable=False)

    processing_status = Column(String, nullable=False)

    file_type = Column(String, nullable=True)
    is_supported = Column(String, nullable=True)
    is_readable = Column(String, nullable=True)
    page_count = Column(Integer, nullable=True)

    result_json = Column(Text, nullable=False)

    processed_at = Column(
    DateTime,
    default=lambda: datetime.now(timezone.utc),
    nullable=False,
)