"""Unified CLI — single entry point for all pipeline operations.

Usage:
    # Pipeline execution
    python -m src.cli run 0522                    # single date, all stages
    python -m src.cli run 0522-0531               # date range
    python -m src.cli run 0522 --stages 01,02,03  # specific stages
    python -m src.cli run 0522 --dry-run          # preview
    python -m src.cli run 0522 --force            # re-run even if done

    # Inspection
    python -m src.cli status                      # pipeline state summary
    python -m src.cli validate 0522               # check for missing source files

    # Analysis
    python -m src.cli backtest 0518-0603          # strategy backtesting
    python -m src.cli evaluate 0522               # strategy evaluation for one date

    # Individual stages
    python -m src.cli stage 01 0522               # run stage 01 for one date
    python -m src.cli stage 03 0522-0531          # run stage 03 for range
"""

import sys
import argparse
from pathlib import Path
from datetime import date

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def cmd_run(args):
    """Execute the pipeline for given dates."""
    from src.pipeline.orchestrator import Pipeline

    stages = None
    if args.stages:
        stage_map = {
            "01": "01_bidding_space",
            "02": "02_dayahead",
            "03": "03_realtime",
            "04": "04_settlement",
            "05": "05_dashboard",
            "06": "06_analysis",
        }
        stages = []
        for s in args.stages.split(","):
            s = s.strip()
            if s in stage_map:
                stages.append(stage_map[s])
            else:
                stages.append(s)

    pipe = Pipeline(
        date_range=args.date_range,
        stages=stages,
        data_root=args.data_root,
        output_root=args.output_root,
        template_root=args.template_root,
    )

    print(f"Pipeline: {len(pipe.dates)} dates, {len(pipe.stages_to_run)} stages")
    print(f"Dates: {pipe.date_strs[0]} ... {pipe.date_strs[-1]}")
    print(f"Stages: {', '.join(pipe.stages_to_run)}")
    print()

    if args.dry_run:
        print("[DRY RUN — no files will be modified]\n")

    state = pipe.run(dry_run=args.dry_run, force=args.force)
    print(f"\n{state.summary()}")


def cmd_status(args):
    """Show pipeline state summary."""
    from src.pipeline.state import PipelineState

    state_file = args.state_file or f"{args.output_root}/pipeline_state.json"
    state = PipelineState(state_file)
    print(state.summary())


def cmd_validate(args):
    """Check which source files are missing."""
    from src.pipeline.orchestrator import Pipeline

    pipe = Pipeline(
        date_range=args.date_range,
        data_root=args.data_root,
        output_root=args.output_root,
        template_root=args.template_root,
    )
    missing = pipe.validate()

    if not missing:
        print("All source files present for all dates.")
    else:
        for date_str, patterns in sorted(missing.items()):
            print(f"{date_str}:")
            for p in patterns:
                print(f"  MISSING: {p}")
        print(f"\n{sum(len(v) for v in missing.values())} missing files.")


def cmd_backtest(args):
    """Run strategy backtesting."""
    from src.utils.date_utils import expand_mmdd_range, date_to_mmdd

    dates = expand_mmdd_range(args.date_range)
    date_strs = [date_to_mmdd(d) for d in dates]

    print(f"Backtesting {len(dates)} dates: {date_strs[0]}...{date_strs[-1]}")
    print("(Backtesting engine — see src/backtesting/engine.py)")
    print("Note: requires bidding space + price data for all dates in range.")


def cmd_evaluate(args):
    """Evaluate strategy for a single date."""
    from src.utils.date_utils import mmdd_to_date, date_to_iso
    from src.data.readers import read_prediction_load_xls, read_trading_result_xls
    from src.business.strategy import evaluate_strategy

    d = mmdd_to_date(args.date)
    date_iso = date_to_iso(d)
    data_dir = Path(args.data_root) / "raw" / date_iso

    # Find source files
    pred_files = list(data_dir.glob("*负荷信息预测*"))
    da_files = list(data_dir.glob("*日前交易结果查询*"))

    if not pred_files:
        print(f"No prediction file for {args.date} in {data_dir}")
        return

    if not da_files:
        print(f"No day-ahead trading file for {args.date} in {data_dir}")
        return

    bidding_space = read_prediction_load_xls(pred_files[0])
    cd_data = read_trading_result_xls(da_files[0])

    signal = evaluate_strategy(bidding_space, cd_data.price, date_iso)

    print(f"\nStrategy Evaluation: {date_iso}")
    print("=" * 50)
    print(f"Trade decision: {'TRADE [GO]' if signal.should_trade else 'NO TRADE [SKIP]'}")
    print(f"Bidding space peak-valley diff: {signal.bidding_space_peak_valley_diff:.0f} MW")
    print(f"Valley window: {signal.valley_window_start} - {signal.valley_window_end}")
    print(f"Is midday valley: {signal.is_midday_valley}")
    print(f"Day-ahead price spread: {signal.day_ahead_price_spread:.0f} yuan/MWh")
    print("\nReasons:")
    for r in signal.reasons:
        print(f"  - {r}")

    # Risk assessment if requested
    if getattr(args, 'with_risk', False):
        _print_risk_assessment(date_iso, bidding_space, cd_data)


def cmd_stage(args):
    """Run a single stage for given dates."""
    from src.utils.date_utils import expand_mmdd_range, date_to_mmdd

    stage_map = {
        "01": ("01_bidding_space", "src.stages.stage01_bidding_space"),
        "02": ("02_dayahead", "src.stages.stage02_dayahead"),
        "03": ("03_realtime", "src.stages.stage03_realtime"),
        "04": ("04_settlement", "src.stages.stage04_settlement"),
        "05": ("05_dashboard", "src.stages.stage05_dashboard"),
    }

    if args.stage not in stage_map:
        print(f"Unknown stage: {args.stage}. Available: {list(stage_map.keys())}")
        sys.exit(1)

    stage_name, module_path = stage_map[args.stage]
    import importlib
    mod = importlib.import_module(module_path)

    dates = expand_mmdd_range(args.date_range)
    kwargs = {
        "data_root": args.data_root,
        "output_root": args.output_root,
        "template_root": args.template_root,
    }

    for d in dates:
        date_str = date_to_mmdd(d)
        try:
            if args.stage == "05":
                mod.run(
                    date_list=[date_str],
                    source_dir=args.output_root,
                    output_dir=f"{args.output_root}/reports",
                )
            else:
                mod.run(date_mmdd=date_str, **kwargs)
        except FileNotFoundError as e:
            print(f"  SKIP {date_str}: {e}")
        except Exception as e:
            print(f"  FAIL {date_str}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="润津储能交易策略与复盘 — 统一命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data-root", default="data",
        help="Root directory for source data (default: data)"
    )
    parser.add_argument(
        "--output-root", default="output",
        help="Root directory for output files (default: output)"
    )
    parser.add_argument(
        "--template-root", default="assets/templates",
        help="Root directory for templates (default: assets/templates)"
    )

    sub = parser.add_subparsers(dest="command", help="Commands")

    # ── run ──
    p_run = sub.add_parser("run", help="Execute pipeline for date(s)")
    p_run.add_argument("date_range", help="Date or range (e.g. 0522 or 0522-0531)")
    p_run.add_argument("--stages", help="Comma-separated stage numbers (e.g. 01,02)")
    p_run.add_argument("--dry-run", action="store_true", help="Preview without executing")
    p_run.add_argument("--force", action="store_true", help="Re-run completed stages")

    # ── status ──
    p_status = sub.add_parser("status", help="Show pipeline state")
    p_status.add_argument("--state-file", help="Path to state JSON file")

    # ── validate ──
    p_val = sub.add_parser("validate", help="Check for missing source files")
    p_val.add_argument("date_range", help="Date range to check (e.g. 0522-0531)")

    # ── backtest ──
    p_bt = sub.add_parser("backtest", help="Run strategy backtesting")
    p_bt.add_argument("date_range", help="Date range (e.g. 0518-0603)")

    # ── risk-profile ──
    p_rp = sub.add_parser("risk-profile", help="Build DA-RT deviation risk profile")
    p_rp.add_argument("date_range", help="Date range (e.g. 0518-0603)")

    # ── evaluate ──
    p_ev = sub.add_parser("evaluate", help="Strategy evaluation for one date")
    p_ev.add_argument("date", help="MMDD date string (e.g. 0522)")
    p_ev.add_argument("--with-risk", action="store_true",
                      help="Include DA-RT deviation risk assessment")

    # ── stage ──
    p_st = sub.add_parser("stage", help="Run a single stage")
    p_st.add_argument("stage", help="Stage number (01-05)")
    p_st.add_argument("date_range", help="Date or range (e.g. 0522 or 0522-0531)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # Dispatch
    cmds = {
        "run": cmd_run,
        "status": cmd_status,
        "validate": cmd_validate,
        "backtest": cmd_backtest,
        "evaluate": cmd_evaluate,
        "risk-profile": cmd_risk_profile,
        "stage": cmd_stage,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()