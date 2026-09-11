from decimal import Decimal, InvalidOperation


TOLERANCE = Decimal("0.01")


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

            # Support the older dictionary-based table structure.
            for row in table.get("rows", []):
                if not isinstance(row, dict):
                    continue

                label = str(
                    row.get("label", "")
                ).strip().lower()

                # Look through the row values.
                for value_item in row.get("values", []):
                    if not isinstance(value_item, dict):
                        continue

                    value = value_item.get("value")

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
    # Subtotal + Tax - Discount + Round Off = Total
    # --------------------------------------------------------

    roundoff_raw = get_field(
        "round_off",
        "round off",
        "rounding",
        "rounding adjustment",
    )

    roundoff = invoice_decimal(roundoff_raw)

    if roundoff is None:
        roundoff = Decimal("0")

    if (
        subtotal is not None
        and tax is not None
        and total is not None
    ):
        checks.append(
            make_check(
                "Invoice Total",
                "Subtotal + Tax - Discount + Round Off = Total",
                {
                    "Subtotal": str(subtotal),
                    "Tax": str(tax),
                    "Discount": str(discount),
                    "Round Off": str(roundoff),
                },
                subtotal + tax - discount + roundoff,
                total,
            )
        )
    else:
        checks.append({
            "check": "Invoice Total",
            "formula": (
                "Subtotal + Tax - Discount + Round Off = Total"
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
                "Round Off": str(roundoff),
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
    #
    # If a line-level discount exists in the extracted
    # invoice table, apply:
    #
    # Quantity × Unit Price × (1 - Discount / 100)
    # = Line Total
    #
    # This handles invoices where the line item amount is
    # calculated after a percentage discount.
    # --------------------------------------------------------

    line_items = data.get("line_items", [])

    # --------------------------------------------------------
    # Extract line-level discounts from invoice tables.
    #
    # The current invoice table structure is:
    #
    # columns = ["SI No.", "Description of Goods", ...,
    #            "Disc. %", "Amount"]
    #
    # rows = [
    #     ["1", "...", ..., "Missing", "2499.84"],
    #     ["2", "...", ..., "99 %", "0.45"],
    #     ...
    # ]
    #
    # We match the table row to the line-item number/order.
    # --------------------------------------------------------

    line_discounts = {}

    for table in data.get("tables", []):
        table_name = str(
            table.get("name", "")
        ).strip().lower()

        # Only inspect the invoice line-items table.
        if "line" not in table_name or "item" not in table_name:
            continue

        columns = table.get("columns", [])
        rows = table.get("rows", [])

        if not isinstance(columns, list):
            continue

        normalized_columns = [
            str(column).strip().lower()
            for column in columns
        ]

        discount_index = None

        for column_index, column in enumerate(
            normalized_columns
        ):
            if (
                "disc" in column
                and "%" in column
            ):
                discount_index = column_index
                break

        if discount_index is None:
            continue

        for row_index, row in enumerate(rows):
            if not isinstance(row, list):
                continue

            if discount_index >= len(row):
                continue

            discount_value = row[discount_index]

            if discount_value is None:
                continue

            discount_text = str(
                discount_value
            ).strip()

            if discount_text.lower() in {
                "",
                "missing",
                "null",
                "none",
                "-",
                "—",
                "–",
            }:
                discount = Decimal("0")
            else:
                discount = invoice_decimal(
                    discount_text.replace("%", "")
                )

                if discount is None:
                    continue

            line_discounts[row_index] = discount

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

        # Line item index is 1-based while table row index
        # is 0-based.
        line_discount = line_discounts.get(
            index - 1,
            Decimal("0"),
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
                    "Quantity × Unit Price "
                    "× (1 - Discount %) = Line Total"
                    if line_discount != Decimal("0")
                    else "Quantity × Unit Price = Line Total"
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
                    "Discount": (
                        f"{line_discount}%"
                        if line_discount != Decimal("0")
                        else "0%"
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

        if line_discount != Decimal("0"):
            calculated_amount = (
                quantity
                * unit_price
                * (
                    Decimal("1")
                    - line_discount / Decimal("100")
                )
            )

            formula = (
                "Quantity × Unit Price "
                "× (1 - Discount %) = Line Total"
            )

            inputs = {
                "Quantity": str(quantity),
                "Unit Price": str(unit_price),
                "Discount": f"{line_discount}%",
            }

        else:
            calculated_amount = (
                quantity * unit_price
            )

            formula = (
                "Quantity × Unit Price = Line Total"
            )

            inputs = {
                "Quantity": str(quantity),
                "Unit Price": str(unit_price),
            }

        # Invoice amounts are normally reported to 2 decimal
        # places. Round the calculated result to cents before
        # comparing against the reported amount.
        calculated_amount = calculated_amount.quantize(
            Decimal("0.01")
        )

        checks.append(
            make_check(
                f"Invoice Line Item {index}",
                formula,
                inputs,
                calculated_amount,
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