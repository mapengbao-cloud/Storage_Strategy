"""Bidding space calculation.

Bidding space = 直调负荷 - 联络线受电 - 风电总加 - 光伏总加

This is the residual load after subtracting tie-line imports, wind,
and solar from total dispatched load. It represents the net load
that thermal/fossil generators must serve and is the key driver
of electricity prices in the Shandong spot market.

Extracted from:
- 01 biddingSpace_analysis/generate.py (_write_formulas)
- 06 DataMining/extract_prices.py (manual Row7 computation)
"""

from src.data.models import BiddingSpaceData, TimeSeries96, N_POINTS


def compute_bidding_space(
    dispatched_load: list[float],
    tie_line_load: list[float],
    wind_power: list[float],
    solar_power: list[float],
) -> list[float]:
    """Compute 96-point bidding space from four component series.

    bidding_space[i] = dispatched_load[i] - tie_line_load[i]
                      - wind_power[i] - solar_power[i]

    Args:
        dispatched_load: 96 values, 直调负荷 (MW).
        tie_line_load: 96 values, 联络线受电 (MW).
        wind_power: 96 values, 风电总加 (MW).
        solar_power: 96 values, 光伏总加 (MW).

    Returns:
        96 bidding space values (MW).
    """
    result = []
    for i in range(N_POINTS):
        val = (
            dispatched_load[i]
            - tie_line_load[i]
            - wind_power[i]
            - solar_power[i]
        )
        result.append(val)
    return result


def from_data_rows(rows: list[list[float]], date_str: str = "") -> BiddingSpaceData:
    """Create BiddingSpaceData from 4 rows of 96 values each.

    Args:
        rows: [dispatched_load, tie_line_load, wind_power, solar_power]
            Each inner list has 96 float values.
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