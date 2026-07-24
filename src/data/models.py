"""Unified data models for the entire pipeline.

All core data structures are defined here as dataclasses. This is the
single source of truth for what data flows between pipeline stages.

Key types:
- TimeSeries96: 96-point (15-min interval) time series for one day
- BiddingSpaceData: Load, wind, solar → bidding space calculation
- ChargeDischargeData: Station-level power & price curve
- DailyRevenue: The 17-value (A-Q) revenue breakdown
- StrategySignal: Trading decision output
"""

from dataclasses import dataclass, field, fields
from datetime import date
from typing import Optional

# Number of time points per day (15-minute intervals)
N_POINTS = 96
TIME_INTERVAL_HOURS = 0.25  # 15 minutes in hours


def _make_time_labels() -> list[str]:
    """Generate 96 time labels: 00:15, 00:30, ..., 24:00."""
    labels = []
    for h in range(24):
        for m in (0, 15, 30, 45):
            labels.append(f"{h:02d}:{m:02d}")
    return labels


TIME_LABELS = _make_time_labels()


# ── Core Time Series ────────────────────────────────────────────

@dataclass
class TimeSeries96:
    """96-point (15-min interval) time series data for one day.

    Attributes:
        date_str: Date string in 'YYYY-MM-DD' format.
        values: 96 float values (one per 15-min interval).
        time_labels: Optional 96 time labels. Generated if not provided.
    """
    date_str: str
    values: list[float]
    time_labels: list[str] = field(default_factory=_make_time_labels)

    def __post_init__(self):
        if len(self.values) != N_POINTS:
            raise ValueError(
                f"Expected {N_POINTS} values, got {len(self.values)}"
            )
        if not self.time_labels or len(self.time_labels) != N_POINTS:
            self.time_labels = _make_time_labels()

    def __getitem__(self, idx: int) -> float:
        return self.values[idx]

    def __iter__(self):
        return iter(self.values)

    def __len__(self) -> int:
        return N_POINTS


# ── Bidding Space ────────────────────────────────────────────────

@dataclass
class BiddingSpaceData:
    """Bidding space components for one date.

    Bidding space = 直调负荷 - 联络线受电 - 风电总加 - 光伏总加 - 核电总加 - 自备机组
    （注：local_power 地方电厂发电总加不参与bs，预留用于分布式光伏）
    """
    date_str: str
    dispatched_load: TimeSeries96      # 直调负荷 (MW)
    tie_line_load: TimeSeries96        # 联络线受电 (MW)
    wind_power: TimeSeries96           # 风电总加 (MW)
    solar_power: TimeSeries96          # 光伏总加 (MW)
    bidding_space: TimeSeries96 | None = None  # computed on init
    nuclear_power: TimeSeries96 | None = None  # 核电总加 (MW), optional (default 0)
    local_power: TimeSeries96 | None = None   # 地方电厂发电总加 (MW), 预留(分布式光伏用), 不参与bs
    self_power: TimeSeries96 | None = None     # 自备机组 (MW), optional (default 0)

    def __post_init__(self):
        if self.bidding_space is None:
            nuc = self.nuclear_power.values if self.nuclear_power else [0.0] * N_POINTS
            slf = self.self_power.values if self.self_power else [0.0] * N_POINTS
            # local_power 不参与 bs（地方电厂发电总加，预留用于分布式光伏）
            bs_values = [
                self.dispatched_load.values[i]
                - self.tie_line_load.values[i]
                - self.wind_power.values[i]
                - self.solar_power.values[i]
                - nuc[i]
                - slf[i]
                for i in range(N_POINTS)
            ]
            self.bidding_space = TimeSeries96(
                date_str=self.date_str, values=bs_values
            )


# ── Charge/Discharge & Price ────────────────────────────────────

@dataclass
class ChargeDischargeData:
    """96-point charge/discharge power and clearing price for Runjin station.

    power_mw: Negative = charging, Positive = discharging, 0 = idle.
    price: Clearing price at each time point (yuan/MWh).
    """
    date_str: str
    power_mw: TimeSeries96    # MW, neg=charge, pos=discharge
    price: TimeSeries96       # yuan/MWh, clearing price

    @property
    def charge_periods(self) -> list[int]:
        """Indices where power < 0 (charging)."""
        return [i for i, v in enumerate(self.power_mw.values) if v < 0]

    @property
    def discharge_periods(self) -> list[int]:
        """Indices where power > 0 (discharging)."""
        return [i for i, v in enumerate(self.power_mw.values) if v > 0]


# ── Revenue ──────────────────────────────────────────────────────

@dataclass
class DailyRevenue:
    """Complete revenue breakdown for one date (17 values = A through Q).

    These correspond to columns A-Q in the 充放测算 row 4,
    which are the source for the 17 columns in each section of the
    statistics table (日前/实时/日结算).

    Fields:
        A: 充电价 (yuan/MWh) — weighted avg price during charging
        B: 充电量 (MWh) — total charging energy
        C: 充电收入 (yuan) — negative = cost
        D-E: 费用 based on I12, I13
        F-G: 费用 based on efficiency * I8, I9
        H: 费用 based on I14
        I: 容量分摊 (yuan) — capacity allocation cost
        J: 容量分摊系数 — capacity allocation coefficient
        K: 总成本 (yuan) — C + D + E + F + G + H + I
        L: 放电价 (yuan/MWh) — weighted avg price during discharging
        M: 放电量 (MWh) — total discharging energy
        N: 放电收入 (yuan) — positive = income
        O: 净收益 (yuan) — N + K
        P: 综合效率 — -M / B
        Q: 价差 (yuan/MWh) — L - A
    """
    date_str: str = ""
    A: float = 0.0   # 充电价
    B: float = 0.0   # 充电量
    C: float = 0.0   # 充电收入
    D: float = 0.0   # 费用1
    E: float = 0.0   # 费用2
    F: float = 0.0   # 费用3
    G: float = 0.0   # 费用4
    H: float = 0.0   # 费用5
    I: float = 0.0   # 容量分摊
    J: float = 0.0   # 容量分摊系数
    K: float = 0.0   # 总成本
    L: float = 0.0   # 放电价
    M: float = 0.0   # 放电量
    N: float = 0.0   # 放电收入
    O: float = 0.0   # 净收益
    P: float = 0.0   # 综合效率
    Q: float = 0.0   # 价差

    # Extra values not in A-Q sequence
    O6: float = 0.0  # N + C (放电收入 + 充电收入), used in settlement column AY

    # Reserved for future revenue types
    fm_revenue: float = 0.0       # 调频收益 (future)
    mlt_revenue: float = 0.0      # 中长期交易收益 (future)
    ramp_revenue: float = 0.0     # 爬坡收益 (future)

    def to_list(self) -> list[float]:
        """Export as ordered list [A, B, C, ..., Q] for writing to Excel."""
        return [
            self.A, self.B, self.C, self.D, self.E, self.F, self.G,
            self.H, self.I, self.J, self.K, self.L, self.M, self.N,
            self.O, self.P, self.Q,
        ]

    @classmethod
    def from_list(cls, values: list[float], date_str: str = "",
                  o6: float = 0.0) -> "DailyRevenue":
        """Create from ordered list [A, B, C, ..., Q]."""
        if len(values) < 17:
            raise ValueError(f"Expected 17 values, got {len(values)}")
        return cls(
            date_str=date_str,
            A=values[0], B=values[1], C=values[2], D=values[3],
            E=values[4], F=values[5], G=values[6], H=values[7],
            I=values[8], J=values[9], K=values[10], L=values[11],
            M=values[12], N=values[13], O=values[14], P=values[15],
            Q=values[16], O6=o6,
        )

    def field_names(self) -> list[str]:
        """Return field names A through Q in order."""
        letter_names = list("ABCDEFGHIJKLMNOPQ")
        return letter_names


# ── Strategy ─────────────────────────────────────────────────────

@dataclass
class StrategySignal:
    """Trading decision for one day based on the 3-condition strategy.

    Attributes:
        date_str: Date in ISO format.
        should_trade: Whether conditions are met for trading.
        bidding_space_peak_valley_diff: MW, 2h sliding window max - min.
        valley_window_start: Start time of valley window (e.g. '08:45').
        valley_window_end: End time of valley window (e.g. '10:30').
        is_midday_valley: Whether valley is in 08:45-14:00 range.
        day_ahead_price_spread: yuan/MWh, max - min of day-ahead price.
        reasons: Human-readable list of why trade/no-trade.
    """
    date_str: str = ""
    should_trade: bool = False
    bidding_space_peak_valley_diff: float = 0.0
    valley_window_start: str = ""
    valley_window_end: str = ""
    is_midday_valley: bool = False
    day_ahead_price_spread: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "date": self.date_str,
            "should_trade": self.should_trade,
            "peak_valley_diff_mw": round(self.bidding_space_peak_valley_diff, 0),
            "valley_window": f"{self.valley_window_start}-{self.valley_window_end}",
            "is_midday_valley": self.is_midday_valley,
            "price_spread": round(self.day_ahead_price_spread, 2),
            "reasons": self.reasons,
        }


# ── Settlement ───────────────────────────────────────────────────

@dataclass
class SettlementBaseValues:
    """Raw values read from settlement sheets (充电/放电日清算费用).

    These are the base inputs to compute_settlement_values().
    """
    date_str: str = ""
    # From 充电日清算费用
    charge_price: float = 0.0      # AC29 (A4 source)
    charge_volume: float = 0.0     # -AB29 (B4 source)
    charge_revenue: float = 0.0    # -AD29 (C4 source)
    # From 放电日清算费用
    discharge_price: float = 0.0   # P101 (L4 source)
    discharge_volume: float = 0.0  # AO101 (M4 source)
    discharge_revenue: float = 0.0 # Q101 (N4 source)


# ── Pipeline ─────────────────────────────────────────────────────

@dataclass
class DateRecord:
    """Metadata for one date in the pipeline.

    Tracks which source files exist and which output files have been generated.
    """
    date_str: str   # ISO format 'YYYY-MM-DD'
    mmdd: str       # 'MMDD' format

    # Source file paths (relative to data/raw/YYYY-MM-DD/)
    has_prediction_load: bool = False
    has_actual_load: bool = False
    has_dayahead_trade: bool = False
    has_realtime_trade: bool = False
    has_charge_settlement: bool = False
    has_discharge_settlement: bool = False

    # Output status
    stage01_done: bool = False
    stage02_done: bool = False
    stage03_done: bool = False
    stage04_done: bool = False
    stage05_done: bool = False
    stage06_done: bool = False

    @property
    def iso_date(self) -> str:
        return self.date_str

    @property
    def ready_for_stage01(self) -> bool:
        return self.has_prediction_load

    @property
    def ready_for_stage02(self) -> bool:
        return self.has_dayahead_trade

    @property
    def ready_for_stage03(self) -> bool:
        return self.has_realtime_trade

    @property
    def ready_for_stage04(self) -> bool:
        return (self.has_charge_settlement
                and self.has_discharge_settlement
                and self.stage03_done)


# ── Risk Assessment ──────────────────────────────────────────────

@dataclass
class WeatherRiskProfile:
    """Weather risk profile for one date — derived from meteorological data.

    Classification is based PRIMARILY on solar radiation (irradiance).
    Cloud cover is unreliable as a risk indicator (model forecasts often
    misplace clouds), but radiation directly determines PV output.

    Used by the risk module to determine weather-driven DA-RT deviation risk.
    """
    date_str: str = ""
    cloud_cover_avg: float = 0.0        # Average cloud cover (%) — secondary
    radiation_max: float = 0.0          # Peak shortwave radiation (W/m²) — PRIMARY
    temp_avg: float = 0.0               # Average temperature (°C)
    humidity_avg: float = 0.0           # Average relative humidity (%)
    wind_speed_avg: float = 0.0         # Average wind speed (m/s)

    # Derived classification
    radiation_variability: float = 0.0  # Std dev of radiation (variability proxy)
    risk_category: str = "unknown"      # strong/moderate/weak/no_radiation [_variable]

    def __post_init__(self):
        if self.risk_category == "unknown":
            self.risk_category = self._classify()

    def _classify(self) -> str:
        """Classify weather risk based on SOLAR RADIATION."""
        rad = self.radiation_max or 0
        if rad > 800:
            return "strong_radiation"
        elif rad > 400:
            return "moderate_radiation"
        elif rad > 200:
            return "weak_radiation"
        else:
            return "no_radiation"


@dataclass
class PriceDeviation:
    """Single-day DA-RT price deviation record (96-point).

    Used for building historical deviation databases and risk profiling.
    """
    date_str: str = ""
    da_prices: list[float] = field(default_factory=list)      # 96 DA prices
    rt_prices: list[float] = field(default_factory=list)      # 96 RT prices
    deviations: list[float] = field(default_factory=list)     # RT - DA per point

    # Per-period aggregates
    charge_period_avg_dev: float = 0.0   # Avg deviation during charge hours
    discharge_period_avg_dev: float = 0.0  # Avg deviation during discharge hours
    max_positive_dev: float = 0.0        # Worst-case for charging (RT >> DA)
    max_negative_dev: float = 0.0        # Worst-case for discharging (RT << DA)

    weather: WeatherRiskProfile | None = None

    def __post_init__(self):
        if self.deviations and not self.charge_period_avg_dev:
            self._compute_aggregates()

    def _compute_aggregates(self):
        """Compute per-period deviation statistics."""
        if not self.deviations or len(self.deviations) != 96:
            return
        devs = self.deviations

        # Identify charge/discharge periods from DA prices
        # Charging: periods where DA price is in lower half → negative deviation bad
        # Discharging: periods where DA price is in upper half → positive deviation bad
        if self.da_prices and len(self.da_prices) == 96:
            median_price = sorted(self.da_prices)[48]
            charge_devs = [abs(d) for i, d in enumerate(devs)
                          if self.da_prices[i] <= median_price and d > 0]
            discharge_devs = [abs(d) for i, d in enumerate(devs)
                             if self.da_prices[i] > median_price and d < 0]
            self.charge_period_avg_dev = (
                sum(charge_devs) / len(charge_devs) if charge_devs else 0.0
            )
            self.discharge_period_avg_dev = (
                sum(discharge_devs) / len(discharge_devs) if discharge_devs else 0.0
            )

        self.max_positive_dev = max(devs) if devs else 0.0
        self.max_negative_dev = min(devs) if devs else 0.0

    @property
    def overall_abs_dev(self) -> float:
        """Mean absolute deviation across all 96 points."""
        if not self.deviations:
            return 0.0
        return sum(abs(d) for d in self.deviations) / len(self.deviations)

    @property
    def overall_rms_dev(self) -> float:
        """Root-mean-square deviation — penalizes large outliers."""
        if not self.deviations:
            return 0.0
        return (sum(d**2 for d in self.deviations) / len(self.deviations)) ** 0.5


@dataclass
class DaRtDeviationStats:
    """Aggregate DA-RT deviation statistics over multiple dates.

    Computed by RiskCalculator from a historical database of PriceDeviation
    records. Used to estimate expected RT price behavior.
    """
    dates_covered: list[str] = field(default_factory=list)

    # Per time-point statistics (96 points each)
    per_point_mean: list[float] = field(default_factory=list)
    per_point_std: list[float] = field(default_factory=list)
    per_point_p5: list[float] = field(default_factory=list)    # 5th percentile
    per_point_p95: list[float] = field(default_factory=list)   # 95th percentile

    # Overall aggregate
    overall_mean_abs_dev: float = 0.0
    overall_rms_dev: float = 0.0

    # Per weather category
    by_weather: dict[str, "DaRtDeviationStats"] = field(default_factory=dict)

    @property
    def n_days(self) -> int:
        return len(self.dates_covered)

    def get_risk_factors(self, charge_indices: list[int],
                         discharge_indices: list[int]) -> tuple[float, float]:
        """Get charge/discharge period risk factors from statistics.

        Returns:
            (charge_risk, discharge_risk) as average abs deviation in yuan/MWh.
        """
        if not self.per_point_mean:
            return 0.0, 0.0
        charge_risk = (
            sum(abs(self.per_point_mean[i]) for i in charge_indices if i < 96)
            / max(len(charge_indices), 1)
        )
        discharge_risk = (
            sum(abs(self.per_point_mean[i]) for i in discharge_indices if i < 96)
            / max(len(discharge_indices), 1)
        )
        return charge_risk, discharge_risk


@dataclass
class RiskAssessment:
    """Comprehensive risk assessment for a single trading day.

    Output of RiskCalculator.assess_risk() — combines weather risk,
    historical deviation risk, and bidding space forecast error risk
    into a single actionable recommendation.
    """
    date_str: str = ""
    risk_level: str = "unknown"       # low / medium / high / extreme
    risk_score: float = 0.0           # 0-100 composite score
    weather_risk: float = 0.0         # Weather component (0-100)
    historical_deviation_risk: float = 0.0  # Historical component (0-100)
    bidding_space_risk: float = 0.0   # Forecast error component (0-100)

    # Revenue estimates under different RT scenarios
    da_revenue_expected: float = 0.0      # DA-expected net revenue
    rt_revenue_best: float = 0.0          # Optimistic (-1 sigma deviation)
    rt_revenue_expected: float = 0.0      # Baseline (expected deviation)
    rt_revenue_worst: float = 0.0         # Pessimistic (-2 sigma ≈ 95% VaR)
    loss_probability: float = 0.0         # Estimated P(net revenue < 0)

    # Operational recommendations
    power_factor: float = 1.0             # Suggested power declaration factor
    charge_time_factor: float = 1.0       # Suggested charge duration extension
    risk_hours: list[tuple[int, int]] = field(default_factory=list)
    recommendation: str = ""

    # Risk breakdown details
    weather_category: str = ""
    similar_days_count: int = 0
    similar_days_avg_dev: float = 0.0

    def to_dict(self) -> dict:
        return {
            "date": self.date_str,
            "risk_level": self.risk_level,
            "risk_score": round(self.risk_score, 1),
            "weather_risk": round(self.weather_risk, 1),
            "historical_risk": round(self.historical_deviation_risk, 1),
            "da_revenue": round(self.da_revenue_expected, 0),
            "rt_revenue_range": (
                f"{self.rt_revenue_worst:,.0f} ~ {self.rt_revenue_best:,.0f}"
            ),
            "loss_probability": f"{self.loss_probability:.1%}",
            "power_factor": self.power_factor,
            "charge_time_factor": self.charge_time_factor,
            "weather": self.weather_category,
            "recommendation": self.recommendation,
        }