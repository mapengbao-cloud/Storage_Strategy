"""Backtesting performance metrics.

Computes key statistics from a list of backtesting results.

Metrics:
- Trade win rate: fraction of trade-signal days with positive net revenue
- Avg trade revenue: mean net revenue on trade-signal days
- Avg no-trade revenue: mean net revenue on days without signal
- VaR 95%: 95th percentile worst-case revenue (Value at Risk)
- Consistency: fraction of trade days where revenue > 0
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BacktestMetrics:
    """Aggregate backtesting performance metrics."""

    total_dates: int = 0
    valid_dates: int = 0
    trade_signal_dates: int = 0
    no_trade_dates: int = 0

    # Revenue on trade days (when strategy would have been active)
    trade_revenues: list[float] = field(default_factory=list)

    # Revenue on non-trade days (if traded anyway — for comparison)
    no_trade_revenues: list[float] = field(default_factory=list)

    # Computed statistics
    avg_trade_revenue: float = 0.0
    avg_no_trade_revenue: Optional[float] = None
    trade_win_rate: float = 0.0
    var_95: float = 0.0  # Value at Risk (95%)
    consistency: float = 0.0  # Fraction of trade days with positive revenue


def compute_metrics(results) -> BacktestMetrics:
    """Compute backtesting metrics from a list of BacktestResult.

    Args:
        results: List of BacktestResult from BacktestEngine.run().

    Returns:
        BacktestMetrics with all statistics computed.
    """
    # Avoid circular import
    from src.backtesting.engine import BacktestResult

    metrics = BacktestMetrics()
    metrics.total_dates = len(results)

    valid = [r for r in results if r.is_valid]
    metrics.valid_dates = len(valid)

    trade_results = [r for r in valid if r.would_have_traded]
    no_trade_results = [r for r in valid if not r.would_have_traded]

    metrics.trade_signal_dates = len(trade_results)
    metrics.no_trade_dates = len(no_trade_results)

    # Revenues
    metrics.trade_revenues = [r.net_revenue_approximate for r in trade_results]
    metrics.no_trade_revenues = [r.net_revenue_approximate for r in no_trade_results]

    # Avg trade revenue
    if metrics.trade_revenues:
        metrics.avg_trade_revenue = sum(metrics.trade_revenues) / len(metrics.trade_revenues)
        metrics.trade_win_rate = (
            sum(1 for v in metrics.trade_revenues if v > 0)
            / len(metrics.trade_revenues)
        )
        metrics.consistency = metrics.trade_win_rate

    # Avg no-trade revenue
    if metrics.no_trade_revenues:
        metrics.avg_no_trade_revenue = (
            sum(metrics.no_trade_revenues) / len(metrics.no_trade_revenues)
        )

    # VaR 95% — sorted ascending, 5th percentile
    if metrics.trade_revenues:
        sorted_revs = sorted(metrics.trade_revenues)
        idx = max(0, int(len(sorted_revs) * 0.05))
        metrics.var_95 = sorted_revs[idx]

    return metrics


def compute_sharpe(returns: list[float], risk_free_rate: float = 0.0) -> float:
    """Compute Sharpe ratio from a list of daily returns.

    Args:
        returns: List of daily return values (not percentages).
        risk_free_rate: Risk-free daily rate (default 0 for short period).

    Returns:
        Sharpe ratio (annualized approximation using sqrt(252)).
    """
    if len(returns) < 2:
        return 0.0

    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = variance ** 0.5

    if std == 0:
        return 0.0

    # Daily Sharpe
    daily_sharpe = (mean - risk_free_rate) / std

    # Annualize (approx 252 trading days)
    return daily_sharpe * (252 ** 0.5)


def compute_max_drawdown(values: list[float]) -> float:
    """Compute maximum drawdown from a cumulative value series.

    Args:
        values: Cumulative value at each step.

    Returns:
        Maximum drawdown as a negative value (e.g., -0.15 = 15% drawdown).
    """
    if not values:
        return 0.0

    peak = values[0]
    max_dd = 0.0

    for v in values:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak != 0 else 0
        if dd < max_dd:
            max_dd = dd

    return max_dd


def compute_win_rate(revenues: list[float]) -> float:
    """Fraction of days with positive revenue."""
    if not revenues:
        return 0.0
    return sum(1 for r in revenues if r > 0) / len(revenues)