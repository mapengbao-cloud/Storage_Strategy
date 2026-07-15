"""Shared Excel utilities — safe cell operations, data conversion, sheet copying.

Extracted from:
- 04 Daily_Settlement_Review/generate_review.py (_is_merged, convert_to_numeric, copy_sheet_data)
- 05 Review_Dashboard_and _weeklyreport/process_data.py (clean_value, PCT_COLUMNS)

Key rules:
- Never write to MergedCells (they raise "'MergedCell' object attribute 'value' is read-only")
- Never overwrite formula cells in templates
- All source data must be numeric (int/float) before writing
"""

import openpyxl
from openpyxl.utils import get_column_letter


def is_merged(cell) -> bool:
    """Check if a cell is a non-writable MergedCell."""
    return type(cell).__name__ == "MergedCell"


def is_formula(cell) -> bool:
    """Check if a cell contains an Excel formula."""
    return isinstance(cell.value, str) and str(cell.value).startswith("=")


def safe_write_cell(ws, row: int, col: int, value, number_format: str | None = None):
    """Write a value to a cell, silently skipping MergedCells and formulas.

    Args:
        ws: Worksheet to write to.
        row: 1-based row index.
        col: 1-based column index.
        value: Value to write (will be converted to float/int if possible).
        number_format: Optional Excel number format string to apply.
    """
    cell = ws.cell(row=row, column=col)
    if is_merged(cell):
        return
    if isinstance(cell.value, str) and str(cell.value).startswith("="):
        return
    cell.value = value
    if number_format:
        cell.number_format = number_format


def safe_write_row(ws, row: int, values: list, start_col: int = 2,
                   number_formats: list[str] | None = None):
    """Write a list of values to a row, starting at start_col.

    Skips MergedCells and formula cells automatically.

    Args:
        ws: Target worksheet.
        row: 1-based row index.
        values: List of values to write.
        start_col: Starting column index (default B=2).
        number_formats: Optional list of format strings, one per value.
    """
    for i, val in enumerate(values):
        col = start_col + i
        fmt = number_formats[i] if number_formats else None
        safe_write_cell(ws, row, col, val, fmt)


def copy_sheet_data(src_ws, dst_ws):
    """Copy non-None values from source sheet to destination sheet.

    Preserves destination formulas (won't overwrite cells where dst has a formula).
    Skips MergedCells in both source and destination.
    Copies number_format from source when present.

    Args:
        src_ws: Source worksheet (with data_only=True values).
        dst_ws: Destination worksheet (may contain formulas).
    """
    for row in src_ws.iter_rows(
        min_row=1, max_row=src_ws.max_row, max_col=src_ws.max_column
    ):
        for src_cell in row:
            if src_cell.value is None:
                continue
            dst_cell = dst_ws.cell(row=src_cell.row, column=src_cell.column)
            if is_merged(dst_cell):
                continue
            if is_formula(dst_cell):
                continue
            dst_cell.value = src_cell.value
            if src_cell.number_format and src_cell.number_format != "General":
                dst_cell.number_format = src_cell.number_format


def convert_to_numeric(ws):
    """Convert string cells that look like numbers to float/int in-place.

    Skips formula cells and MergedCells. Useful after copy_sheet_data
    when the source may have string-encoded numbers.

    Args:
        ws: Worksheet to convert in-place.
    """
    for row in ws.iter_rows(
        min_row=1, max_row=ws.max_row, max_col=ws.max_column
    ):
        for cell in row:
            if is_merged(cell) or cell.value is None:
                continue
            if not isinstance(cell.value, str):
                continue
            if str(cell.value).startswith("="):
                continue
            s = str(cell.value).strip()
            try:
                v = float(s)
                if v == int(v) and "." not in s and "e" not in s.lower():
                    cell.value = int(v)
                else:
                    cell.value = v
            except ValueError:
                pass


def copy_number_format_from_previous_row(ws, target_row: int, max_col: int):
    """Copy number_format from the previous row to the target row.

    Used when writing new data rows in the statistics table (Stage 05).
    The previous row's format is the reference for correct display.

    Args:
        ws: Target worksheet.
        target_row: Row to apply formats to.
        max_col: Last column index to process.
    """
    prev_row = target_row - 1
    if prev_row < 1:
        return
    for col in range(1, max_col + 1):
        prev_cell = ws.cell(row=prev_row, column=col)
        target_cell = ws.cell(row=target_row, column=col)
        if prev_cell.number_format and prev_cell.number_format != "General":
            target_cell.number_format = prev_cell.number_format


def write_96point_formulas(ws, row: int, formula_template: str,
                           start_col: int = 2, count: int = 96):
    """Write 96 formulas to a row using column-letter substitution.

    Example:
        write_96point_formulas(ws, row=7, formula_template="{col}3-{col}4-{col}5-{col}6")
        → B7: =B3-B4-B5-B6, C7: =C3-C4-C5-C6, ...

    Args:
        ws: Target worksheet.
        row: 1-based row index.
        formula_template: String with {col} placeholder for column letter.
        start_col: Starting column (default 2 = B).
        count: Number of formulas to write (default 96).
    """
    for i in range(count):
        col = start_col + i
        col_letter = get_column_letter(col)
        formula = formula_template.replace("{col}", col_letter)
        cell = ws.cell(row=row, column=col)
        if not is_merged(cell):
            cell.value = formula


def copy_cell_formats(ws, row: int, max_col: int,
                      number_format_map: dict[int, str]):
    """Apply specific number formats to cells in a row.

    Args:
        ws: Target worksheet.
        row: 1-based row index.
        max_col: Last column index.
        number_format_map: {col_index: format_string} dict.
    """
    for col, fmt in number_format_map.items():
        if col <= max_col:
            cell = ws.cell(row=row, column=col)
            if not is_merged(cell) and not is_formula(cell):
                cell.number_format = fmt