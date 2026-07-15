"""Strategy backtesting engine.

For each historical date:
1. Run the 3-condition strategy evaluation using available data
2. Compare trade/no-trade signal with actual daily revenue
3. Compute aggregate performance metrics

Workflow:
    engine = BacktestEngine(data_root='data', output_root='output')
    results = engine.run(date_range='0518-0603')
    metrics = engine.metrics(results)
    engine.print_report(results, metrics)
"""

from dataclasses import dataclass, field
from pathlib import Path
from datetime import date

from src.utils.date_utils import expand_mmdd_range, date_to_mmdd, mmdd_to_date, date_to_iso
from src.data.models import StrategySignal, DailyRevenue
from src.data.readers import read_prediction_load_xls, read_trading_result_xls
from src.business.strategy import evaluate_strategy
from src.business.revenue import compute_charge_discharge_from_96point
from src.backtesting.metrics import compute_metrics, BacktestMetrics


@dataclass
class BacktestResult:
    """Single-date backtesting result."""
    date_str: str       # MMDD
    date_iso: str       # ISO format
    signal: StrategySignal | None = None
    charge_volume: float = 0.0
    discharge_volume: float = 0.0
    charge_price: float = 0.0
    discharge_price: float = 0.0
    price_spread: float = 0.0
    net_revenue_approximate: float = 0.0
    error: str | None = None

    @property
    def would_have_traded(self) -> bool:
        return self.signal is not None and self.signal.should_trade

    @property
    def is_valid(self) -> bool:
        return self.error is None and self.signal is not None


class BacktestEngine:
    """Run strategy backtesting over a date range."""

    def __init__(
        self,
        data_root: str = "data",
        output_root: str = "output",
        template_root: str = "assets/templates",
    ):
        self.data_root = Path(data_root)
        self.output_root = Path(output_root)
        self.template_root = Path(template_root)

    def run(
        self,
        date_range: str,
        verbose: bool = True,
    ) -> list[BacktestResult]:
        """Run backtesting for a date range.

        For each date, attempts to:
        1. Read load prediction file → BiddingSpaceData
        2. Read day-ahead trading result → ChargeDischargeData
        3. Run strategy evaluation → StrategySignal
        4. Compute approximate revenue from 96-point data

        Args:
            date_range: MMDD-MMDD string (e.g. '0518-0603').
            verbose: Print progress per date.

        Returns:
            List of BacktestResult for each date.
        """
        dates = expand_mmdd_range(date_range)
        results = []

        for d in dates:
            date_str = date_to_mmdd(d)
            date_iso = date_to_iso(d)
            data_dir = self.data_root / "raw" / date_iso

            result = BacktestResult(date_str=date_str, date_iso=date_iso)

            # Step 1: Load prediction data
            pred_files = list(data_dir.glob("*负荷信息预测*"))
            if not pred_files:
                result.error = "no prediction file"
                results.append(result)
                if verbose:
                    print(f"  {date_str}: SKIP — no prediction file")
                continue

            try:
                bs_data = read_prediction_load_xls(pred_files[0])
            except Exception as e:
                result.error = f"prediction read error: {e}"
                results.append(result)
                if verbose:
                    print(f"  {date_str}: SKIP — {e}")
                continue

            # Step 2: Load day-ahead trading result
            da_files = list(data_dir.glob("*日前交易结果查询*"))
            if not da_files:
                result.error = "no day-ahead trading file"
                results.append(result)
                if verbose:
                    print(f"  {date_str}: SKIP — no day-ahead trading file")
                continue

            try:
                cd_data = read_trading_result_xls(da_files[0])
            except Exception as e:
                result.error = f"trading result read error: {e}"
                results.append(result)
                if verbose:
                    print(f"  {date_str}: SKIP — {e}")
                continue

            # Step 3: Strategy evaluation
            signal = evaluate_strategy(bs_data, cd_data.price, date_iso)
            result.signal = signal

            # Step 4: Approximate revenue from 96-point data
            try:
                B, A, C, M_val, L, N_val = compute_charge_discharge_from_96point(cd_data)
                result.charge_volume = B
                result.charge_price = A
                result.discharge_volume = M_val
                result.discharge_price = L
                result.price_spread = L - A
                result.net_revenue_approximate = N_val + C
            except Exception:
                pass

            results.append(result)

            if verbose:
                trade_str = "TRADE" if signal.should_trade else "NO"
                print(
                    f"  {date_str}: {trade_str} | "
                    f"spread={result.price_spread:.0f} | "
                    f"bs_diff={signal.bidding_space_peak_valley_diff:.0f}MW | "
                    f"midday={signal.is_midday_valley}"
                )

        return results

    def metrics(self, results: list[BacktestResult]) -> BacktestMetrics:
        """Compute aggregate performance metrics from backtesting results.

        Args:
            results: List of BacktestResult from run().

        Returns:
            BacktestMetrics dataclass.
        """
        return compute_metrics(results)

    def print_report(
        self,
        results: list[BacktestResult],
        metrics: BacktestMetrics | None = None,
    ):
        """Print a formatted backtesting report.

        Args:
            results: Backtesting results from run().
            metrics: Pre-computed metrics, or None to compute on the fly.
        """
        if metrics is None:
            metrics = self.metrics(results)

        valid = [r for r in results if r.is_valid]
        trade_dates = [r for r in valid if r.would_have_traded]
        no_trade_dates = [r for r in valid if not r.would_have_traded]

        print("\n" + "=" * 60)
        print("STRATEGY BACKTESTING REPORT")
        print("=" * 60)
        print(f"Period: {results[0].date_str} - {results[-1].date_str}")
        print(f"Total dates: {len(results)}")
        print(f"Valid dates: {len(valid)}")
        print(f"Errors: {len(results) - len(valid)}")

        print(f"\nTrade signals:")
        print(f"  TRADE:     {len(trade_dates)} days")
        print(f"  NO TRADE:  {len(no_trade_dates)} days")

        if trade_dates:
            trades_net = [r.net_revenue_approximate for r in trade_dates]
            print(f"\nTrade days revenue:")
            print(f"  Total:     {sum(trades_net):,.0f} yuan")
            print(f"  Avg/day:   {sum(trades_net)/len(trades_net):,.0f} yuan")
            print(f"  Max:       {max(trades_net):,.0f} yuan")
            print(f"  Min:       {min(trades_net):,.0f} yuan")

        if no_trade_dates:
            nt_net = [r.net_revenue_approximate for r in no_trade_dates]
            print(f"\nNon-trade days revenue (if traded):")
            print(f"  Total:     {sum(nt_net):,.0f} yuan")
            print(f"  Avg/day:   {sum(nt_net)/len(nt_net):,.0f} yuan")

        print(f"\nMetrics:")
        print(f"  Trade win rate:      {metrics.trade_win_rate:.1%}")
        print(f"  Avg trade revenue:   {metrics.avg_trade_revenue:,.0f} yuan")
        print(f"  Value at Risk (95%): {metrics.var_95:,.0f} yuan")
        print(f"  Consistency:         {metrics.consistency:.1%}")

        if metrics.trade_revenues:
            print(f"\nStrategy (3 conditions):")
            print(f"  If trade → avg {metrics.avg_trade_revenue:,.0f} yuan/day")
            if metrics.avg_no_trade_revenue is not None:
                diff = metrics.avg_trade_revenue - metrics.avg_no_trade_revenue
                print(f"  Strategy edge: {diff:+,.0f} yuan/day")

        # Summary verdict
        if metrics.avg_trade_revenue > 0 and metrics.trade_win_rate > 0.5:
            verdict = "Strategy shows positive expected value"
        elif metrics.avg_trade_revenue > 0:
            verdict = "Strategy has positive avg return but low win rate"
        else:
            verdict = "Strategy needs revision — negative expected value"

        print(f"\nVerdict: {verdict}")
        print("=" * 60)

    def export_csv(self, results: list[BacktestResult], path: str):
        """Export backtesting results to CSV for further analysis."""
        import csv

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "date", "should_trade", "bs_peak_valley_diff_mw",
                "valley_window", "is_midday_valley", "price_spread",
                "charge_price", "discharge_price", "spread",
                "charge_vol", "discharge_vol", "net_revenue_approx",
                "reasons", "error",
            ])
            for r in results:
                writer.writerow([
                    r.date_iso,
                    r.would_have_traded,
                    round(r.signal.bidding_space_peak_valley_diff, 0) if r.signal else "",
                    f"{r.signal.valley_window_start}-{r.signal.valley_window_end}" if r.signal else "",
                    r.signal.is_midday_valley if r.signal else "",
                    round(r.signal.day_ahead_price_spread, 2) if r.signal else "",
                    round(r.charge_price, 2),
                    round(r.discharge_price, 2),
                    round(r.price_spread, 2),
                    round(r.charge_volume, 2),
                    round(r.discharge_volume, 2),
                    round(r.net_revenue_approximate, 2),
                    " | ".join(r.signal.reasons) if r.signal else "",
                    r.error or "",
                ])
        print(f"Exported: {path}")