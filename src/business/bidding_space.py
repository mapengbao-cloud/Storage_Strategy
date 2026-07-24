"""Bidding space calculation.

Bidding space = 直调负荷 - 联络线受电 - 风电总加 - 光伏总加 - 核电总加 - 自备机组

注：local_power（地方电厂发电总加）不属竞价空间，预留用于分布式光伏=全网负荷-直调-地方电厂。
This is the residual load after subtracting tie-line imports, wind, solar,
nuclear, and self-supply units from total dispatched load. It represents
the net load that thermal/fossil generators must serve and is the key driver
of electricity prices in the Shandong spot market.

Extracted from:
- 01 biddingSpace_analysis/generate.py (_write_formulas)  [4-sheet Excel path, nuclear/local/self=0]
- 06 DataMining/extract_prices.py (manual Row7 computation)
"""

from src.data.models import BiddingSpaceData, TimeSeries96, N_POINTS


def compute_bidding_space(
    dispatched_load: list[float],
    tie_line_load: list[float],
    wind_power: list[float],
    solar_power: list[float],
    nuclear_power: list[float] | None = None,
    self_power: list[float] | None = None,
    local_power: list[float] | None = None,
) -> list[float]:
    """Compute 96-point bidding space from component series.

    bidding_space[i] = dispatched_load[i] - tie_line_load[i]
                      - wind_power[i] - solar_power[i]
                      - nuclear_power[i] - self_power[i]

    注：local_power（地方电厂发电总加）不参与竞价空间计算，仅作为参数保留以备
    分布式光伏推导（分布式光伏=全网负荷-直调-地方电厂）。本函数即使传入 local_power
    也忽略它，确保 bs 严格按 5 项计算。

    Args:
        dispatched_load: 96 values, 直调负荷 (MW).
        tie_line_load: 96 values, 联络线受电 (MW).
        wind_power: 96 values, 风电总加 (MW).
        solar_power: 96 values, 光伏总加 (MW).
        nuclear_power: 96 values, 核电总加 (MW). Optional, default 0 (Excel path).
        self_power: 96 values, 自备机组 (MW). Optional, default 0 (Excel path).
        local_power: 96 values, 地方电厂发电总加 (MW). 不参与bs，预留参数(默认None).

    Returns:
        96 bidding space values (MW).
    """
    # Optional terms default to zero (back-compat for 4-sheet Excel path)
    nuc = [0.0] * N_POINTS if nuclear_power is None else nuclear_power
    slf = [0.0] * N_POINTS if self_power is None else self_power
    # local_power 不参与 bs（即使传入也忽略）

    result = []
    for i in range(N_POINTS):
        val = (
            dispatched_load[i]
            - tie_line_load[i]
            - wind_power[i]
            - solar_power[i]
            - nuc[i]
            - slf[i]
        )
        result.append(val)
    return result


def from_data_rows(rows: list[list[float]], date_str: str = "") -> BiddingSpaceData:
    """Create BiddingSpaceData from 4 rows of 96 values each (Excel 4-sheet path).

    Args:
        rows: [dispatched_load, tie_line_load, wind_power, solar_power]
            Each inner list has 96 float values. nuclear/local/self default to 0.
        date_str: Optional date string.

    Returns:
        BiddingSpaceData with bidding_space computed.
    """
    if len(rows) != 4:
        raise ValueError(f"Expected 4 rows, got {len(rows)}")

    return BiddingSpaceData(
        date_str=date_str,
        dispatched_load=TimeSeries96(date_str=date_str, values=rows[0]),
        tie_line_load=TimeSeries96(date_str=date_str, values=rows[1]),
        wind_power=TimeSeries96(date_str=date_str, values=rows[2]),
        solar_power=TimeSeries96(date_str=date_str, values=rows[3]),
    )


def find_peak_valley_window(
    values: list[float],
    window_points: int = 8,  # 2 hours = 8 × 15min
) -> tuple[float, float, int, int]:
    """Find peak and valley 2h sliding windows in a 96-point series.

    Used by the strategy engine to identify the highest and lowest
    2-hour average periods in the bidding space curve.

    Args:
        values: 96-point series.
        window_points: Sliding window size in data points (default 8 = 2h).

    Returns:
        (peak_avg, valley_avg, peak_start_idx, valley_start_idx)
        where indices are 0-based start positions of the windows.
    """
    max_avg = float("-inf")
    min_avg = float("inf")
    max_idx = 0
    min_idx = 0

    for i in range(len(values) - window_points + 1):
        window = values[i:i + window_points]
        avg = sum(window) / window_points
        if avg > max_avg:
            max_avg = avg
            max_idx = i
        if avg < min_avg:
            min_avg = avg
            min_idx = i

    return max_avg, min_avg, max_idx, min_idx