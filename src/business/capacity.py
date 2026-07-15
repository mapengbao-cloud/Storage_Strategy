"""Capacity allocation coefficient (J4) computation.

Weighted average of monthly capacity allocation coefficients during
charging periods. Extracted from compute_J4() in
04 Daily_Settlement_Review/generate_review.py and the identical logic
in 05 Review_Dashboard_and _weeklyreport/process_data.py.

Formula:
    J_val = sum(coeff_i * charge_mwh_i) / sum(charge_mwh_i)
    where charge_mwh_i = n_val_i / 4 for periods where n_val_i <= 0

The month column is determined by the current month. The 容量分摊系数
sheet has 12 month columns (J column = column 10 for May, etc.).
"""

from src.config import get_month_column
from src.utils.numerics import safe_float


def compute_J_val(
    cap_coefficients: list[float],  # 96 monthly coefficients
    power_mw: list[float],          # 96 charge/discharge values (N column)
    time_interval_hours: float = 0.25,
) -> float:
    """Compute weighted average of capacity allocation coefficients.

    Only charging periods (power <= 0) contribute to the weighted average.

    Args:
        cap_coefficients: 96 values from 容量分摊系数 sheet, month column.
            Row 8-103 in the sheet (= time points 1-96).
        power_mw: 96 charge/discharge power values from 报价及预中标 N column.
            Negative = charging, Positive = discharging.
        time_interval_hours: 0.25 for 15-min intervals.

    Returns:
        Weighted average coefficient, or 0.0 if no charging periods.
    """
    numer = 0.0
    denom = 0.0

    # Ensure both lists have 96 elements
    n = min(len(cap_coefficients), len(power_mw))

    for i in range(n):
        coeff = cap_coefficients[i]
        power = power_mw[i]

        if coeff is None or power is None:
            continue

        try:
            coeff = float(coeff)
            power = float(power)
        except (ValueError, TypeError):
            continue

        if power <= 0:  # charging period (including idle at 0)
            charge_mwh = power * time_interval_hours  # power is negative
            numer += coeff * charge_mwh
            denom += charge_mwh

    return numer / denom if denom != 0 else 0.0


def compute_J_val_from_workbook(cap_ws, price_ws, month: int) -> float:
    """Compute J4 from open workbook sheets (legacy interface).

    Reads capacity coefficients from the month column (8-103) and
    power values from 报价及预中标 N column (rows 2-97).

    Args:
        cap_ws: 容量分摊系数 worksheet.
        price_ws: 报价及预中标 worksheet.
        month: Month number (1-12), determines which column to read.

    Returns:
        Weighted average coefficient.
    """
    month_col = get_month_column(month)
    cap_numer = 0.0
    cap_denom = 0.0

    for r in range(8, cap_ws.max_row + 1):
        price_row = r - 6  # cap row 8 → price row 2
        coeff = cap_ws.cell(row=r, column=month_col).value
        n_val = price_ws.cell(row=price_row, column=14).value  # N column

        if coeff is None or n_val is None:
            continue

        try:
            coeff = float(coeff)
            n_val = float(n_val)
        except (ValueError, TypeError):
            continue

        if n_val <= 0:  # charging period
            charge_mwh = n_val / 4
            cap_numer += coeff * charge_mwh
            cap_denom += charge_mwh

    return cap_numer / cap_denom if cap_denom != 0 else 0.0