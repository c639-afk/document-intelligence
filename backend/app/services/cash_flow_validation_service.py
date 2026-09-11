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

