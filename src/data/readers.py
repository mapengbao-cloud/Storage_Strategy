"""Unified file readers — read all source file formats into data models.

Formats:
- 负荷信息预测.xls → BiddingSpaceData (prediction)
- 电网运行实际信息.xlsx → BiddingSpaceData (actual)
- 发电侧交易结果查询.xls → ChargeDischargeData
- 结算单.xlsx → raw sheet data (list of lists)
- 复盘产出.xlsx → PriceData (read J column)
"""

import pandas as pd
import openpyxl
from pathlib import Path
from typing import Optional

from src.data.models import (
    TimeSeries96, BiddingSpaceData, ChargeDischargeData,
    SettlementBaseValues, N_POINTS,
)
from src.utils.numerics import safe_float


# ── Bidding Space Readers ────────────────────────────────────────

def read_prediction_load_xls(path: Path) -> BiddingSpaceData:
    """Read 4 sheets from prediction .xls (负荷信息预测).

    Each sheet is row-oriented: df.iloc[2, 1:97] yields 96 values.
    Sheet names: 直调负荷, 联络线受电负荷, 风电总加, 光伏总加
    """
    sheet_names = ["直调负荷", "联络线受电负荷", "风电总加", "光伏总加"]
    rows = []
    for sn in sheet_names:
        df = pd.read_excel(path, sheet_name=sn, header=None)
        values = [float(df.iloc[2, c]) for c in range(1, N_POINTS + 1)]
        rows.append(values)

    # Extract date from filename or use empty
    date_str = _extract_date_from_filename(path.name)

    return BiddingSpaceData(
        date_str=date_str,
        dispatched_load=TimeSeries96(date_str=date_str, values=rows[0]),
        tie_line_load=TimeSeries96(date_str=date_str, values=rows[1]),
        wind_power=TimeSeries96(date_str=date_str, values=rows[2]),
        solar_power=TimeSeries96(date_str=date_str, values=rows[3]),
    )


def read_actual_grid_xlsx(path: Path) -> BiddingSpaceData:
    """Read 负荷信息 sheet from actual grid data .xlsx.

    Column-oriented: rows 1-96, columns C-F (2-5).
    All values stored as STRINGS (e.g. "62191.80") — must convert via float().
    """
    df = pd.read_excel(path, sheet_name="负荷信息", header=None)
    col_map = [2, 3, 4, 5]  # 直调负荷, 联络线受电, 风电, 光伏
    rows = []
    for ci in col_map:
        values = [float(df.iloc[r, ci]) for r in range(1, N_POINTS + 1)]
        rows.append(values)

    date_str = _extract_date_from_filename(path.name)

    return BiddingSpaceData(
        date_str=date_str,
        dispatched_load=TimeSeries96(date_str=date_str, values=rows[0]),
        tie_line_load=TimeSeries96(date_str=date_str, values=rows[1]),
        wind_power=TimeSeries96(date_str=date_str, values=rows[2]),
        solar_power=TimeSeries96(date_str=date_str, values=rows[3]),
    )


# ── Trading Result Reader ────────────────────────────────────────

def read_trading_result_xls(path: Path) -> ChargeDischargeData:
    """Read 发电侧交易结果查询.xls (day-ahead or real-time).

    Sheet 0 only. 96 time points (rows 2-97 in template, 1-96 0-based in df).
    - col 1 (B): 出力 (power, MW) → 充放电曲线
    - col 3 (D): 电价 (price, yuan/MWh) → clearing price

    Returns:
        ChargeDischargeData with power_mw and price TimeSeries96.
    """
    df = pd.read_excel(path, header=None, sheet_name=0)

    power_values = []
    price_values = []
    for i in range(96):
        power_values.append(float(df.iloc[i + 1, 1]))
        price_values.append(float(df.iloc[i + 1, 3]))

    date_str = _extract_date_from_filename(path.name)

    return ChargeDischargeData(
        date_str=date_str,
        power_mw=TimeSeries96(date_str=date_str, values=power_values),
        price=TimeSeries96(date_str=date_str, values=price_values),
    )


# ── Settlement Reader ────────────────────────────────────────────

def read_settlement_base_values(
    charge_path: Path, discharge_path: Path
) -> SettlementBaseValues:
    """Read base settlement values from 充电/放电结算单.

    Reads the key cells from:
    - 充电结算单 日清算数据: AC29, AB29, AD29
    - 放电结算单 日清算费用: P101, AO101, Q101

    Returns:
        SettlementBaseValues dataclass.
    """
    date_str = _extract_date_from_filename(charge_path.name)

    wb_charge = openpyxl.load_workbook(charge_path, data_only=True)
    wb_discharge = openpyxl.load_workbook(discharge_path, data_only=True)

    ws_charge = wb_charge["日清算数据"]
    ws_discharge = wb_discharge["日清算费用"]

    result = SettlementBaseValues(
        date_str=date_str,
        charge_price=safe_float(ws_charge.cell(row=29, column=29).value),
        charge_volume=-safe_float(ws_charge.cell(row=29, column=28).value),
        charge_revenue=-safe_float(ws_charge.cell(row=29, column=30).value),
        discharge_price=safe_float(ws_discharge.cell(row=101, column=16).value),
        discharge_volume=safe_float(ws_discharge.cell(row=101, column=41).value),
        discharge_revenue=safe_float(ws_discharge.cell(row=101, column=17).value),
    )

    wb_charge.close()
    wb_discharge.close()
    return result


# ── Review File Reader ───────────────────────────────────────────

def read_price_from_review(path: Path) -> TimeSeries96:
    """Read price column (J, col 10) from a review workbook's 报价及预中标 sheet.

    Used by Stage 06 extract_prices.py to read 96-point prices from
    day-ahead/real-time review output files.

    Args:
        path: Path to a MMDD-*机组组合收益复盘.xlsx file.

    Returns:
        TimeSeries96 with 96 price values.
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    sn = next(s for s in wb.sheetnames if "报价" in s and "预中标" in s)
    ws = wb[sn]

    values = []
    for row in range(2, 98):  # rows 2-97
        val = ws.cell(row=row, column=10).value  # J column
        values.append(safe_float(val))

    wb.close()
    date_str = _extract_date_from_filename(path.name)
    return TimeSeries96(date_str=date_str, values=values)


def read_bidding_space_from_output(path: Path) -> TimeSeries96:
    """Read bidding space from Stage 01 output file.

    Reads rows 3-6 from Sheet1, computes bidding space = R3-R4-R5-R6.

    Args:
        path: Path to MMDD-竞价空间分析.xlsx.

    Returns:
        TimeSeries96 with 96 bidding space values.
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Sheet1"]

    rows_data = []
    for row in range(3, 7):  # rows 3-6
        row_vals = []
        for col in range(2, 98):  # B-CS (cols 2-97)
            row_vals.append(safe_float(ws.cell(row=row, column=col).value))
        rows_data.append(row_vals)

    wb.close()

    bs_values = [
        rows_data[0][i] - rows_data[1][i] - rows_data[2][i] - rows_data[3][i]
        for i in range(N_POINTS)
    ]
    date_str = _extract_date_from_filename(path.name)
    return TimeSeries96(date_str=date_str, values=bs_values)


# ── Helpers ──────────────────────────────────────────────────────

def _extract_date_from_filename(filename: str) -> str:
    """Extract ISO date from filename patterns like:
    - '0522-xxx.xlsx' → '2026-05-22'
    - '2026-05-22xxx.xls' → '2026-05-22'
    - '6052-2026-05-22xxx.xlsx' → '2026-05-22'
    """
    import re

    # Try ISO format first: YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # Try MMDD format at start of filename
    m = re.match(r"^(\d{2})(\d{2})", filename)
    if m:
        return f"2026-{m.group(1)}-{m.group(2)}"

    return ""


def find_source_file(
    date_mmdd: str, pattern: str, data_root: str = "data"
) -> Optional[Path]:
    """Find a source file in data/raw/YYYY-MM-DD/.

    Args:
        date_mmdd: MMDD date string (e.g. '0522').
        pattern: Glob pattern to match (e.g. '*日前交易结果查询*').
        data_root: Root data directory.

    Returns:
        Path to the first matching file, or None.
    """
    from src.utils.date_utils import mmdd_to_date

    d = mmdd_to_date(date_mmdd)
    date_dir = Path(data_root) / "raw" / d.isoformat()
    if not date_dir.exists():
        return None
    candidates = list(date_dir.glob(pattern))
    return candidates[0] if candidates else None