from app.services.financial_validation_service import (
    validate_invoice,
    validate_balance_sheet,
    validate_profit_and_loss,
    validate_cash_flow_statement,
)


def get_statuses(result):
    return [check["status"] for check in result["checks"]]


def test_invoice_validation():
    data = {
        "document_type": "invoice",
        "fields": [
            {"name": "Subtotal", "value": "100"},
            {"name": "Tax Amount", "value": "10"},
            {"name": "Total", "value": "110"},
        ],
        "line_items": [
            {
                "description": "Item A",
                "quantity": "2",
                "unit_price": "25",
                "amount": "50",
            },
            {
                "description": "Item B",
                "quantity": "1",
                "unit_price": "50",
                "amount": "50",
            },
        ],
        "tables": [],
    }

    result = validate_invoice(data)

    assert result["overall_status"] == "PASS"


def test_balance_sheet_validation():
    data = {
        "document_type": "balance_sheet",
        "fields": [],
        "line_items": [],
        "tables": [
            {
                "name": "Balance Sheet",
                "columns": ["Particulars", "2025"],
                "rows": [
                    {
                        "type": "section_header",
                        "label": "ASSETS",
                        "values": [],
                    },
                    {
                        "type": "total",
                        "label": "Total",
                        "values": [
                            {"period": "2025", "value": "1000"}
                        ],
                    },
                    {
                        "type": "section_header",
                        "label": "CAPITAL AND LIABILITIES",
                        "values": [],
                    },
                    {
                        "type": "total",
                        "label": "Total",
                        "values": [
                            {"period": "2025", "value": "1000"}
                        ],
                    },
                ],
            }
        ],
    }

    result = validate_balance_sheet(data)

    assert result["overall_status"] == "PASS"

def test_profit_and_loss_validation():
    data = {
        "document_type": "profit_and_loss",
        "fields": [],
        "line_items": [],
        "tables": [
            {
                "name": "Profit and Loss",
                "columns": ["Particulars", "2025"],
                "rows": [
                    {
                        "type": "line_item",
                        "label": "Interest Earned",
                        "values": [{"period": "2025", "value": "100"}],
                    },
                    {
                        "type": "line_item",
                        "label": "Other Income",
                        "values": [{"period": "2025", "value": "20"}],
                    },
                    {
                        "type": "total",
                        "label": "Total Income",
                        "values": [{"period": "2025", "value": "120"}],
                    },
                    {
                        "type": "line_item",
                        "label": "Interest Expended",
                        "values": [{"period": "2025", "value": "30"}],
                    },
                    {
                        "type": "line_item",
                        "label": "Operating Expenses",
                        "values": [{"period": "2025", "value": "20"}],
                    },
                    {
                        "type": "line_item",
                        "label": "Provisions & Contingencies",
                        "values": [{"period": "2025", "value": "10"}],
                    },
                    {
                        "type": "total",
                        "label": "Total Expenditure",
                        "values": [{"period": "2025", "value": "60"}],
                    },
                    {
                        "type": "total",
                        "label": "Consolidated Net Profit before Minority Interest",
                        "values": [{"period": "2025", "value": "60"}],
                    },
                    {
                        "type": "line_item",
                        "label": "Minority Interest",
                        "values": [{"period": "2025", "value": "5"}],
                    },
                    {
                        "type": "total",
                        "label": "Consolidated Net Profit attributable to Group",
                        "values": [{"period": "2025", "value": "55"}],
                    },
                ],
            }
        ],
    }

    result = validate_profit_and_loss(data)

    assert result["overall_status"] == "PASS"


def test_cash_flow_validation():
    data = {
        "document_type": "cash_flow_statement",
        "fields": [],
        "line_items": [],
        "tables": [
            {
                "name": "Cash Flow Statement",
                "columns": ["Particulars", "2025"],
                "rows": [
                    {
                        "type": "line_item",
                        "label": "Net Cash Flow from Operating Activities",
                        "values": [
                            {"period": "2025", "value": "100"}
                        ],
                    },
                    {
                        "type": "line_item",
                        "label": "Net Cash Used in Investing Activities",
                        "values": [
                            {"period": "2025", "value": "-30"}
                        ],
                    },
                    {
                        "type": "line_item",
                        "label": "Net Cash Generated from Financing Activities",
                        "values": [
                            {"period": "2025", "value": "20"}
                        ],
                    },
                    {
                        "type": "total",
                        "label": "Net Increase in Cash and Cash Equivalents",
                        "values": [
                            {"period": "2025", "value": "90"}
                        ],
                    },
                    {
                        "type": "line_item",
                        "label": "Opening Cash",
                        "values": [
                            {"period": "2025", "value": "100"}
                        ],
                    },
                    {
                        "type": "total",
                        "label": "Closing Cash",
                        "values": [
                            {"period": "2025", "value": "190"}
                        ],
                    },
                ],
            }
        ],
    }

    result = validate_cash_flow_statement(data)

    assert result["overall_status"] == "PASS"

def test_invoice_incorrect_total_fails():
    data = {
        "document_type": "invoice",
        "fields": [
            {"name": "Subtotal", "value": "100"},
            {"name": "Tax Amount", "value": "10"},
            {"name": "Total", "value": "150"},
        ],
        "line_items": [],
        "tables": [],
    }

    result = validate_invoice(data)

    

    assert result["overall_status"] == "FAIL"


def test_balance_sheet_does_not_balance():
    data = {
        "document_type": "balance_sheet",
        "fields": [],
        "line_items": [],
        "tables": [
            {
                "name": "Balance Sheet",
                "columns": ["Particulars", "2025"],
                "rows": [
                    {
                        "type": "section_header",
                        "label": "ASSETS",
                        "values": [],
                    },
                    {
                        "type": "total",
                        "label": "Total",
                        "values": [
                            {"period": "2025", "value": "1000"}
                        ],
                    },
                    {
                        "type": "section_header",
                        "label": "CAPITAL AND LIABILITIES",
                        "values": [],
                    },
                    {
                        "type": "total",
                        "label": "Total",
                        "values": [
                            {"period": "2025", "value": "900"}
                        ],
                    },
                ],
            }
        ],
    }

    result = validate_balance_sheet(data)

    
    assert result["overall_status"] == "FAIL"


def test_profit_and_loss_incorrect_total_income():
    data = {
        "document_type": "profit_and_loss",
        "fields": [],
        "line_items": [],
        "tables": [
            {
                "name": "Profit and Loss",
                "columns": ["Particulars", "2025"],
                "rows": [
                    {
                        "type": "line_item",
                        "label": "Interest Earned",
                        "values": [
                            {"period": "2025", "value": "100"}
                        ],
                    },
                    {
                        "type": "line_item",
                        "label": "Other Income",
                        "values": [
                            {"period": "2025", "value": "20"}
                        ],
                    },
                    {
                        "type": "total",
                        "label": "Total Income",
                        "values": [
                            {"period": "2025", "value": "150"}
                        ],
                    },
                ],
            }
        ],
    }

    result = validate_profit_and_loss(data)

    
    assert result["overall_status"] == "FAIL"


def test_cash_flow_incorrect_net_change():
    data = {
        "document_type": "cash_flow_statement",
        "fields": [],
        "line_items": [],
        "tables": [
            {
                "name": "Cash Flow Statement",
                "columns": ["Particulars", "2025"],
                "rows": [
                    {
                        "type": "line_item",
                        "label": "Net Cash Flow from Operating Activities",
                        "values": [
                            {"period": "2025", "value": "100"}
                        ],
                    },
                    {
                        "type": "line_item",
                        "label": "Net Cash Used in Investing Activities",
                        "values": [
                            {"period": "2025", "value": "-30"}
                        ],
                    },
                    {
                        "type": "line_item",
                        "label": "Net Cash Generated from Financing Activities",
                        "values": [
                            {"period": "2025", "value": "20"}
                        ],
                    },
                    {
                        "type": "total",
                        "label": "Net Increase in Cash and Cash Equivalents",
                        "values": [
                            {"period": "2025", "value": "200"}
                        ],
                    },
                ],
            }
        ],
    }

    result = validate_cash_flow_statement(data)

    assert result["overall_status"] == "FAIL"