"""Generate bidding space analysis for a given date.

Usage:
    python generate.py MMDD                          # prediction (auto-find source)
    python generate.py MMDD <source_path>            # explicit source
    python generate.py MMDD actual                   # actual grid data (auto-find)
    python generate.py MMDD actual <source_path>     # explicit actual source
"""

import sys
from pathlib import Path
import pandas as pd
import openpyxl

ROOT = Path(__file__).parent
TEMPLATE = ROOT / "assets" / "输出模版-0521-竞价空间分析.xlsx"


def _read_prediction(src: Path) -> list[list[float]]:
    """Read 4 sheets from prediction .xls, return 4 rows of 96 floats."""
    sheet_names = ["直调负荷", "联络线受电负荷", "风电总加", "光伏总加"]
    rows = []
    for sn in sheet_names:
        df = pd.read_excel(src, sheet_name=sn, header=None)
        values = [float(df.iloc[2, c]) for c in range(1, 97)]
        rows.append(values)
    return rows


def _read_actual(src: Path) -> list[list[float]]:
    """Read 负荷信息 sheet from actual .xlsx, return 4 rows of 96 floats."""
    df = pd.read_excel(src, sheet_name="负荷信息", header=None)
    # 直调负荷=C(2), 联络线受电=D(3), 风电=E(4), 光伏=F(5)
    col_map = [2, 3, 4, 5]
    rows = []
    for ci in col_map:
        values = [float(df.iloc[r, ci]) for r in range(1, 97)]
        rows.append(values)
    return rows


def _write_formulas(ws, col_count: int = 97):
    """Write formulas to row 7, columns B-CS (2-97)."""
    # Row 7: 竞价空间 = col3 - col4 - col5 - col6
    for c in range(2, col_count + 1):
        col_letter = openpyxl.utils.get_column_letter(c)
        ws.cell(row=7, column=c, value=f"={col_letter}3-{col_letter}4-{col_letter}5-{col_letter}6")


def generate(date_str: str, source_path: str | None = None, is_actual: bool = False):
    """Generate one bidding space analysis file."""
    suffix = "实际" if is_actual else "预测"
    out_path = ROOT / "output" / f"{date_str}-竞价空间分析({suffix}).xlsx"

    if source_path:
        src = Path(source_path)
    elif is_actual:
        src = ROOT / "assets" / f"{date_str}-电网运行实际信息.xlsx"
    else:
        # Find matching prediction file YYYY-MM-DD负荷信息预测.xls
        candidates = list(ROOT.glob(f"assets/*-{date_str}负荷信息预测.xls"))
        # Also try YYYY-MM-DD format with year
        year = f"2026-{date_str[:2]}-{date_str[2:]}" if len(date_str) == 4 else date_str
        candidates += list(ROOT.glob(f"assets/{year}负荷信息预测.xls"))
        src = candidates[0] if candidates else None
        if not src:
            raise FileNotFoundError(f"No prediction file found for {date_str}")

    # Read data
    data_rows = _read_actual(src) if is_actual else _read_prediction(src)

    # Copy template
    wb = openpyxl.load_workbook(TEMPLATE)
    ws = wb["Sheet1"]

    # Write data rows 3-6, cols B-CS (2-97)
    for row_idx, values in enumerate(data_rows, start=3):
        for col_idx, val in enumerate(values, start=2):
            ws.cell(row=row_idx, column=col_idx, value=val)

    # Write formulas
    _write_formulas(ws)

    out_path.parent.mkdir(exist_ok=True)
    wb.save(out_path)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    date_str = sys.argv[1]
    is_actual = len(sys.argv) > 2 and sys.argv[2] == "actual"
    src = None

    if is_actual:
        if len(sys.argv) > 3:
            src = sys.argv[3]
    else:
        if len(sys.argv) > 2:
            src = sys.argv[2]

    generate(date_str, src, is_actual)