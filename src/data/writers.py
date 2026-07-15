"""Safe Excel writers — template-based output generation.

Key rules:
- Never overwrite template formulas or MergedCells
- All data written to Excel must be numeric (int/float)
- Preserve template formatting, only write data values
"""

import shutil
import openpyxl
from pathlib import Path
from typing import Optional

from src.utils.excel_utils import (
    is_merged, is_formula, safe_write_cell, copy_sheet_data,
    convert_to_numeric,
)


def copy_template(template_path: Path, output_path: Path) -> openpyxl.Workbook:
    """Copy a template file to output and open it for writing.

    Args:
        template_path: Path to the template .xlsx file.
        output_path: Path to write the output to.

    Returns:
        Open workbook ready for editing.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_path, output_path)
    return openpyxl.load_workbook(output_path)


def write_96point_data(
    ws, data_rows: list[list[float]],
    start_row: int = 3, start_col: int = 2, count: int = 96
):
    """Write 96-point data rows to a worksheet.

    Used by Stage 01 to write 4 data rows (rows 3-6) to the bidding
    space template.

    Args:
        ws: Target worksheet.
        data_rows: List of lists, each inner list has `count` float values.
        start_row: First data row (1-based).
        start_col: First data column (1-based).
        count: Number of time points per row (default 96).
    """
    for row_offset, values in enumerate(data_rows):
        row = start_row + row_offset
        for col_offset, val in enumerate(values):
            col = start_col + col_offset
            safe_write_cell(ws, row, col, val)


def write_trading_review(
    wb: openpyxl.Workbook,
    sheet_name: str,
    power_values: list[float],
    price_values: list[float],
    data_rows: int = 96,
    start_row: int = 2,
    col_power: int = 14,   # N
    col_price_j: int = 10,  # J: 统一结算日前
    col_price_k: int = 11,  # K: 节点日前电价
):
    """Write 96-point charge/discharge data to a trading review template.

    Used by Stage 02 (day-ahead) and Stage 03 (real-time).
    Both have identical template structure: 报价及预中标 sheet,
    columns J/K/N for price/power.

    Args:
        wb: Open workbook (from copy_template).
        sheet_name: Sheet name (typically '报价及预中标').
        power_values: 96 values for column N (充放电曲线).
        price_values: 96 values for columns J and K (统一/节点电价).
        data_rows: Number of time points (default 96).
        start_row: First data row in template (default 2).
        col_power: Column for power values (default 14 = N).
        col_price_j: Column for unified price (default 10 = J).
        col_price_k: Column for node price (default 11 = K).
    """
    ws = wb[sheet_name]
    for i in range(data_rows):
        row = start_row + i
        safe_write_cell(ws, row, col_price_j, price_values[i])
        safe_write_cell(ws, row, col_price_k, price_values[i])
        safe_write_cell(ws, row, col_power, power_values[i])


def write_settlement_review(
    wb_out: openpyxl.Workbook,
    wb_charge: openpyxl.Workbook,
    wb_discharge: openpyxl.Workbook,
    charge_sheet: str = "日清算数据",
    discharge_sheet: str = "日清算费用",
    target_charge: str = "充电日清算费用",
    target_discharge: str = "放电日清算费用",
):
    """Copy settlement data to the daily settlement review template.

    Steps:
    1. Full copy: charge_sheet → target_charge
    2. Full copy: discharge_sheet → target_discharge
    3. Convert string numbers to numeric in both targets

    Args:
        wb_out: Output workbook (template copy).
        wb_charge: Charge settlement source workbook.
        wb_discharge: Discharge settlement source workbook.
        charge_sheet: Source sheet name in wb_charge.
        discharge_sheet: Source sheet name in wb_discharge.
        target_charge: Target sheet name in wb_out.
        target_discharge: Target sheet name in wb_out.
    """
    # Copy charge settlement data
    copy_sheet_data(wb_charge[charge_sheet], wb_out[target_charge])
    convert_to_numeric(wb_out[target_charge])

    # Copy discharge settlement data
    copy_sheet_data(wb_discharge[discharge_sheet], wb_out[target_discharge])
    convert_to_numeric(wb_out[target_discharge])


def write_review_parameters(
    ws_cf_out,
    ws_cf_source,
    param_rows: list[int] | None = None,
    param_col: int = 9,   # I column
    j4_row: int = 4,
    j4_col: int = 10,     # J column
    j4_value: float | None = None,
):
    """Write I8-I14 parameters and J4 to 充放测算 sheet.

    Args:
        ws_cf_out: Target 充放测算 worksheet.
        ws_cf_source: Source 充放测算 worksheet (for I8-I14 values).
        param_rows: List of rows to copy I-column values from.
            Default: [8, 9, 12, 13, 14].
        param_col: Column for parameter values (default 9 = I).
        j4_row, j4_col: Cell for J4 value (default: row 4, col 10).
        j4_value: J4 capacity coefficient. If None, skipped.
    """
    if param_rows is None:
        param_rows = [8, 9, 12, 13, 14]

    for r in param_rows:
        src_val = ws_cf_source.cell(row=r, column=param_col).value
        if src_val is not None:
            try:
                safe_write_cell(ws_cf_out, r, param_col, float(src_val))
            except (ValueError, TypeError):
                safe_write_cell(ws_cf_out, r, param_col, src_val)

    if j4_value is not None:
        safe_write_cell(ws_cf_out, j4_row, j4_col, j4_value)


def save_and_close(wb: openpyxl.Workbook, output_path: Path) -> Path:
    """Save workbook and close it.

    Args:
        wb: Workbook to save.
        output_path: Path to save to.

    Returns:
        The output path for confirmation.
    """
    wb.save(str(output_path))
    wb.close()
    return output_path


def save_with_fallback(wb: openpyxl.Workbook, output_path: Path) -> Path:
    """Save workbook, falling back to timestamped filename if locked.

    Args:
        wb: Workbook to save.
        output_path: Preferred output path.

    Returns:
        The actual path saved to.
    """
    try:
        wb.save(str(output_path))
        wb.close()
        return output_path
    except PermissionError:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = output_path.stem
        ext = output_path.suffix
        fallback = output_path.parent / f"{stem}_{ts}{ext}"
        wb.save(str(fallback))
        wb.close()
        print(f"[INFO] File locked, saved as: {fallback.name}")
        return fallback