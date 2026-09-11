from io import BytesIO

from PIL import Image
import pytesseract
from pypdf import PdfReader
from pdf2image import convert_from_bytes


def extract_text_from_image(content: bytes) -> str:
    image = Image.open(BytesIO(content))
    return pytesseract.image_to_string(image)


def extract_text_from_pdf_native(content: bytes) -> list[dict]:
    reader = PdfReader(BytesIO(content))

    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""

        pages.append({
            "page_number": page_number,
            "text": text,
        })

    return pages


def extract_text_from_pdf_ocr(content: bytes) -> list[dict]:
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

    return pages


async def extract_text(file) -> dict:
    content = await file.read()
    filename = (file.filename or "").lower()

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
            return {
                "ocr_used": False,
                "mime_type": "application/pdf",
                "content": content,
                "pages": native_pages,
            }

        # Scanned/image-based PDF.
        ocr_pages = extract_text_from_pdf_ocr(content)

        return {
            "ocr_used": True,
            "mime_type": "application/pdf",
            "content": content,
            "pages": ocr_pages,
        }

    raise ValueError("Unsupported document format")