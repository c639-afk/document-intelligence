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

