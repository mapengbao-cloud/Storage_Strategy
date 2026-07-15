"""DA-RT price deviation risk calculator.

Quantifies the risk of real-time settlement prices deviating from
day-ahead clearing prices, which is the key financial risk for
energy storage stations that must declare DA schedules but settle at RT.

Core risk mechanism:
- DA declares charge at low price → RT price is higher → charge cost > expected
- DA declares discharge at high price → RT price is lower → discharge income < expected
- Weather (cloud cover, radiation) is the primary driver of DA-RT deviation

Usage:
    from src.business.risk import RiskCalculator, assess_daily_risk

    calc = RiskCalculator()
    assessment = calc.assess_risk(
        date_str='2026-06-05',
        weather_data=weather_dict,
        da_prices=da_96,
        charge_indices=[32..47],
        discharge_indices=[60..75],
    )
    print(f"Risk: {assessment.risk_level}, Score: {assessment.risk_score}")
    print(f"Power factor: {assessment.power_factor}")
    print(f"Recommendation: {assessment.recommendation}")
"""

import math
from dataclasses import dataclass, field
from typing import Optional

from src.data.models import (
    WeatherRiskProfile, PriceDeviation, DaRtDeviationStats,
    RiskAssessment, TimeSeries96, N_POINTS,
)
from src.config import get_parameters


# ── Weather Risk Classification ──────────────────────────────────

def classify_weather_risk(weather: dict | WeatherRiskProfile | None) -> tuple[str, float]:
    """Classify weather risk using SOLAR RADIATION as the primary indicator.

    Radiation (irradiance, W/m²) is the direct driver of photovoltaic output
    and therefore the key factor in DA-RT price deviation for midday-valley
    trading strategies:

    - High radiation (>800 W/m²) → strong PV → deep midday valley → stable
    - Medium radiation (400-800) → moderate PV → shallow valley → some risk
    - Low radiation (<200) → weak/no PV → no valley or shallow → high risk
    - Variable radiation → PV output fluctuates → RT prices unpredictable

    Cloud cover is unreliable (model forecasts are often wrong about cloud
    placement). Radiation is a more direct and physically meaningful metric
    since it directly determines PV generation at the panel level.

    Args:
        weather: Weather data dict or WeatherRiskProfile, or None.

    Returns:
        (risk_category, risk_score) where categories are:
        strong_radiation / moderate_radiation / weak_radiation / no_radiation,
        and score is 0-100.
    """
    if weather is None:
        return "unknown", 50.0

    params = _get_risk_params()

    if isinstance(weather, WeatherRiskProfile):
        radiation = weather.radiation_max or 0
        rad_var = weather.radiation_variability or 0
    elif isinstance(weather, dict):
        radiation = weather.get("radiation_max", 0) or 0
        rad_var = weather.get("radiation_variability", 0) or 0
    else:
        return "unknown", 50.0

    if radiation is None or radiation == 0:
        # Try to estimate from cloud as fallback only
        cloud = None
        if isinstance(weather, WeatherRiskProfile):
            cloud = weather.cloud_cover_avg
        elif isinstance(weather, dict):
            cloud = weather.get("cloud_cover_avg")
        if cloud is not None and cloud > 0:
            radiation = max(0, (100 - cloud) * 10)  # rough estimate
        else:
            return "unknown", 50.0

    strong_threshold = params["weather_risk"]["strong_radiation_threshold"]
    moderate_threshold = params["weather_risk"]["moderate_radiation_threshold"]
    weak_threshold = params["weather_risk"]["weak_radiation_threshold"]
    rad_var_threshold = params["weather_risk"]["radiation_variability_threshold"]

    # ── Radiation-based classification ──
    if radiation > strong_threshold:
        # Strong radiation → deep PV valley → DA/RT prices converge → LOW risk
        category = "strong_radiation"
        base_score = 5.0
    elif radiation > moderate_threshold:
        # Moderate radiation → PV valley exists but shallower → MEDIUM risk
        category = "moderate_radiation"
        base_score = 30.0
    elif radiation > weak_threshold:
        # Weak radiation → little PV → valley may not materialize → HIGH risk
        category = "weak_radiation"
        base_score = 60.0
    else:
        # Very low radiation → almost no PV → valley absent → EXTREME risk
        category = "no_radiation"
        base_score = 85.0

    # ── Variability penalty ──
    # High radiation variability = PV output fluctuating within the day
    # This directly causes RT price jumping → add score proportional to variability
    variability_penalty = 0.0
    if rad_var_threshold and rad_var_threshold > 0:
        # rad_var is W/m² std dev. Typical: 0-50=stable, 50-200=moderate, >300=highly variable
        variability_penalty = min(30, (rad_var / rad_var_threshold) * 15)

    # ── Final score ──
    score = min(100, base_score + variability_penalty)

    # ── Determine risk level label ──
    if score < 25:
        level_label = "low"
    elif score < 45:
        level_label = "medium"
    elif score < params.get("max_risk_score_trade", 60):
        level_label = "high"
    else:
        level_label = "extreme"

    # Append variability info to category
    if variability_penalty > 5:
        category = f"{category}_variable"
        score = min(100, score)

    return category, min(100, score)


# ── Deviation Statistics ─────────────────────────────────────────

def compute_deviation_stats(
    deviations: list[PriceDeviation],
    weather_category: str | None = None,
) -> DaRtDeviationStats:
    """Compute aggregate DA-RT deviation statistics from historical records.

    Args:
        deviations: List of PriceDeviation records (one per historical date).
        weather_category: If set, filter to only this weather category.

    Returns:
        DaRtDeviationStats with per-point mean/std/percentiles.
    """
    if weather_category:
        filtered = [
            d for d in deviations
            if d.weather and d.weather.risk_category == weather_category
        ]
        if len(filtered) >= _get_risk_params()["min_similar_weather_days"]:
            deviations = filtered

    if not deviations:
        return DaRtDeviationStats()

    n = len(deviations)
    dates = [d.date_str for d in deviations]

    # Per-point statistics
    per_point_mean = [0.0] * N_POINTS
    per_point_std = [0.0] * N_POINTS
    per_point_p5 = [0.0] * N_POINTS
    per_point_p95 = [0.0] * N_POINTS

    for i in range(N_POINTS):
        point_devs = []
        for d in deviations:
            if i < len(d.deviations):
                point_devs.append(d.deviations[i])

        if point_devs:
            mean = sum(point_devs) / len(point_devs)
            per_point_mean[i] = mean

            if len(point_devs) > 1:
                variance = sum((x - mean) ** 2 for x in point_devs) / (len(point_devs) - 1)
                per_point_std[i] = math.sqrt(variance)

            sorted_devs = sorted(point_devs)
            p5_idx = max(0, int(len(sorted_devs) * 0.05))
            p95_idx = min(len(sorted_devs) - 1, int(len(sorted_devs) * 0.95))
            per_point_p5[i] = sorted_devs[p5_idx]
            per_point_p95[i] = sorted_devs[p95_idx]

    # Overall aggregates
    all_abs = [abs(d) for d in per_point_mean]
    overall_mean_abs = sum(all_abs) / N_POINTS if all_abs else 0.0
    overall_rms = (sum(d**2 for d in per_point_mean) / N_POINTS) ** 0.5 if per_point_mean else 0.0

    return DaRtDeviationStats(
        dates_covered=dates,
        per_point_mean=per_point_mean,
        per_point_std=per_point_std,
        per_point_p5=per_point_p5,
        per_point_p95=per_point_p95,
        overall_mean_abs_dev=overall_mean_abs,
        overall_rms_dev=overall_rms,
    )


# ── Risk Assessment ──────────────────────────────────────────────

class RiskCalculator:
    """Compute DA-RT deviation risk for a single trading day.

    Combines three risk components:
    1. Weather risk — cloud cover / radiation → classification
    2. Historical deviation risk — how much did RT deviate from DA on similar days?
    3. Bidding space forecast error risk — how uncertain is the BS forecast?
    """

    def __init__(self, historical_deviations: list[PriceDeviation] | None = None):
        """
        Args:
            historical_deviations: Pre-loaded historical deviation records.
                If None, assessment will use weather-only risk.
        """
        self._history = historical_deviations or []
        self._stats_cache: dict[str, DaRtDeviationStats] = {}

    def assess_risk(
        self,
        date_str: str = "",
        weather_data: dict | WeatherRiskProfile | None = None,
        da_prices: list[float] | None = None,
        da_revenue: float = 0.0,
        charge_indices: list[int] | None = None,
        discharge_indices: list[int] | None = None,
        bidding_space_forecast: list[float] | None = None,
        bidding_space_actual: list[float] | None = None,
    ) -> RiskAssessment:
        """Full risk assessment for one trading day.

        Args:
            date_str: ISO date string.
            weather_data: Weather forecast or actual data.
            da_prices: 96-point DA clearing prices.
            da_revenue: DA-expected net revenue (yuan).
            charge_indices: Indices of charging periods (0-95).
            discharge_indices: Indices of discharging periods (0-95).
            bidding_space_forecast: DA-forecast bidding space (96 points).
            bidding_space_actual: Actual bidding space if available (96 points).

        Returns:
            RiskAssessment with risk level, score, revenue band, and recommendations.
        """
        params = _get_risk_params()
        weights = params["risk_weights"]

        # ── 1. Weather risk ──
        weather_cat, weather_score = classify_weather_risk(weather_data)

        # ── 2. Historical deviation risk ──
        hist_score = 50.0
        similar_days = 0
        similar_avg_dev = 0.0

        if self._history and weather_cat != "unknown":
            # Filter deviations by weather category
            matching = [
                d for d in self._history
                if d.weather and d.weather.risk_category == weather_cat
            ]
            if len(matching) >= params["min_similar_weather_days"]:
                stats = compute_deviation_stats(matching)
                similar_days = len(matching)

                # Score based on RMS deviation relative to threshold
                max_dev = params["max_acceptable_deviation_charge"]
                if max_dev > 0:
                    hist_score = min(100, (stats.overall_rms_dev / max_dev) * 60)
                similar_avg_dev = stats.overall_mean_abs_dev

                # Cache stats
                self._stats_cache[weather_cat] = stats
            else:
                # Not enough similar days — use overall stats
                stats = compute_deviation_stats(self._history)
                if stats.n_days > 0:
                    max_dev = params["max_acceptable_deviation_charge"]
                    if max_dev > 0:
                        hist_score = min(100, (stats.overall_rms_dev / max_dev) * 60)
                    similar_avg_dev = stats.overall_mean_abs_dev

        # ── 3. Bidding space forecast error risk ──
        bs_score = 50.0
        if bidding_space_forecast and bidding_space_actual:
            bs_score = _compute_bs_error_score(
                bidding_space_forecast, bidding_space_actual
            )

        # ── Composite risk score ──
        risk_score = (
            weights["weather"] * weather_score
            + weights["historical_deviation"] * hist_score
            + weights["bidding_space_error"] * bs_score
        )

        # ── Risk level ──
        if risk_score < 25:
            risk_level = "low"
        elif risk_score < 45:
            risk_level = "medium"
        elif risk_score < params["max_risk_score_trade"]:
            risk_level = "high"
        else:
            risk_level = "extreme"

        # ── Revenue estimates under different RT scenarios ──
        rt_best, rt_expected, rt_worst = _estimate_rt_revenue(
            da_revenue,
            da_prices,
            self._history,
            weather_cat,
            charge_indices or [],
            discharge_indices or [],
        )

        # ── Loss probability ──
        loss_prob = _estimate_loss_probability(
            da_revenue,
            self._history,
            weather_cat,
            charge_indices or [],
            discharge_indices or [],
        )

        # ── Operational recommendations ──
        ops = params["operation_by_risk"].get(risk_level, params["operation_by_risk"]["low"])
        power_factor = ops["power_factor"]
        charge_time_factor = ops["charge_time_factor"]
        recommendation = ops["description"]

        # Identify high-risk hours
        risk_hours = _identify_risk_hours(
            da_prices, charge_indices or [], discharge_indices or [],
            self._history, weather_cat,
        )

        return RiskAssessment(
            date_str=date_str,
            risk_level=risk_level,
            risk_score=risk_score,
            weather_risk=weather_score,
            historical_deviation_risk=hist_score,
            bidding_space_risk=bs_score,
            da_revenue_expected=da_revenue,
            rt_revenue_best=rt_best,
            rt_revenue_expected=rt_expected,
            rt_revenue_worst=rt_worst,
            loss_probability=loss_prob,
            power_factor=power_factor,
            charge_time_factor=charge_time_factor,
            risk_hours=risk_hours,
            recommendation=recommendation,
            weather_category=weather_cat,
            similar_days_count=similar_days,
            similar_days_avg_dev=similar_avg_dev,
        )

    def assess_risk_simple(
        self,
        date_str: str = "",
        weather_data: dict | None = None,
        da_revenue: float = 0.0,
    ) -> RiskAssessment:
        """Quick risk assessment with weather data only (no historical DB).

        Useful when historical deviation data is not yet available.
        """
        return self.assess_risk(
            date_str=date_str,
            weather_data=weather_data,
            da_revenue=da_revenue,
        )


# ── Convenience function ─────────────────────────────────────────

def assess_daily_risk(
    date_str: str = "",
    weather_data: dict | WeatherRiskProfile | None = None,
    da_prices: list[float] | None = None,
    da_revenue: float = 0.0,
    charge_indices: list[int] | None = None,
    discharge_indices: list[int] | None = None,
    historical_deviations: list[PriceDeviation] | None = None,
) -> RiskAssessment:
    """One-line risk assessment for a single trading day.

    Args:
        date_str: Date string.
        weather_data: Weather forecast/actual data.
        da_prices: 96-point DA prices.
        da_revenue: Expected net revenue from DA.
        charge_indices: Charging period indices.
        discharge_indices: Discharging period indices.
        historical_deviations: Pre-loaded deviation history.

    Returns:
        RiskAssessment with risk level, score, and recommendations.
    """
    calc = RiskCalculator(historical_deviations)
    return calc.assess_risk(
        date_str=date_str,
        weather_data=weather_data,
        da_prices=da_prices,
        da_revenue=da_revenue,
        charge_indices=charge_indices,
        discharge_indices=discharge_indices,
    )


# ── Internal helpers ─────────────────────────────────────────────

def _get_risk_params() -> dict:
    """Get risk parameters from config."""
    return get_parameters()["strategy"]["risk"]


def _compute_bs_error_score(
    forecast: list[float], actual: list[float]
) -> float:
    """Compute bidding space forecast error risk score (0-100).

    Uses RMSE of forecast vs actual, normalized by typical BS values.
    """
    if not forecast or not actual:
        return 50.0

    n = min(len(forecast), len(actual))
    if n == 0:
        return 50.0

    errors = [forecast[i] - actual[i] for i in range(n)]
    rmse = (sum(e**2 for e in errors) / n) ** 0.5

    # Normalize: typical BS ~ 30000 MW, RMSE < 1000 = low risk
    if rmse < 500:
        return 10.0
    elif rmse < 1000:
        return 25.0
    elif rmse < 2000:
        return 40.0
    elif rmse < 4000:
        return 60.0
    elif rmse < 8000:
        return 80.0
    else:
        return 95.0


def _estimate_rt_revenue(
    da_revenue: float,
    da_prices: list[float] | None,
    history: list[PriceDeviation],
    weather_category: str,
    charge_indices: list[int],
    discharge_indices: list[int],
) -> tuple[float, float, float]:
    """Estimate RT revenue under best/expected/worst RT price scenarios.

    Returns:
        (rt_best, rt_expected, rt_worst) in yuan.
    """
    if not history or not da_prices:
        return da_revenue, da_revenue, da_revenue

    # Get deviation stats for this weather category
    if weather_category != "unknown":
        matching = [d for d in history
                    if d.weather and d.weather.risk_category == weather_category]
    else:
        matching = history

    if not matching:
        return da_revenue, da_revenue, da_revenue

    stats = compute_deviation_stats(matching)

    # Estimate impact on charge/discharge periods
    charge_impact = 0.0
    discharge_impact = 0.0

    # Charge impact: positive deviation = cost increase
    if charge_indices:
        charge_mean_devs = [stats.per_point_mean[i] for i in charge_indices if i < 96]
        charge_std_devs = [stats.per_point_std[i] for i in charge_indices if i < 96]
        if charge_mean_devs:
            # Expected: mean deviation → cost increase
            charge_impact = sum(charge_mean_devs) / len(charge_mean_devs)

    # Discharge impact: negative deviation = revenue decrease
    if discharge_indices:
        discharge_mean_devs = [stats.per_point_mean[i] for i in discharge_indices if i < 96]
        discharge_std_devs = [stats.per_point_std[i] for i in discharge_indices if i < 96]
        if discharge_mean_devs:
            discharge_impact = sum(discharge_mean_devs) / len(discharge_mean_devs)

    # Approximate: revenue impact = -(charge_impact) + discharge_impact
    # charge_impact > 0 → cost increase → revenue decrease
    # discharge_impact < 0 → revenue decrease
    total_impact = -charge_impact + discharge_impact

    # Scale: assume ~180 MWh charge, ~160 MWh discharge per day
    # This is approximate — actual volumes should be passed in
    avg_charge_vol = 180.0
    avg_discharge_vol = 160.0

    rt_expected = da_revenue - abs(charge_impact) * avg_charge_vol * 0.5 + discharge_impact * avg_discharge_vol * 0.5

    # Worst case: 2 sigma adverse deviation
    charge_2sigma = sum(
        abs(stats.per_point_p95[i])
        for i in charge_indices if i < 96
    ) / max(len(charge_indices), 1) if charge_indices else 0

    discharge_2sigma = sum(
        abs(stats.per_point_p5[i])
        for i in discharge_indices if i < 96
    ) / max(len(discharge_indices), 1) if discharge_indices else 0

    rt_worst = da_revenue - charge_2sigma * avg_charge_vol - discharge_2sigma * avg_discharge_vol

    # Best case: favorable deviation
    rt_best = da_revenue + abs(charge_impact) * avg_charge_vol * 0.3 + abs(discharge_impact) * avg_discharge_vol * 0.3

    return rt_best, rt_expected, rt_worst


def _estimate_loss_probability(
    da_revenue: float,
    history: list[PriceDeviation],
    weather_category: str,
    charge_indices: list[int],
    discharge_indices: list[int],
) -> float:
    """Estimate probability that net RT revenue < 0."""
    if not history:
        return 0.0

    if weather_category != "unknown":
        matching = [d for d in history
                    if d.weather and d.weather.risk_category == weather_category]
    else:
        matching = history

    if not matching:
        return 0.0

    # Count how many similar days had worse-than-expected outcomes
    # Simple heuristic: if deviation RMS > 50 → higher loss probability
    stats = compute_deviation_stats(matching)
    rms = stats.overall_rms_dev

    if rms < 20:
        return 0.05
    elif rms < 40:
        return 0.10
    elif rms < 60:
        return 0.20
    elif rms < 100:
        return 0.35
    else:
        return 0.50


def _identify_risk_hours(
    da_prices: list[float] | None,
    charge_indices: list[int],
    discharge_indices: list[int],
    history: list[PriceDeviation],
    weather_category: str,
) -> list[tuple[int, int]]:
    """Identify high-risk time periods where DA-RT deviation is historically large.

    Returns list of (start_idx, end_idx) for continuous high-risk blocks.
    """
    if not da_prices or not history:
        return []

    if weather_category != "unknown":
        matching = [d for d in history
                    if d.weather and d.weather.risk_category == weather_category]
    else:
        matching = history

    if not matching:
        return []

    stats = compute_deviation_stats(matching)
    threshold = _get_risk_params()["max_acceptable_deviation_charge"]

    # Find continuous blocks where abs deviation > threshold
    high_risk = [i for i in range(N_POINTS)
                 if abs(stats.per_point_mean[i]) > threshold]

    if not high_risk:
        return []

    # Group into contiguous blocks
    blocks = []
    start = high_risk[0]
    prev = high_risk[0]

    for idx in high_risk[1:]:
        if idx == prev + 1:
            prev = idx
        else:
            blocks.append((start, prev))
            start = idx
            prev = idx
    blocks.append((start, prev))

    return blocks