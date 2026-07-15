"""Stage 03: Real-time trading review (实时机组组合收益复盘).

Reads 发电侧实时交易结果查询.xls, writes 96-point power/price data
to the real-time review template. Structurally identical to Stage 02.

Usage (standalone):
    python -m src.stages.stage03_realtime 0522              # auto-find source
    python -m src.stages.stage03_realtime 0522 <src_path>   # explicit source

Usage (from pipeline):
    from src.stages.stage03_realtime import run
    run('0522')

Template: assets/templates/实时机组组合收益复盘.xlsx
Output:  output/YYYY-MM-DD/MMDD-实时机组组合收益复盘.xlsx
"""

import sys
from pathlib import Path
from typing import Optional

from src.stages.stage02_dayahead import _generate_trading_review


def run(
    date_mmdd: str,
    source_path: Optional[str] = None,
    data_root: str = "data",
    output_root: str = "output",
    template_root: str = "assets/templates",
) -> Path:
    """Generate real-time trading review for one date.

    Args:
        date_mmdd: MMDD date string (e.g. '0522').
        source_path: Optional explicit path to source .xls file.
        data_root: Root directory for source data.
        output_root: Root directory for output files.
        template_root: Root directory for templates.

    Returns:
        Path to the generated output file.
    """
    return _generate_trading_review(
        date_mmdd=date_mmdd,
        source_pattern="*实时交易结果查询*",
        template_name="实时机组组合收益复盘.xlsx",
        output_suffix="实时机组组合收益复盘",
        source_path=source_path,
        data_root=data_root,
        output_root=output_root,
        template_root=template_root,
    )


# ── CLI entry point ──────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    mmd = sys.argv[1]
    src = sys.argv[2] if len(sys.argv) > 2 else None
    run(mmd, src)