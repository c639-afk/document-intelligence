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

