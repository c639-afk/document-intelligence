from pathlib import Path
from io import BytesIO
import logging
from fastapi import UploadFile
from pypdf import PdfReader
from PIL import Image

SUPPORTED_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}

SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

MAX_PAGES = 3

logger = logging.getLogger(__name__)


class DocumentValidationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


async def validate_document(file: UploadFile) -> dict:
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()

    logger.info(
        "Document validation requested: filename=%s, extension=%s",
        filename,
        extension,
    )

    # Check extension
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentValidationError(
            "UNSUPPORTED_FILE_TYPE",
            "Only PDF / JPG / PNG documents are supported.",
        )

    # Read file
    content = await file.read()

    # Empty file
    if not content:
        raise DocumentValidationError(
            "EMPTY_FILE",
            "The uploaded file is empty.",
        )

    # Validate PDF
    if extension == ".pdf":
        try:
            reader = PdfReader(BytesIO(content))
            page_count = len(reader.pages)

        except Exception:
            raise DocumentValidationError(
                "CORRUPTED_FILE",
                "The uploaded PDF is corrupted or unreadable.",
            )

        if page_count == 0:
            raise DocumentValidationError(
                "CORRUPTED_FILE",
                "The uploaded PDF contains no readable pages.",
            )

        if page_count > MAX_PAGES:
            raise DocumentValidationError(
                "PAGE_LIMIT_EXCEEDED",
                "Documents may contain a maximum of 3 pages.",
            )

    else:
        try:
            image = Image.open(BytesIO(content))
            image.verify()
            page_count = 1

        except Exception:
            raise DocumentValidationError(
                "CORRUPTED_FILE",
                "The uploaded image is corrupted or unreadable.",
            )

    # Reset file position so later services can read it
    await file.seek(0)

    logger.info(
        "Document validation passed: filename=%s, page_count=%s",
        filename,
        page_count,
    )

    return {
        "file_type": file.content_type,
        "is_supported": True,
        "is_readable": True,
        "page_count": page_count,
        "status": "PASS",
    }