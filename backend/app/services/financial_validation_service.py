from decimal import Decimal, InvalidOperation


TOLERANCE = Decimal("0.01")


# ============================================================
# COMMON HELPERS
# ============================================================

def to_decimal(value):
    if value is None:
        return None

    try:
        value = str(value).strip()

        if value in {"", "-", "—", "–", "null", "None"}:
            return None

        negative = value.startswith("(") and value.endswith(")")

        value = (
            value
            .replace(",", "")
            .replace("₹", "")
            .replace("$", "")
            .replace("€", "")
            .replace("(", "")
            .replace(")", "")
            .strip()
        )

        number = Decimal(value)

        return -number if negative else number

    except (InvalidOperation, ValueError, TypeError):
        return None


def make_check(
    name,
    formula,
    inputs,
    calculated_value,
    reported_value,
):
    if calculated_value is None or reported_value is None:
        return {
            "check": name,
            "formula": formula,
            "input_values": inputs,
            "calculated_value": (
                str(calculated_value)
                if calculated_value is not None
                else None
            ),
            "reported_value": (
                str(reported_value)
                if reported_value is not None
                else None
            ),
            "variance": None,
            "status": "NOT_APPLICABLE",
        }

    variance = calculated_value - reported_value

    return {
        "check": name,
        "formula": formula,
        "input_values": inputs,
        "calculated_value": str(calculated_value),
        "reported_value": str(reported_value),
        "variance": str(variance),
        "status": (
            "PASS"
            if abs(variance) <= TOLERANCE
            else "FAIL"
        ),
    }


def get_all_rows(data):
    """
    Canonical structure:

    tables
      -> rows

    Also supports tables -> sections -> rows so that
    older extracted documents do not crash the service.
    """

    rows = []

    for table in data.get("tables", []):

        for row in table.get("rows", []):
            if isinstance(row, dict):
                rows.append(row)

        for section in table.get("sections", []):
            for row in section.get("rows", []):
                if isinstance(row, dict):
                    rows.append(row)

            for row in section.get("line_items", []):
                if isinstance(row, dict):
                    rows.append(row)

    return rows


def row_label(row):
    for key in [
        "label",
        "particulars",
        "line_item",
        "name",
        "description",
    ]:
        value = row.get(key)

        if value is not None and str(value).strip():
            return str(value).strip()

    return ""


def get_period_value(row, period):
    if not row:
        return None

    # Canonical structure:
    #
    # "values": [
    #   {"period": "31-Mar-17", "value": "..."}
    # ]

    for item in row.get("values", []):
        if not isinstance(item, dict):
            continue

        item_period = str(
            item.get("period", "")
        ).strip().lower()

        if item_period == str(period).strip().lower():
            return to_decimal(item.get("value"))

    # Compatibility with older flat structure
    if period in row:
        return to_decimal(row.get(period))

    for key, value in row.items():
        if str(key).strip().lower() == str(period).strip().lower():
            return to_decimal(value)

    return None


def get_periods(data):
    periods = set()

    for row in get_all_rows(data):
        for item in row.get("values", []):
            if isinstance(item, dict):
                period = item.get("period")

                if period:
                    periods.add(str(period).strip())

        # Compatibility with flat rows
        for key in row.keys():
            key_lower = str(key).lower()

            if (
                key_lower.startswith("as_at_")
                or key_lower.startswith("year_ended_")
            ):
                periods.add(str(key))

    return sorted(periods)


def find_rows(data, *names):
    rows = get_all_rows(data)

    names = [
        str(name).strip().lower()
        for name in names
    ]

    matches = []

    for row in rows:
        label = row_label(row).lower()

        for name in names:
            if name in label:
                matches.append(row)
                break

    return matches


def find_row(data, *names):
    matches = find_rows(data, *names)

    return matches[0] if matches else None


def overall_status(checks):
    applicable = [
        check
        for check in checks
        if check["status"] != "NOT_APPLICABLE"
    ]

    if any(
        check["status"] == "FAIL"
        for check in applicable
    ):
        return "FAIL"

    if applicable:
        return "PASS"

    return "NOT_APPLICABLE"


# ============================================================
# INVOICE
# ============================================================

# ============================================================
# INVOICE
# ============================================================

def validate_invoice(data):
    checks = []

    fields = {
        str(field.get("name", "")).strip().lower(): field.get("value")
        for field in data.get("fields", [])
        if isinstance(field, dict)
    }

    # --------------------------------------------------------
    # Invoice-specific number parsing
    # --------------------------------------------------------

    def invoice_decimal(value):
        if value is None:
            return None

        value = str(value).strip()

        if value in {"", "-", "—", "–", "null", "None"}:
            return None

        negative = (
            value.startswith("(")
            and value.endswith(")")
        )

        value = value.replace("(", "").replace(")", "")
        value = (
            value.replace("₹", "")
            .replace("$", "")
            .replace("€", "")
            .strip()
        )

        # Handle decimal comma formats:
        # 126,27 -> 126.27
        # 12,63  -> 12.63
        # 1,234.56 -> 1234.56

        if "," in value and "." not in value:
            parts = value.split(",")

            if len(parts) == 2 and len(parts[1]) <= 2:
                value = ".".join(parts)
            else:
                value = "".join(parts)

        else:
            value = value.replace(",", "")

        try:
            number = Decimal(value)
            return -number if negative else number

        except (InvalidOperation, ValueError, TypeError):
            return None

    # --------------------------------------------------------
    # Find field using multiple possible names
    # --------------------------------------------------------

    def get_field(*names):
        for name in names:
            value = fields.get(name.lower())

            if value is not None:
                return value

        return None

    # --------------------------------------------------------
    # SUMMARY TABLE FALLBACK
    #
    # Some invoices put totals in a SUMMARY table instead
    # of the top-level fields.
    # --------------------------------------------------------

    def get_summary_value(*names):
        names = {
            str(name).strip().lower()
            for name in names
        }

        for table in data.get("tables", []):
            table_name = str(
                table.get("name", "")
            ).strip().lower()

            if "summary" not in table_name:
                continue

            for row in table.get("rows", []):
                if not isinstance(row, dict):
                    continue

                label = str(
                    row.get("label", "")
                ).strip().lower()

                # Look through the row values.
                # For this invoice the SUMMARY table has:
                #
                # VAT [%] | Net worth | VAT | Gross worth
                #
                # and the Total row contains the values.

                for value_item in row.get("values", []):
                    if not isinstance(value_item, dict):
                        continue

                    value = value_item.get("value")

                    if label == "total":
                        continue

                    if value is None:
                        continue

                # Handle rows where the label itself identifies
                # the value.
                if label in names:
                    values = row.get("values", [])

                    for value_item in values:
                        if isinstance(value_item, dict):
                            value = value_item.get("value")

                            if value is not None:
                                return value

            # ------------------------------------------------
            # Canonical Gemini table structure:
            #
            # columns = ["VAT [%]", "Net worth", "VAT",
            #            "Gross worth"]
            #
            # rows contain values with the same order.
            # ------------------------------------------------

            columns = [
                str(column).strip().lower()
                for column in table.get("columns", [])
            ]

            if columns:
                total_row = None

                for row in table.get("rows", []):
                    if not isinstance(row, dict):
                        continue

                    label = str(
                        row.get("label", "")
                    ).strip().lower()

                    if label == "total":
                        total_row = row
                        break

                if total_row is not None:
                    values = total_row.get("values", [])

                    for wanted_name in names:
                        if wanted_name not in columns:
                            continue

                        column_index = columns.index(
                            wanted_name
                        )

                        if column_index < len(values):
                            value_item = values[column_index]

                            if isinstance(value_item, dict):
                                value = value_item.get("value")

                                if value is not None:
                                    return value

        return None

    # --------------------------------------------------------
    # Find invoice totals
    #
    # Fields are preferred.
    # SUMMARY table is used as fallback.
    # --------------------------------------------------------

    subtotal_raw = get_field(
        "subtotal",
        "total net amount",
        "total_net_amount",
        "net total",
        "net amount",
        "net_amount",
        "net worth",
        "net_worth",
    )

    if subtotal_raw is None:
        subtotal_raw = get_summary_value(
            "net worth",
            "net_worth",
        )

    tax_raw = get_field(
        "tax amount",
        "total vat amount",
        "total_vat_amount",
        "tax_amount",
        "vat total",
        "vat amount",
        "vat_amount",
    )

    if tax_raw is None:
        tax_raw = get_summary_value(
            "vat",
            "vat amount",
            "vat_amount",
        )

    discount_raw = get_field(
        "discount",
        "discount amount",
        "discount_amount",
    )

    total_raw = get_field(
        "total amount",
        "total_amount",
        "gross amount",
        "gross_amount",
        "gross total",
        "invoice total",
        "total",
        "gross worth",
        "gross_worth",
    )

    if total_raw is None:
        total_raw = get_summary_value(
            "gross worth",
            "gross_worth",
        )

    subtotal = invoice_decimal(subtotal_raw)
    tax = invoice_decimal(tax_raw)
    discount = invoice_decimal(discount_raw)

    if discount is None:
        discount = Decimal("0")

    total = invoice_decimal(total_raw)

    # --------------------------------------------------------
    # Check 1:
    #
    # Subtotal + Tax - Discount = Total
    # --------------------------------------------------------

    if (
        subtotal is not None
        and tax is not None
        and total is not None
    ):
        checks.append(
            make_check(
                "Invoice Total",
                "Subtotal + Tax - Discount = Total",
                {
                    "Subtotal": str(subtotal),
                    "Tax": str(tax),
                    "Discount": str(discount),
                },
                subtotal + tax - discount,
                total,
            )
        )

    else:
        checks.append({
            "check": "Invoice Total",
            "formula": (
                "Subtotal + Tax - Discount = Total"
            ),
            "input_values": {
                "Subtotal": (
                    str(subtotal)
                    if subtotal is not None
                    else None
                ),
                "Tax": (
                    str(tax)
                    if tax is not None
                    else None
                ),
                "Discount": str(discount),
            },
            "calculated_value": None,
            "reported_value": (
                str(total)
                if total is not None
                else None
            ),
            "variance": None,
            "status": "NOT_APPLICABLE",
        })

    # --------------------------------------------------------
    # Check 2:
    #
    # Quantity × Unit Price = Line Total
    # --------------------------------------------------------

    line_items = data.get("line_items", [])

    for index, item in enumerate(
        line_items,
        start=1,
    ):
        if not isinstance(item, dict):
            continue

        quantity = invoice_decimal(
            item.get("quantity")
        )

        unit_price = invoice_decimal(
            item.get("unit_price")
        )

        amount = invoice_decimal(
            item.get("amount")
        )

        if (
            quantity is None
            or unit_price is None
            or amount is None
        ):
            checks.append({
                "check": (
                    f"Invoice Line Item {index}"
                ),
                "formula": (
                    "Quantity × Unit Price = Line Total"
                ),
                "input_values": {
                    "Quantity": (
                        str(quantity)
                        if quantity is not None
                        else None
                    ),
                    "Unit Price": (
                        str(unit_price)
                        if unit_price is not None
                        else None
                    ),
                },
                "calculated_value": None,
                "reported_value": (
                    str(amount)
                    if amount is not None
                    else None
                ),
                "variance": None,
                "status": "NOT_APPLICABLE",
            })

            continue

        checks.append(
            make_check(
                f"Invoice Line Item {index}",
                "Quantity × Unit Price = Line Total",
                {
                    "Quantity": str(quantity),
                    "Unit Price": str(unit_price),
                },
                quantity * unit_price,
                amount,
            )
        )

    # --------------------------------------------------------
    # Check 3:
    #
    # Sum of line item amounts = Subtotal
    # --------------------------------------------------------

    line_amounts = []

    for item in line_items:
        if not isinstance(item, dict):
            continue

        amount = invoice_decimal(
            item.get("amount")
        )

        if amount is not None:
            line_amounts.append(amount)

    if (
        line_amounts
        and subtotal is not None
        and len(line_amounts) == len(line_items)
    ):
        calculated_line_total = sum(
            line_amounts,
            Decimal("0"),
        )

        checks.append(
            make_check(
                "Invoice Line Items Subtotal",
                "Sum of Line Item Amounts = Subtotal",
                {
                    "Line Item Amounts": [
                        str(value)
                        for value in line_amounts
                    ],
                    "Subtotal": str(subtotal),
                },
                calculated_line_total,
                subtotal,
            )
        )

    # --------------------------------------------------------
    # Check 4:
    #
    # Subtotal × Tax Rate = Tax
    # --------------------------------------------------------

    tax_rates = []

    for item in line_items:
        if not isinstance(item, dict):
            continue

        tax_rate = invoice_decimal(
            str(item.get("tax_rate", "")).replace("%", "")
        )

        if tax_rate is not None:
            tax_rates.append(tax_rate)

    unique_tax_rates = set(tax_rates)

    if (
        subtotal is not None
        and tax is not None
        and len(unique_tax_rates) == 1
    ):
        tax_rate = tax_rates[0]

        calculated_tax = (
            subtotal * tax_rate / Decimal("100")
        )

        checks.append(
            make_check(
                "Invoice Tax",
                "Subtotal × Tax Rate = Tax",
                {
                    "Subtotal": str(subtotal),
                    "Tax Rate": f"{tax_rate}%",
                },
                calculated_tax,
                tax,
            )
        )
    else:
        checks.append({
            "check": "Invoice Tax",
            "formula": "Subtotal × Tax Rate = Tax",
            "input_values": {
                "Subtotal": (
                    str(subtotal)
                    if subtotal is not None
                    else None
                ),
                "Tax Rate": (
                    f"{tax_rates[0]}%"
                    if len(unique_tax_rates) == 1
                    else None
                ),
            },
            "calculated_value": None,
            "reported_value": (
                str(tax)
                if tax is not None
                else None
            ),
            "variance": None,
            "status": "NOT_APPLICABLE",
        })

    # --------------------------------------------------------
    # Overall status
    # --------------------------------------------------------

    status = overall_status(checks)

    issues = [
        check["check"]
        for check in checks
        if check["status"] == "FAIL"
    ]

    return {
        "checks": checks,
        "overall_status": status,
        "issues": issues,
    }

# ============================================================
# BALANCE SHEET
# ============================================================

# ============================================================
# BALANCE SHEET
# ============================================================

def validate_balance_sheet(data):
    checks = []
    issues = []

    rows = get_all_rows(data)

    periods = get_periods(data)

    capital_total = None
    asset_total = None

    # --------------------------------------------------------
    # Track which section a row belongs to.
    # --------------------------------------------------------

    current_section = ""

    for table in data.get("tables", []):

        # Canonical format
        for row in table.get("rows", []):

            row_type = str(
                row.get("type", "")
            ).lower()

            if row_type == "section_header":
                current_section = row_label(row).upper()
                continue

            if row_type != "total":
                continue

            label = row_label(row).lower()

            if label != "total":
                continue

            values = {
                period: get_period_value(
                    row,
                    period
                )
                for period in periods
            }

            if "CAPITAL AND LIABILITIES" in current_section:
                capital_total = values

            elif current_section == "ASSETS":
                asset_total = values

    # --------------------------------------------------------
    # If canonical rows were not found, inspect sections.
    # --------------------------------------------------------

    if capital_total is None or asset_total is None:

        for table in data.get("tables", []):

            for section in table.get(
                "sections",
                []
            ):

                section_name = str(
                    section.get(
                        "name",
                        section.get(
                            "section_name",
                            ""
                        )
                    )
                ).upper()

                rows_in_section = (
                    section.get("rows", [])
                    or section.get("line_items", [])
                )

                for row in rows_in_section:

                    if str(
                        row.get("type", "")
                    ).lower() != "total":
                        continue

                    if row_label(row).lower() != "total":
                        continue

                    values = {
                        period: get_period_value(
                            row,
                            period
                        )
                        for period in periods
                    }

                    if (
                        "CAPITAL AND LIABILITIES"
                        in section_name
                    ):
                        capital_total = values

                    elif section_name == "ASSETS":
                        asset_total = values

    if capital_total is None or asset_total is None:
        return {
            "checks": [],
            "overall_status": "NOT_APPLICABLE",
            "issues": [
                "Required Balance Sheet totals "
                "could not be identified."
            ],
        }

    # --------------------------------------------------------
    # Balance Sheet equation for EVERY period
    # --------------------------------------------------------

    for period in periods:

        capital_value = capital_total.get(period)
        assets_value = asset_total.get(period)

        if (
            capital_value is None
            or assets_value is None
        ):
            checks.append({
                "check": (
                    f"Balance Sheet Equation - "
                    f"{period}"
                ),
                "formula": (
                    "Total Assets = "
                    "Total Capital and Liabilities"
                ),
                "input_values": {
                    "Total Assets": (
                        str(assets_value)
                        if assets_value is not None
                        else None
                    ),
                    "Total Capital and Liabilities": (
                        str(capital_value)
                        if capital_value is not None
                        else None
                    ),
                },
                "calculated_value": None,
                "reported_value": (
                    str(assets_value)
                    if assets_value is not None
                    else None
                ),
                "variance": None,
                "status": "NOT_APPLICABLE",
            })

            continue

        checks.append(
            make_check(
                f"Balance Sheet Equation - {period}",
                "Total Assets = Total Capital and Liabilities",
                {
                    "Total Assets": str(assets_value),
                    "Total Capital and Liabilities": (
                        str(capital_value)
                    ),
                },
                capital_value,
                assets_value,
            )
        )

    status = overall_status(checks)

    issues = [
        check["check"]
        for check in checks
        if check["status"] == "FAIL"
    ]

    return {
        "checks": checks,
        "overall_status": status,
        "issues": issues,
    }


# ============================================================
# PROFIT & LOSS
# ============================================================

def validate_profit_and_loss(data):
    checks = []

    rows = get_all_rows(data)
    periods = get_periods(data)

    if not rows:
        return {
            "checks": [],
            "overall_status": "NOT_APPLICABLE",
            "issues": [
                "No Profit and Loss rows were found."
            ],
        }

    # --------------------------------------------------------
    # Helper to find exact/partial row
    # --------------------------------------------------------

    def find(*names):
        names_lower = [
            name.lower()
            for name in names
        ]

        for row in rows:
            label = row_label(row).lower()

            for name in names_lower:
                if name in label:
                    return row

        return None

    interest_earned = find(
        "interest earned"
    )

    other_income = find(
        "other income"
    )

    total_income = find(
        "total income"
    )

    interest_expended = find(
        "interest expended"
    )

    operating_expenses = find(
        "operating expenses"
    )

    provisions = find(
        "provisions and contingencies"
    )

    total_expenditure = find(
        "total expenditure"
    )

    net_profit = find(
        "net profit for the year",
        "net profit"
    )

    minority = find(
        "minority interest"
    )

    associates = find(
        "share in profits of associates",
        "associates"
    )

    consolidated = find(
        "consolidated profit for the year attributable to the group",
        "consolidated profit"
    )

    # --------------------------------------------------------
    # Determine periods
    # --------------------------------------------------------

    if not periods:
        periods = [
            "year_ended_31_mar_17",
            "year_ended_31_mar_16",
        ]

    for period in periods:

        # ----------------------------------------------------
        # Total Income
        # ----------------------------------------------------

        interest_value = get_period_value(
            interest_earned,
            period
        )

        other_value = get_period_value(
            other_income,
            period
        )

        income_total = get_period_value(
            total_income,
            period
        )

        if (
            interest_value is not None
            and other_value is not None
            and income_total is not None
        ):
            checks.append(
                make_check(
                    f"P&L Total Income - {period}",
                    "Interest Earned + Other Income = Total Income",
                    {
                        "Interest Earned": str(
                            interest_value
                        ),
                        "Other Income": str(
                            other_value
                        ),
                    },
                    interest_value + other_value,
                    income_total,
                )
            )

        # ----------------------------------------------------
        # Total Expenditure
        # ----------------------------------------------------

        interest_expended_value = get_period_value(
            interest_expended,
            period
        )

        operating_value = get_period_value(
            operating_expenses,
            period
        )

        provisions_value = get_period_value(
            provisions,
            period
        )

        expenditure_total = get_period_value(
            total_expenditure,
            period
        )

        if all(
            value is not None
            for value in [
                interest_expended_value,
                operating_value,
                provisions_value,
                expenditure_total,
            ]
        ):
            checks.append(
                make_check(
                    f"P&L Total Expenditure - {period}",
                    (
                        "Interest Expended + Operating Expenses "
                        "+ Provisions and Contingencies "
                        "= Total Expenditure"
                    ),
                    {
                        "Interest Expended": str(
                            interest_expended_value
                        ),
                        "Operating Expenses": str(
                            operating_value
                        ),
                        "Provisions and Contingencies": str(
                            provisions_value
                        ),
                    },
                    (
                        interest_expended_value
                        + operating_value
                        + provisions_value
                    ),
                    expenditure_total,
                )
            )

        # ----------------------------------------------------
        # Net Profit
        # ----------------------------------------------------

        net_profit_value = get_period_value(
            net_profit,
            period
        )

        if (
            income_total is not None
            and expenditure_total is not None
            and net_profit_value is not None
        ):
            checks.append(
                make_check(
                    f"P&L Net Profit - {period}",
                    "Total Income - Total Expenditure = Net Profit",
                    {
                        "Total Income": str(
                            income_total
                        ),
                        "Total Expenditure": str(
                            expenditure_total
                        ),
                    },
                    income_total - expenditure_total,
                    net_profit_value,
                )
            )

        # ----------------------------------------------------
        # Consolidated Profit
        # ----------------------------------------------------

        minority_value = get_period_value(
            minority,
            period
        )

        associates_value = get_period_value(
            associates,
            period
        )

        consolidated_value = get_period_value(
            consolidated,
            period
        )

        if (
            net_profit_value is not None
            and minority_value is not None
            and associates_value is not None
            and consolidated_value is not None
        ):
            checks.append(
                make_check(
                    f"P&L Consolidated Profit - {period}",
                    (
                        "Net Profit - Minority Interest "
                        "+ Share in Profits of Associates "
                        "= Consolidated Profit"
                    ),
                    {
                        "Net Profit": str(
                            net_profit_value
                        ),
                        "Minority Interest": str(
                            minority_value
                        ),
                        "Share in Profits of Associates": str(
                            associates_value
                        ),
                    },
                    (
                        net_profit_value
                        - minority_value
                        + associates_value
                    ),
                    consolidated_value,
                )
            )

    status = overall_status(checks)

    issues = [
        check["check"]
        for check in checks
        if check["status"] == "FAIL"
    ]

    return {
        "checks": checks,
        "overall_status": status,
        "issues": issues,
    }


# ============================================================
# CASH FLOW
# ============================================================

def validate_cash_flow_statement(data):
    checks = []
    rows = get_all_rows(data)
    periods = get_periods(data)

    if not rows:
        return {
            "checks": [],
            "overall_status": "NOT_APPLICABLE",
            "issues": ["No Cash Flow rows were found."],
        }

    def find_row_by_label(*patterns):
        patterns = [p.lower() for p in patterns]

        for row in rows:
            label = row_label(row).lower()

            for pattern in patterns:
                if pattern in label:
                    return row

        return None

    # ========================================================
    # IDENTIFY CASH FLOW ROWS
    # ========================================================

    operating = find_row_by_label(
        "net cash flow (used in) / from operating activities",
        "net cash flow from operating activities",
        "net cash flow used in operating activities",
    )

    investing = find_row_by_label(
        "net cash used in investing activities",
        "net cash flow from investing activities",
        "net cash flow used in investing activities",
    )

    financing = find_row_by_label(
        "net cash generated from financing activities",
        "net cash flow from financing activities",
        "net cash flow used in financing activities",
    )

    fx_adjustment = find_row_by_label(
        "effect of exchange fluctuation on translation reserve",
        "foreign exchange",
        "exchange fluctuation",
    )

    amalgamation = find_row_by_label(
        "cash and cash equivalents on amalgamation",
        "cash acquired on amalgamation",
    )

    net_change = find_row_by_label(
        "net increase / (decrease) in cash and cash equivalents",
        "net increase in cash and cash equivalents",
        "net change in cash and cash equivalents",
    )

    opening_cash = find_row_by_label(
        "cash and cash equivalents as at april 1st",
        "cash and cash equivalents at beginning",
        "opening cash",
    )

    closing_cash = find_row_by_label(
        "cash and cash equivalents as at march 31st",
        "cash and cash equivalents at end",
        "closing cash",
    )

    if not periods:
        return {
            "checks": [],
            "overall_status": "NOT_APPLICABLE",
            "issues": ["No reporting periods were found."],
        }

    # ========================================================
    # VALIDATE EACH PERIOD
    # ========================================================

    for period in periods:

        operating_value = get_period_value(
            operating, period
        )

        investing_value = get_period_value(
            investing, period
        )

        financing_value = get_period_value(
            financing, period
        )

        fx_value = get_period_value(
            fx_adjustment, period
        )

        amalgamation_value = get_period_value(
            amalgamation, period
        )

        net_change_value = get_period_value(
            net_change, period
        )

        opening_value = get_period_value(
            opening_cash, period
        )

        closing_value = get_period_value(
            closing_cash, period
        )

        # ----------------------------------------------------
        # CHECK 1:
        #
        # Operating + Investing + Financing
        # + FX + Amalgamation (if reported)
        # = Net Change in Cash
        # ----------------------------------------------------

        if (
            operating_value is not None
            and investing_value is not None
            and financing_value is not None
            and net_change_value is not None
        ):
            inputs = {
                "Operating Cash Flow": str(
                    operating_value
                ),
                "Investing Cash Flow": str(
                    investing_value
                ),
                "Financing Cash Flow": str(
                    financing_value
                ),
            }

            calculated_value = (
                operating_value
                + investing_value
                + financing_value
            )

            formula = (
                "Operating Cash Flow + "
                "Investing Cash Flow + "
                "Financing Cash Flow = "
                "Net Change in Cash"
            )

            if fx_value is not None:
                inputs["FX Adjustment"] = str(
                    fx_value
                )

                calculated_value += fx_value

                formula = (
                    "Operating Cash Flow + "
                    "Investing Cash Flow + "
                    "Financing Cash Flow + "
                    "FX Adjustment = "
                    "Net Change in Cash"
                )

            if amalgamation_value is not None:
                inputs["Cash Acquired on Amalgamation"] = str(
                    amalgamation_value
                )

                calculated_value += amalgamation_value

                formula = (
                    formula.replace(
                        " = Net Change in Cash",
                        " + Cash Acquired on Amalgamation "
                        "= Net Change in Cash",
                    )
                )

            checks.append(
                make_check(
                    f"Cash Flow Net Change - {period}",
                    formula,
                    inputs,
                    calculated_value,
                    net_change_value,
                )
            )

        else:
            checks.append({
                "check": (
                    f"Cash Flow Net Change - {period}"
                ),
                "formula": (
                    "Operating Cash Flow + "
                    "Investing Cash Flow + "
                    "Financing Cash Flow + "
                    "optional adjustments = "
                    "Net Change in Cash"
                ),
                "input_values": {
                    "Operating Cash Flow": (
                        str(operating_value)
                        if operating_value is not None
                        else None
                    ),
                    "Investing Cash Flow": (
                        str(investing_value)
                        if investing_value is not None
                        else None
                    ),
                    "Financing Cash Flow": (
                        str(financing_value)
                        if financing_value is not None
                        else None
                    ),
                    "FX Adjustment": (
                        str(fx_value)
                        if fx_value is not None
                        else None
                    ),
                    "Cash Acquired on Amalgamation": (
                        str(amalgamation_value)
                        if amalgamation_value is not None
                        else None
                    ),
                },
                "calculated_value": None,
                "reported_value": (
                    str(net_change_value)
                    if net_change_value is not None
                    else None
                ),
                "variance": None,
                "status": "NOT_APPLICABLE",
            })

        # ----------------------------------------------------
        # CHECK 2:
        #
        # Opening Cash + Net Change in Cash = Closing Cash
        #
        # IMPORTANT:
        # Do NOT add amalgamation here.
        # Amalgamation is already included in Net Change
        # when it is reported as part of the cash-flow bridge.
        # ----------------------------------------------------

        if (
            opening_value is not None
            and net_change_value is not None
            and closing_value is not None
        ):
            checks.append(
                make_check(
                    f"Cash Flow Closing Cash - {period}",
                    (
                        "Opening Cash + "
                        "Net Change in Cash = "
                        "Closing Cash"
                    ),
                    {
                        "Opening Cash": str(
                            opening_value
                        ),
                        "Net Change in Cash": str(
                            net_change_value
                        ),
                    },
                    opening_value + net_change_value,
                    closing_value,
                )
            )

        else:
            checks.append({
                "check": (
                    f"Cash Flow Closing Cash - {period}"
                ),
                "formula": (
                    "Opening Cash + "
                    "Net Change in Cash = "
                    "Closing Cash"
                ),
                "input_values": {
                    "Opening Cash": (
                        str(opening_value)
                        if opening_value is not None
                        else None
                    ),
                    "Net Change in Cash": (
                        str(net_change_value)
                        if net_change_value is not None
                        else None
                    ),
                },
                "calculated_value": None,
                "reported_value": (
                    str(closing_value)
                    if closing_value is not None
                    else None
                ),
                "variance": None,
                "status": "NOT_APPLICABLE",
            })

    # ========================================================
    # OVERALL STATUS
    # ========================================================

    applicable_checks = [
        check
        for check in checks
        if check["status"] != "NOT_APPLICABLE"
    ]

    if any(
        check["status"] == "FAIL"
        for check in applicable_checks
    ):
        overall_status = "FAIL"

    elif applicable_checks:
        overall_status = "PASS"

    else:
        overall_status = "NOT_APPLICABLE"

    issues = [
        check["check"]
        for check in checks
        if check["status"] == "FAIL"
    ]

    return {
        "checks": checks,
        "overall_status": overall_status,
        "issues": issues,
    }


# ============================================================
# MAIN DISPATCHER
# ============================================================

def validate_financial_data(
    document_type,
    extracted_data,
):
    if document_type == "invoice":
        return validate_invoice(extracted_data)

    if document_type == "balance_sheet":
        return validate_balance_sheet(extracted_data)

    if document_type == "profit_and_loss":
        return validate_profit_and_loss(extracted_data)

    if document_type == "cash_flow_statement":
        return validate_cash_flow_statement(
            extracted_data
        )

    return {
        "checks": [],
        "overall_status": "NOT_APPLICABLE",
        "issues": [
            f"Unsupported document type: {document_type}"
        ],
    }

