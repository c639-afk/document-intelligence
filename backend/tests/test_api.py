import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def make_png():
    image = Image.new("RGB", (10, 10), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_health():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_list_documents():
    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    assert "documents" in response.json()


def test_get_missing_document():
    response = client.get("/api/v1/documents/does-not-exist.jpg")

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "DOCUMENT_NOT_FOUND"


@pytest.mark.anyio
async def test_process_unsupported_file():
    response = client.post(
        "/api/v1/documents/process",
        files={
            "file": (
                "test.txt",
                b"this is not a supported document",
                "text/plain",
            )
        },
        data={"document_type": "invoice"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.anyio
async def test_process_empty_file():
    response = client.post(
        "/api/v1/documents/process",
        files={
            "file": (
                "empty.pdf",
                b"",
                "application/pdf",
            )
        },
        data={"document_type": "invoice"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "EMPTY_FILE"


def test_process_valid_invoice_with_mocked_extraction(
    monkeypatch,
):
    mocked_extraction = {
        "document_type": "invoice",
        "fields": [
            {
                "name": "invoice_number",
                "value": "TEST-001",
                "evidence": "Invoice no: TEST-001",
                "page_number": 1,
            },
            {
                "name": "subtotal",
                "value": "100.00",
                "evidence": "$100.00",
                "page_number": 1,
            },
            {
                "name": "tax_amount",
                "value": "10.00",
                "evidence": "$10.00",
                "page_number": 1,
            },
            {
                "name": "total_amount",
                "value": "110.00",
                "evidence": "$110.00",
                "page_number": 1,
            },
        ],
        "line_items": [
            {
                "description": "Test Item",
                "quantity": "2",
                "unit_price": "50.00",
                "amount": "100.00",
                "tax_rate": "10%",
                "additional_fields": [],
                "evidence": "2 x $50.00 = $100.00",
                "page_number": 1,
            }
        ],
        "tables": [],
    }

    async def mock_extract_text(file):
        return {
            "ocr_used": True,
            "mime_type": "image/png",
            "content": make_png(),
            "pages": [
                {
                    "page_number": 1,
                    "text": "Invoice no: TEST-001",
                }
            ],
        }

    async def mock_extract_document(
        document_type,
        pages,
        document_content,
        mime_type,
    ):
        return mocked_extraction

    monkeypatch.setattr(
        "app.api.routes.documents.extract_text",
        mock_extract_text,
    )

    monkeypatch.setattr(
        "app.api.routes.documents.extract_document",
        mock_extract_document,
    )

    response = client.post(
        "/api/v1/documents/process",
        files={
            "file": (
                "api-test-invoice.png",
                make_png(),
                "image/png",
            )
        },
        data={"document_type": "invoice"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["document_name"] == "api-test-invoice.png"
    assert data["document_type"] == "invoice"
    assert data["processing_status"] == "PASS"

    assert data["file_validation"]["status"] == "PASS"

    assert data["extracted_data"]["fields"][0]["value"] == "TEST-001"

    assert data["validation"]["overall_status"] == "PASS"

    assert "processing_metadata" in data
    assert data["processing_metadata"]["ocr_used"] is True

    saved_response = client.get(
        "/api/v1/documents/api-test-invoice.png"
    )

    assert saved_response.status_code == 200

    saved_data = saved_response.json()

    assert saved_data["document_name"] == "api-test-invoice.png"
    assert saved_data["processing_status"] == "PASS"

def test_reprocessing_same_document_updates_existing_record(
    monkeypatch,
):
    async def mock_extract_text(file):
        return {
            "ocr_used": True,
            "mime_type": "image/png",
            "content": make_png(),
            "pages": [
                {
                    "page_number": 1,
                    "text": "Invoice",
                }
            ],
        }

    async def mock_extract_document(
        document_type,
        pages,
        document_content,
        mime_type,
    ):
        return {
            "document_type": "invoice",
            "fields": [
                {
                    "name": "invoice_number",
                    "value": "UPDATED-001",
                    "evidence": "Invoice no: UPDATED-001",
                    "page_number": 1,
                },
                {
                    "name": "subtotal",
                    "value": "100.00",
                    "evidence": "$100.00",
                    "page_number": 1,
                },
                {
                    "name": "tax_amount",
                    "value": "10.00",
                    "evidence": "$10.00",
                    "page_number": 1,
                },
                {
                    "name": "total_amount",
                    "value": "110.00",
                    "evidence": "$110.00",
                    "page_number": 1,
                },
            ],
            "line_items": [
                {
                    "description": "Updated Item",
                    "quantity": "2",
                    "unit_price": "50.00",
                    "amount": "100.00",
                    "tax_rate": "10%",
                    "additional_fields": [],
                    "evidence": "2 x $50.00 = $100.00",
                    "page_number": 1,
                }
            ],
            "tables": [],
        }

    monkeypatch.setattr(
        "app.api.routes.documents.extract_text",
        mock_extract_text,
    )
    monkeypatch.setattr(
        "app.api.routes.documents.extract_document",
        mock_extract_document,
    )

    filename = "reprocessing-test.png"

    first_response = client.post(
        "/api/v1/documents/process",
        files={
            "file": (
                filename,
                make_png(),
                "image/png",
            )
        },
        data={"document_type": "invoice"},
    )

    assert first_response.status_code == 200

    second_response = client.post(
        "/api/v1/documents/process",
        files={
            "file": (
                filename,
                make_png(),
                "image/png",
            )
        },
        data={"document_type": "invoice"},
    )

    assert second_response.status_code == 200

    data = second_response.json()

    assert data["document_name"] == filename
    assert (
        data["extracted_data"]["fields"][0]["value"]
        == "UPDATED-001"
    )

    saved_response = client.get(
        f"/api/v1/documents/{filename}"
    )

    assert saved_response.status_code == 200

    saved_data = saved_response.json()

    assert (
        saved_data["extracted_data"]["fields"][0]["value"]
        == "UPDATED-001"
    )

def test_process_valid_balance_sheet_with_mocked_extraction(
    
    monkeypatch,
):
    async def mock_extract_text(file):
        return {
            "ocr_used": True,
            "mime_type": "image/png",
            "content": make_png(),
            "pages": [{"page_number": 1, "text": "Balance Sheet"}],
        }

    async def mock_extract_document(
        document_type,
        pages,
        document_content,
        mime_type,
    ):
        return {
            "document_type": "balance_sheet",
            "fields": [],
            "line_items": [],
            "tables": [
                {
                    "name": "Balance Sheet",
                    "sections": [
                        {
                            "name": "ASSETS",
                            "line_items": [
                                {
                                    "type": "total",
                                    "label": "Total",
                                    "values": [
                                        {
                                            "period": "2024",
                                            "value": "1000",
                                            "evidence": "1000",
                                            "page_number": 1,
                                        }
                                    ],
                                }
                            ],
                        },
                        {
                            "name": "CAPITAL AND LIABILITIES",
                            "line_items": [
                                {
                                    "type": "total",
                                    "label": "Total",
                                    "values": [
                                        {
                                            "period": "2024",
                                            "value": "1000",
                                            "evidence": "1000",
                                            "page_number": 1,
                                        }
                                    ],
                                }
                            ],
                        },
                    ],
                }
            ],
        }

    monkeypatch.setattr(
        "app.api.routes.documents.extract_text",
        mock_extract_text,
    )

    monkeypatch.setattr(
        "app.api.routes.documents.extract_document",
        mock_extract_document,
    )

    response = client.post(
        "/api/v1/documents/process",
        files={
            "file": (
                "api-test-balance-sheet.png",
                make_png(),
                "image/png",
            )
        },
        data={"document_type": "balance_sheet"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["document_type"] == "balance_sheet"
    assert data["processing_status"] == "PASS"
    assert data["validation"]["overall_status"] == "PASS"
def test_process_valid_profit_and_loss_with_mocked_extraction(
    monkeypatch,
):
    async def mock_extract_text(file):
        return {
            "ocr_used": True,
            "mime_type": "image/png",
            "content": make_png(),
            "pages": [{"page_number": 1, "text": "Profit and Loss"}],
        }

    async def mock_extract_document(
        document_type,
        pages,
        document_content,
        mime_type,
    ):
        return {
            "document_type": "profit_and_loss",
            "fields": [],
            "line_items": [],
            "tables": [
                {
                    "name": "Profit and Loss",
                    "columns": ["Particulars", "2024"],
                    "rows": [
                        {
                            "type": "line_item",
                            "label": "Interest Earned",
                            "schedule": None,
                            "values": [
                                {
                                    "period": "2024",
                                    "value": "100",
                                    "evidence": "100",
                                    "page_number": 1,
                                }
                            ],
                            "evidence": "Interest Earned 100",
                            "page_number": 1,
                        },
                        {
                            "type": "line_item",
                            "label": "Other Income",
                            "schedule": None,
                            "values": [
                                {
                                    "period": "2024",
                                    "value": "50",
                                    "evidence": "50",
                                    "page_number": 1,
                                }
                            ],
                            "evidence": "Other Income 50",
                            "page_number": 1,
                        },
                        {
                            "type": "total",
                            "label": "Total Income",
                            "schedule": None,
                            "values": [
                                {
                                    "period": "2024",
                                    "value": "150",
                                    "evidence": "150",
                                    "page_number": 1,
                                }
                            ],
                            "evidence": "Total Income 150",
                            "page_number": 1,
                        },
                    ],
                }
            ],
        }

    monkeypatch.setattr(
        "app.api.routes.documents.extract_text",
        mock_extract_text,
    )
    monkeypatch.setattr(
        "app.api.routes.documents.extract_document",
        mock_extract_document,
    )

    response = client.post(
        "/api/v1/documents/process",
        files={
            "file": (
                "api-test-profit-loss.png",
                make_png(),
                "image/png",
            )
        },
        data={"document_type": "profit_and_loss"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["document_type"] == "profit_and_loss"
    assert data["processing_status"] == "PASS"
    assert data["validation"]["overall_status"] == "PASS"


def test_process_valid_cash_flow_with_mocked_extraction(
    monkeypatch,
):
    async def mock_extract_text(file):
        return {
            "ocr_used": True,
            "mime_type": "image/png",
            "content": make_png(),
            "pages": [{"page_number": 1, "text": "Cash Flow"}],
        }

    async def mock_extract_document(
        document_type,
        pages,
        document_content,
        mime_type,
    ):
        return {
            "document_type": "cash_flow_statement",
            "fields": [],
            "line_items": [],
            "tables": [
                {
                    "name": "Cash Flow",
                    "columns": ["Particulars", "2024"],
                    "rows": [
                        {
                            "type": "line_item",
                            "label": "Net Cash Flow from Operating Activities",
                            "schedule": None,
                            "values": [
                                {
                                    "period": "2024",
                                    "value": "100",
                                    "evidence": "100",
                                    "page_number": 1,
                                }
                            ],
                            "evidence": "Operating 100",
                            "page_number": 1,
                        },
                        {
                            "type": "line_item",
                            "label": "Net Cash Used in Investing Activities",
                            "schedule": None,
                            "values": [
                                {
                                    "period": "2024",
                                    "value": "-50",
                                    "evidence": "-50",
                                    "page_number": 1,
                                }
                            ],
                            "evidence": "Investing -50",
                            "page_number": 1,
                        },
                        {
                            "type": "line_item",
                            "label": "Net Cash Generated from Financing Activities",
                            "schedule": None,
                            "values": [
                                {
                                    "period": "2024",
                                    "value": "25",
                                    "evidence": "25",
                                    "page_number": 1,
                                }
                            ],
                            "evidence": "Financing 25",
                            "page_number": 1,
                        },
                        {
                            "type": "total",
                            "label": "Net Increase in Cash and Cash Equivalents",
                            "schedule": None,
                            "values": [
                                {
                                    "period": "2024",
                                    "value": "75",
                                    "evidence": "75",
                                    "page_number": 1,
                                }
                            ],
                            "evidence": "Net Increase 75",
                            "page_number": 1,
                        },
                    ],
                }
            ],
        }

    monkeypatch.setattr(
        "app.api.routes.documents.extract_text",
        mock_extract_text,
    )

    monkeypatch.setattr(
        "app.api.routes.documents.extract_document",
        mock_extract_document,
    )

    response = client.post(
        "/api/v1/documents/process",
        files={
            "file": (
                "api-test-cash-flow.png",
                make_png(),
                "image/png",
            )
        },
        data={"document_type": "cash_flow_statement"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["document_type"] == "cash_flow_statement"
    assert data["processing_status"] == "PASS"
    assert data["validation"]["overall_status"] == "PASS"