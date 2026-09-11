import io

import pytest
from fastapi import UploadFile
from PIL import Image

from app.services.document_validation_service import (
    DocumentValidationError,
    validate_document,
)


def make_png():
    image = Image.new("RGB", (10, 10), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_upload_file(filename, content, content_type):
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers={"content-type": content_type},
    )


@pytest.mark.anyio
async def test_valid_png():
    file = make_upload_file("test.png", make_png(), "image/png")

    result = await validate_document(file)

    assert result["is_supported"] is True
    assert result["is_readable"] is True
    assert result["status"] == "PASS"
    assert result["page_count"] == 1


@pytest.mark.anyio
async def test_unsupported_file_type():
    file = make_upload_file(
        "test.txt",
        b"this is not a supported document",
        "text/plain",
    )

    with pytest.raises(DocumentValidationError) as exc:
        await validate_document(file)

    assert exc.value.code == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.anyio
async def test_empty_file():
    file = make_upload_file(
        "empty.pdf",
        b"",
        "application/pdf",
    )

    with pytest.raises(DocumentValidationError) as exc:
        await validate_document(file)

    assert exc.value.code == "EMPTY_FILE"


@pytest.mark.anyio
async def test_corrupted_pdf():
    file = make_upload_file(
        "corrupted.pdf",
        b"this is not a valid pdf",
        "application/pdf",
    )

    with pytest.raises(DocumentValidationError) as exc:
        await validate_document(file)

    assert exc.value.code == "CORRUPTED_FILE"


@pytest.mark.anyio
async def test_corrupted_png():
    file = make_upload_file(
        "corrupted.png",
        b"this is not a valid png",
        "image/png",
    )

    with pytest.raises(DocumentValidationError) as exc:
        await validate_document(file)

    assert exc.value.code == "CORRUPTED_FILE"


@pytest.mark.anyio
async def test_pdf_page_limit():
    from pypdf import PdfWriter

    buffer = io.BytesIO()
    writer = PdfWriter()

    for _ in range(4):
        writer.add_blank_page(width=100, height=100)

    writer.write(buffer)

    file = make_upload_file(
        "four_pages.pdf",
        buffer.getvalue(),
        "application/pdf",
    )

    with pytest.raises(DocumentValidationError) as exc:
        await validate_document(file)

    assert exc.value.code == "PAGE_LIMIT_EXCEEDED"