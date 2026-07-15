"""Revenue type breakdown — separate revenue streams for the energy storage station.

Current revenue sources:
- spot_arbitrage: 现货价差充放收益 (day-ahead + real-time spread arbitrage)

Future revenue sources:
- fm: 调频收益 (frequency modulation)
- mlt: 中长期交易收益 (medium/long-term contracts)
- ramp: 爬坡收益 (ramping product)
- capacity_market: 容量市场收益 (capacity market)
- ancillary: 辅助服务收益 (other ancillary services)

Usage:
    from src.business.revenue_types import RevenueBreakdown, RevenueStreams
    breakdown = RevenueBreakdown(spot_arbitrage=93206.06)
    total = breakdown.total_revenue
"""

from dataclasses import dataclass, field
from enum import Enum


class RevenueStream(Enum):
    SPOT_ARBITRAGE = "spot_arbitrage"
    FREQUENCY_MODULATION = "fm"
    MEDIUM_LONG_TERM = "mlt"
    RAMPING = "ramp"
    CAPACITY_MARKET = "capacity_market"
    ANCILLARY = "ancillary"


STREAM_LABELS: dict[RevenueStream, str] = {
    RevenueStream.SPOT_ARBITRAGE: "现货价差充放",
    RevenueStream.FREQUENCY_MODULATION: "调频收益",
    RevenueStream.MEDIUM_LONG_TERM: "中长期交易",
    RevenueStream.RAMPING: "爬坡收益",
    RevenueStream.CAPACITY_MARKET: "容量市场",
    RevenueStream.ANCILLARY: "辅助服务",
}


@dataclass
class RevenueBreakdown:
    """Breakdown of revenue by source type for a single date.

    Each field represents net revenue (yuan) for that stream.
    """
    date_str: str = ""
    spot_arbitrage: float = 0.0    # 现货价差充放收益
    fm: float = 0.0                # 调频收益
    mlt: float = 0.0               # 中长期交易收益
    ramp: float = 0.0              # 爬坡收益
    capacity_market: float = 0.0   # 容量市场收益
    ancillary: float = 0.0         # 辅助服务收益

    # Metadata
    spot_volume_charge: float = 0.0    # 现货充电量 (MWh)
    spot_volume_discharge: float = 0.0 # 现货放电量 (MWh)
    spot_spread: float = 0.0           # 现货充放价差 (yuan/MWh)

    @property
    def total_revenue(self) -> float:
        """Total revenue = sum of all streams."""
        return (
            self.spot_arbitrage
            + self.fm
            + self.mlt
            + self.ramp
            + self.capacity_market
            + self.ancillary
        )

    @property
    def active_streams(self) -> dict[str, float]:
        """Return only streams with non-zero revenue."""
        streams = {
            "spot_arbitrage": self.spot_arbitrage,
            "fm": self.fm,
            "mlt": self.mlt,
            "ramp": self.ramp,
            "capacity_market": self.capacity_market,
            "ancillary": self.ancillary,
        }
        return {k: v for k, v in streams.items() if v != 0.0}

    def to_dict(self) -> dict:
        """Export as dict for JSON serialization."""
        return {
            "date": self.date_str,
            "spot_arbitrage": self.spot_arbitrage,
            "fm": self.fm,
            "mlt": self.mlt,
            "ramp": self.ramp,
            "capacity_market": self.capacity_market,
            "ancillary": self.ancillary,
            "total": self.total_revenue,
        }

    @classmethod
    def from_daily_revenue(cls, daily_revenue, date_str: str = "") -> "RevenueBreakdown":
        """Convert DailyRevenue to RevenueBreakdown.

        The DailyRevenue.O (净收益) maps to spot_arbitrage.
        Other fields are zero until data becomes available.
        """
        from src.data.models import DailyRevenue
        return cls(
            date_str=date_str or daily_revenue.date_str,
            spot_arbitrage=daily_revenue.O,
            spot_volume_charge=daily_revenue.B,
            spot_volume_discharge=daily_revenue.M,
            spot_spread=daily_revenue.Q,
        )

    def summarize(self) -> str:
        """One-line revenue summary."""
        parts = [f"现货: {self.spot_arbitrage:,.0f}"]
        if self.fm != 0:
            parts.append(f"调频: {self.fm:,.0f}")
        if self.mlt != 0:
            parts.append(f"中长期: {self.mlt:,.0f}")
        parts.append(f"合计: {self.total_revenue:,.0f}")
        return " | ".join(parts)


@dataclass
class RevenueSeries:
    """Time series of RevenueBreakdown for multiple dates.

    Supports cumulative statistics, trend analysis, and visualization data.
    """
    breakdowns: list[RevenueBreakdown] = field(default_factory=list)

    def add(self, breakdown: RevenueBreakdown):
        self.breakdowns.append(breakdown)

    @property
    def total_spot_revenue(self) -> float:
        return sum(b.spot_arbitrage for b in self.breakdowns)

    @property
    def dates(self) -> list[str]:
        return [b.date_str for b in self.breakdowns]

    @property
    def spot_revenues(self) -> list[float]:
        return [b.spot_arbitrage for b in self.breakdowns]

    @property
    def total_revenues(self) -> list[float]:
        return [b.total_revenue for b in self.breakdowns]

    def cumulative_series(self) -> list[float]:
        """Cumulative total revenue over time."""
        cumsum = 0.0
        result = []
        for b in self.breakdowns:
            cumsum += b.total_revenue
            result.append(cumsum)
        return result

    def to_dataframe(self):
        """Export as pandas DataFrame for analysis."""
        import pandas as pd
        return pd.DataFrame([b.to_dict() for b in self.breakdowns])