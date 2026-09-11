from io import BytesIO
import logging

from PIL import Image
import pytesseract
from pypdf import PdfReader
from pdf2image import convert_from_bytes

logger = logging.getLogger(__name__)


def extract_text_from_image(content: bytes) -> str:
    logger.info("Image OCR started")
    image = Image.open(BytesIO(content))
    text = pytesseract.image_to_string(image)
    logger.info("Image OCR completed")
    return text

def extract_text_from_pdf_native(content: bytes) -> list[dict]:
    logger.info("Native PDF text extraction started")
    reader = PdfReader(BytesIO(content))

    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""

        pages.append({
            "page_number": page_number,
            "text": text,
        })

    logger.info(
        "Native PDF text extraction completed: pages=%s",
        len(pages),
    )

    return pages


def extract_text_from_pdf_ocr(content: bytes) -> list[dict]:
    logger.info("Scanned PDF OCR started")

    images = convert_from_bytes(
        content,
        dpi=200,
    )

    pages = []

    for page_number, image in enumerate(images, start=1):
        text = pytesseract.image_to_string(image)

        pages.append({
            "page_number": page_number,
            "text": text,
        })

    

    logger.info(
        "Scanned PDF OCR completed: pages=%s",
        len(pages),
    )

    return pages


async def extract_text(file) -> dict:
    content = await file.read()
    filename = (file.filename or "").lower()

    logger.info(
        "Text extraction requested: filename=%s",
        file.filename,
    )

    # JPG / PNG
    if filename.endswith((".jpg", ".jpeg", ".png")):
        text = extract_text_from_image(content)

        return {
            "ocr_used": True,
            "mime_type": file.content_type,
            "content": content,
            "pages": [
                {
                    "page_number": 1,
                    "text": text,
                }
            ],
        }

    # PDF
    if filename.endswith(".pdf"):
        native_pages = extract_text_from_pdf_native(content)

        native_text = "\n".join(
            page["text"].strip()
            for page in native_pages
        )

        # Native PDF has meaningful text.
        if len(native_text.strip()) >= 50:

            logger.info(
                "Using native PDF text extraction: filename=%s",
                file.filename,
            )
            return {
                "ocr_used": False,
                "mime_type": "application/pdf",
                "content": content,
                "pages": native_pages,
            }

        # Scanned/image-based PDF.
        ocr_pages = extract_text_from_pdf_ocr(content)

        logger.info(
            "Using OCR for scanned PDF: filename=%s",
            file.filename,
        )

        return {
            "ocr_used": True,
            "mime_type": "application/pdf",
            "content": content,
            "pages": ocr_pages,
        }

    raise ValueError("Unsupported document format")