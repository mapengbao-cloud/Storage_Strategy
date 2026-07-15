"""Strategy rule engine — evaluate whether to trade on a given day.

Based on the 3-condition strategy from 06 DataMining/策略复盘结论.md:

Condition 1a: 竞价空间 2h sliding window peak-valley difference >= 23,000 MW
Condition 1b: Valley period must be in midday (08:45-14:00) — "midday valley type"
Condition 2:  Day-ahead price spread >= 200 yuan/MWh

All three conditions must be met for a trade signal.

The conditions are configurable via config/parameters.yaml.
"""

from src.data.models import StrategySignal, BiddingSpaceData, TimeSeries96
from src.business.bidding_space import find_peak_valley_window
from src.config import get_parameters
from src.utils.date_utils import time_label_to_hours, time_label_to_index


def _get_strategy_params() -> dict:
    """Get strategy parameters from config."""
    return get_parameters()["strategy"]


def evaluate_strategy(
    bidding_space: BiddingSpaceData,
    day_ahead_price: TimeSeries96,
    date_str: str = "",
) -> StrategySignal:
    """Evaluate the 3-condition strategy for a single day.

    Args:
        bidding_space: Bidding space data for the day.
        day_ahead_price: 96-point day-ahead clearing price.
        date_str: ISO date string for the signal.

    Returns:
        StrategySignal with trade decision and reasons.
    """
    params = _get_strategy_params()
    bs_params = params["bidding_space"]
    spread_params = params["price_spread"]

    threshold = bs_params["peak_valley_diff_threshold_mw"]
    valley_start = bs_params["valley_window_start"]
    valley_end = bs_params["valley_window_end"]
    spread_threshold = spread_params["day_ahead_spread_threshold"]
    window_points = bs_params["sliding_window_hours"] * 4  # 8 points = 2h

    bs_values = bidding_space.bidding_space.values
    prices = day_ahead_price.values

    # ── Condition 1a: Peak-valley difference ──
    peak_avg, valley_avg, peak_idx, valley_idx = find_peak_valley_window(
        bs_values, window_points
    )
    peak_valley_diff = peak_avg - valley_avg

    # ── Condition 1b: Midday valley check ──
    valley_hour = valley_idx / 4.0  # convert point index to decimal hours
    valley_start_hour = time_label_to_hours(valley_start)
    valley_end_hour = time_label_to_hours(valley_end)
    is_midday_valley = valley_start_hour <= valley_hour <= valley_end_hour

    # ── Condition 2: Day-ahead price spread ──
    valid_prices = [p for p in prices if p is not None]
    if valid_prices:
        price_spread = max(valid_prices) - min(valid_prices)
    else:
        price_spread = 0.0

    # ── Build reasons ──
    reasons = []
    if peak_valley_diff < threshold:
        reasons.append(
            f"竞价空间峰谷差 {peak_valley_diff:.0f} MW < {threshold} MW"
        )
    else:
        reasons.append(
            f"竞价空间峰谷差 {peak_valley_diff:.0f} MW >= {threshold} MW [OK]"
        )

    if not is_midday_valley:
        reasons.append(
            f"谷值时段 {valley_hour:.1f}h 不在 {valley_start}-{valley_end}（中午谷值型）"
        )
    else:
        reasons.append(
            f"谷值时段 {valley_hour:.1f}h 在 {valley_start}-{valley_end}（中午谷值型）[OK]"
        )

    if price_spread < spread_threshold:
        reasons.append(
            f"日前价差 {price_spread:.0f} < {spread_threshold} 元/MWh"
        )
    else:
        reasons.append(
            f"日前价差 {price_spread:.0f} >= {spread_threshold} 元/MWh [OK]"
        )

    should_trade = (
        peak_valley_diff >= threshold
        and is_midday_valley
        and price_spread >= spread_threshold
    )

    # Format valley window times
    valley_start_time = f"{valley_idx // 4:02d}:{(valley_idx % 4) * 15:02d}"
    valley_end_time = (
        f"{(valley_idx + window_points - 1) // 4:02d}:"
        f"{((valley_idx + window_points - 1) % 4) * 15:02d}"
    )

    return StrategySignal(
        date_str=date_str,
        should_trade=should_trade,
        bidding_space_peak_valley_diff=peak_valley_diff,
        valley_window_start=valley_start_time,
        valley_window_end=valley_end_time,
        is_midday_valley=is_midday_valley,
        day_ahead_price_spread=price_spread,
        reasons=reasons,
    )


def classify_bidding_space_shape(
    bidding_space: BiddingSpaceData,
) -> str:
    """Classify the bidding space shape for a given day.

    Returns one of:
        'midday_valley' — valley in 08:45-14:00, diff >= 23,000 (tradeable)
        'midday_valley_weak' — valley in midday but diff < 23,000
        'non_midday_valley' — valley not in midday (not tradeable)
    """
    params = _get_strategy_params()
    bs_params = params["bidding_space"]
    threshold = bs_params["peak_valley_diff_threshold_mw"]
    window_points = bs_params["sliding_window_hours"] * 4
    valley_start = bs_params["valley_window_start"]
    valley_end = bs_params["valley_window_end"]

    bs_values = bidding_space.bidding_space.values
    _, _, _, valley_idx = find_peak_valley_window(bs_values, window_points)

    valley_hour = valley_idx / 4.0
    valley_start_hour = time_label_to_hours(valley_start)
    valley_end_hour = time_label_to_hours(valley_end)
    is_midday = valley_start_hour <= valley_hour <= valley_end_hour

    peak_avg, valley_avg, _, _ = find_peak_valley_window(bs_values, window_points)
    diff = peak_avg - valley_avg

    if is_midday:
        if diff >= threshold:
            return "midday_valley"
        else:
            return "midday_valley_weak"
    else:
        return "non_midday_valley"