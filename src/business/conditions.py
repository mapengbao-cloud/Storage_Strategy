"""Pluggable strategy conditions — each condition is a callable that returns
a (passed: bool, reason: str) tuple.

This allows adding/removing/modifying strategy conditions without changing
the core strategy engine. New revenue types (中长期, 爬坡, 调频) can add
their own conditions as plugins.

Usage:
    from src.business.conditions import (
        ConditionContext, bidding_space_condition, price_spread_condition,
        ALL_CONDITIONS, evaluate_all
    )

    ctx = ConditionContext(bidding_space=bs, day_ahead_price=price)
    results = evaluate_all(ctx)  # -> list of (condition_name, passed, reason)
"""

from dataclasses import dataclass, field
from typing import Callable, Protocol
from src.data.models import BiddingSpaceData, TimeSeries96
from src.business.bidding_space import find_peak_valley_window
from src.config import get_parameters
from src.utils.date_utils import time_label_to_hours


# ── Condition Context ────────────────────────────────────────────

@dataclass
class ConditionContext:
    """All data available to strategy conditions.

    Add new fields as new data sources become available (e.g.,
    weather_data, fm_price, mlt_contracts, ramp_signal, etc.).
    """
    date_str: str = ""
    bidding_space: BiddingSpaceData | None = None
    day_ahead_price: TimeSeries96 | None = None
    real_time_price: TimeSeries96 | None = None

    # Future data sources
    weather_data: dict | None = None       # from weather.py
    fm_price: TimeSeries96 | None = None   # 调频市场价格
    mlt_contract: dict | None = None       # 中长期合约
    ramp_signal: dict | None = None        # 爬坡产品信号


# ── Condition Result ──────────────────────────────────────────────

@dataclass
class ConditionResult:
    """Single condition evaluation result."""
    name: str
    description: str
    passed: bool
    reason: str
    details: dict = field(default_factory=dict)  # e.g. {'diff_mw': 23800, 'threshold': 23000}


# ── Condition Type ────────────────────────────────────────────────

ConditionFunc = Callable[[ConditionContext], ConditionResult]


# ── Built-in Conditions ──────────────────────────────────────────

def bidding_space_peak_valley_condition(ctx: ConditionContext) -> ConditionResult:
    """Condition 1a: 竞价空间 2h sliding window peak-valley difference.

    Checks if peak-valley difference >= threshold (default 23,000 MW).
    """
    params = get_parameters()["strategy"]["bidding_space"]
    threshold = params["peak_valley_diff_threshold_mw"]
    window_points = params["sliding_window_hours"] * 4

    if ctx.bidding_space is None or ctx.bidding_space.bidding_space is None:
        return ConditionResult(
            name="bidding_space_peak_valley",
            description="竞价空间 2h 峰谷差",
            passed=False,
            reason="无竞价空间数据",
        )

    bs_values = ctx.bidding_space.bidding_space.values
    peak_avg, valley_avg, peak_idx, valley_idx = find_peak_valley_window(
        bs_values, window_points
    )
    diff = peak_avg - valley_avg
    passed = diff >= threshold

    return ConditionResult(
        name="bidding_space_peak_valley",
        description=f"竞价空间 2h 峰谷差 >= {threshold:,} MW",
        passed=passed,
        reason=(
            f"峰谷差 {diff:,.0f} MW {'>=' if passed else '<'} {threshold:,} MW"
        ),
        details={
            "diff_mw": round(diff, 0),
            "threshold_mw": threshold,
            "peak_avg_mw": round(peak_avg, 0),
            "valley_avg_mw": round(valley_avg, 0),
            "peak_idx": peak_idx,
            "valley_idx": valley_idx,
        },
    )


def midday_valley_condition(ctx: ConditionContext) -> ConditionResult:
    """Condition 1b: Valley period must be in midday window (08:45-14:00).

    This ensures the valley is photovoltaic-driven (midday solar surplus),
    which has predictable real-time price behavior.
    """
    params = get_parameters()["strategy"]["bidding_space"]
    valley_start = params["valley_window_start"]
    valley_end = params["valley_window_end"]
    window_points = params["sliding_window_hours"] * 4

    if ctx.bidding_space is None or ctx.bidding_space.bidding_space is None:
        return ConditionResult(
            name="midday_valley",
            description=f"谷值在午间 ({valley_start}-{valley_end})",
            passed=False,
            reason="无竞价空间数据",
        )

    bs_values = ctx.bidding_space.bidding_space.values
    _, _, _, valley_idx = find_peak_valley_window(bs_values, window_points)
    valley_hour = valley_idx / 4.0
    valley_start_hour = time_label_to_hours(valley_start)
    valley_end_hour = time_label_to_hours(valley_end)
    is_midday = valley_start_hour <= valley_hour <= valley_end_hour

    valley_start_time = f"{valley_idx // 4:02d}:{(valley_idx % 4) * 15:02d}"
    valley_end_time = (
        f"{(valley_idx + window_points - 1) // 4:02d}:"
        f"{((valley_idx + window_points - 1) % 4) * 15:02d}"
    )

    return ConditionResult(
        name="midday_valley",
        description=f"谷值在午间 ({valley_start}-{valley_end})",
        passed=is_midday,
        reason=(
            f"谷值时段 {valley_start_time}-{valley_end_time}"
            f" ({'在' if is_midday else '不在'}"
            f" {valley_start}-{valley_end})"
        ),
        details={
            "valley_hour": valley_hour,
            "valley_window": f"{valley_start_time}-{valley_end_time}",
            "midday_window": f"{valley_start}-{valley_end}",
        },
    )


def price_spread_condition(ctx: ConditionContext) -> ConditionResult:
    """Condition 2: Day-ahead price spread >= threshold (default 200 yuan/MWh).

    Uses max - min of the 96-point day-ahead clearing price.
    """
    params = get_parameters()["strategy"]["price_spread"]
    threshold = params["day_ahead_spread_threshold"]

    if ctx.day_ahead_price is None:
        return ConditionResult(
            name="price_spread",
            description=f"日前价差 >= {threshold} 元/MWh",
            passed=False,
            reason="无日前电价数据",
        )

    prices = ctx.day_ahead_price.values
    valid_prices = [p for p in prices if p is not None]

    if not valid_prices:
        return ConditionResult(
            name="price_spread",
            description=f"日前价差 >= {threshold} 元/MWh",
            passed=False,
            reason="日前电价数据为空",
        )

    price_spread = max(valid_prices) - min(valid_prices)
    passed = price_spread >= threshold

    return ConditionResult(
        name="price_spread",
        description=f"日前价差 >= {threshold} 元/MWh",
        passed=passed,
        reason=(
            f"日前价差 {price_spread:,.0f}"
            f" {'>=' if passed else '<'} {threshold} 元/MWh"
        ),
        details={
            "spread": round(price_spread, 2),
            "threshold": threshold,
            "max_price": round(max(valid_prices), 2),
            "min_price": round(min(valid_prices), 2),
        },
    )


# ── Future Conditions (disabled by default) ──────────────────────

def fm_price_condition(ctx: ConditionContext) -> ConditionResult:
    """Future: 调频价格条件 — requires fm_price data.

    Placeholder until 润津 starts participating in FM market.
    """
    if ctx.fm_price is None:
        return ConditionResult(
            name="fm_price",
            description="调频价格条件（预留）",
            passed=True,  # Skip — not applicable yet
            reason="调频市场未参与，跳过",
        )
    # Future implementation: check FM spread vs threshold
    return ConditionResult(
        name="fm_price",
        description="调频价格条件",
        passed=True,
        reason="调频数据可用，待实现具体条件",
    )


def mlt_position_condition(ctx: ConditionContext) -> ConditionResult:
    """Future: 中长期仓位条件 — requires mlt_contract data.

    Placeholder until 润津 enters medium/long-term contracts.
    """
    if ctx.mlt_contract is None:
        return ConditionResult(
            name="mlt_position",
            description="中长期仓位条件（预留）",
            passed=True,  # Skip — not applicable yet
            reason="中长期合约未签订，跳过",
        )
    # Future implementation
    return ConditionResult(
        name="mlt_position",
        description="中长期仓位条件",
        passed=True,
        reason="中长期合约数据可用，待实现具体条件",
    )


# ── Risk Conditions ──────────────────────────────────────────────

def weather_risk_condition(ctx: ConditionContext) -> ConditionResult:
    """Condition: Weather-driven DA-RT deviation risk assessment.

    Checks if weather conditions (cloud cover, radiation) indicate
    acceptable DA-RT price deviation risk. High cloud cover or
    radiation variability = higher risk of RT price divergence.

    Requires: ctx.weather_data (dict with cloud_cover_avg, radiation_max, etc.)
    Gracefully passes if weather data is unavailable.
    """
    from src.business.risk import classify_weather_risk
    from src.config import get_parameters
    risk_params = get_parameters()["strategy"].get("risk", {})
    max_score = risk_params.get("max_risk_score_trade", 60)

    if ctx.weather_data is None:
        return ConditionResult(
            name="weather_risk",
            description="气象风险条件",
            passed=True,  # Graceful — no data, no block
            reason="无气象数据，跳过天气风险评估",
        )

    category, score = classify_weather_risk(ctx.weather_data)
    passed = score <= max_score

    return ConditionResult(
        name="weather_risk",
        description=f"气象风险 <= {max_score}分",
        passed=passed,
        reason=(
            f"天气: {category} (风险分 {score:.0f}/100)"
            f" {'[OK]' if passed else '[HIGH RISK]'}"
        ),
        details={
            "weather_category": category,
            "risk_score": round(score, 1),
            "max_score": max_score,
        },
    )


def da_rt_deviation_condition(ctx: ConditionContext) -> ConditionResult:
    """Condition: Historical DA-RT price deviation risk.

    Requires historical deviation data pre-loaded into the context
    or computed from database queries. Checks whether the expected
    DA-RT deviation on similar-weather days is within acceptable bounds.

    Requires: ctx.real_time_price for RT prices, or pre-computed stats.
    Gracefully passes if deviation data is unavailable.
    """
    from src.config import get_parameters
    risk_params = get_parameters()["strategy"].get("risk", {})
    max_charge_dev = risk_params.get("max_acceptable_deviation_charge", 50)
    max_discharge_dev = risk_params.get("max_acceptable_deviation_discharge", 50)

    # Check if deviation data is available in context
    deviation_data = getattr(ctx, '_deviation_stats', None)
    if deviation_data is None:
        return ConditionResult(
            name="da_rt_deviation",
            description="日前-实时电价偏差风险",
            passed=True,  # Graceful — requires pre-loaded data
            reason="无历史偏差数据，跳过DA-RT风险评估",
        )

    # Check if deviation is acceptable
    charge_risk = getattr(deviation_data, 'charge_period_risk', 0)
    discharge_risk = getattr(deviation_data, 'discharge_period_risk', 0)

    charge_ok = charge_risk <= max_charge_dev
    discharge_ok = discharge_risk <= max_discharge_dev
    passed = charge_ok and discharge_ok

    details = {
        "charge_period_risk": round(charge_risk, 1),
        "charge_threshold": max_charge_dev,
        "discharge_period_risk": round(discharge_risk, 1),
        "discharge_threshold": max_discharge_dev,
    }

    if not passed:
        reasons = []
        if not charge_ok:
            reasons.append(f"充电偏差 {charge_risk:.0f} > {max_charge_dev} 元/MWh")
        if not discharge_ok:
            reasons.append(f"放电偏差 {discharge_risk:.0f} > {max_discharge_dev} 元/MWh")
        reason = "; ".join(reasons)
    else:
        reason = (
            f"充电偏差 {charge_risk:.1f}, 放电偏差 {discharge_risk:.1f}"
            f" 均在阈值内 [OK]"
        )

    return ConditionResult(
        name="da_rt_deviation",
        description="日前-实时电价偏差风险",
        passed=passed,
        reason=reason,
        details=details,
    )


# ── Condition Registry ───────────────────────────────────────────

# Active conditions (used for daily strategy evaluation)
ACTIVE_CONDITIONS: list[ConditionFunc] = [
    bidding_space_peak_valley_condition,
    midday_valley_condition,
    price_spread_condition,
]

# Extended conditions with risk (use when weather + RT data available)
RISK_AWARE_CONDITIONS: list[ConditionFunc] = [
    bidding_space_peak_valley_condition,
    midday_valley_condition,
    price_spread_condition,
    weather_risk_condition,
    da_rt_deviation_condition,
]

# All registered conditions including future ones
ALL_CONDITIONS: dict[str, ConditionFunc] = {
    "bidding_space_peak_valley": bidding_space_peak_valley_condition,
    "midday_valley": midday_valley_condition,
    "price_spread": price_spread_condition,
    "fm_price": fm_price_condition,
    "mlt_position": mlt_position_condition,
    "weather_risk": weather_risk_condition,
    "da_rt_deviation": da_rt_deviation_condition,
}


def evaluate_all(
    ctx: ConditionContext,
    conditions: list[ConditionFunc] | None = None,
) -> list[ConditionResult]:
    """Evaluate all active conditions and return results.

    Args:
        ctx: ConditionContext with all available data.
        conditions: Specific conditions to evaluate, or None for ACTIVE_CONDITIONS.

    Returns:
        List of ConditionResult, one per condition.
    """
    if conditions is None:
        conditions = ACTIVE_CONDITIONS
    return [cond(ctx) for cond in conditions]


def should_trade(results: list[ConditionResult]) -> bool:
    """Determine if ALL conditions passed."""
    return all(r.passed for r in results)


def format_reasons(results: list[ConditionResult]) -> list[str]:
    """Format condition results into human-readable reasons list."""
    return [f"[{'OK' if r.passed else 'NO'}] {r.description}: {r.reason}" for r in results]