"""Stage 02: Day-ahead trading review (日前机组组合收益复盘).

Reads 发电侧日前交易结果查询.xls, writes 96-point power/price data
to the day-ahead review template.

Usage (standalone):
    python -m src.stages.stage02_dayahead 0522              # auto-find source
    python -m src.stages.stage02_dayahead 0522 <src_path>   # explicit source

Usage (from pipeline):
    from src.stages.stage02_dayahead import run
    run('0522')

Template: assets/templates/日前机组组合收益复盘.xlsx
Output:  output/YYYY-MM-DD/MMDD-日前机组组合收益复盘.xlsx

Stage 02 and Stage 03 are structurally identical. They share the
internal _generate_trading_review() function.
"""

import sys
from pathlib import Path
from typing import Optional

from src.data.readers import read_trading_result_xls
from src.data.writers import copy_template, write_trading_review, save_and_close
from src.utils.date_utils import mmdd_to_date, date_to_iso


def _generate_trading_review(
    date_mmdd: str,
    source_pattern: str,
    template_name: str,
    output_suffix: str,
    source_path: Optional[str] = None,
    data_root: str = "data",
    output_root: str = "output",
    template_root: str = "assets/templates",
) -> Path:
    """Internal: generate a trading review file (shared by Stage 02 and 03).

    Args:
        date_mmdd: MMDD date string (e.g. '0522').
        source_pattern: Glob pattern for source file (e.g. '*日前交易结果查询*').
        template_name: Template filename (e.g. '日前机组组合收益复盘.xlsx').
        output_suffix: Output filename suffix (e.g. '日前机组组合收益复盘').
        source_path: Optional explicit path to source .xls.
        data_root: Root data directory.
        output_root: Root output directory.
        template_root: Root template directory.

    Returns:
        Path to the generated output file.
    """
    d = mmdd_to_date(date_mmdd)
    date_iso = date_to_iso(d)
    out_name = f"{date_mmdd}-{output_suffix}.xlsx"

    # Resolve source
    if source_path:
        src = Path(source_path)
    else:
        data_dir = Path(data_root) / "raw" / date_iso
        candidates = list(data_dir.glob(source_pattern))
        if not candidates:
            raise FileNotFoundError(
                f"No source matching '{source_pattern}' "
                f"for {date_mmdd} in {data_dir}"
            )
        src = candidates[0]

    # Read 96-point charge/discharge + price data
    cd_data = read_trading_result_xls(src)

    # Open template
    tpl = Path(template_root) / template_name
    if not tpl.exists():
        raise FileNotFoundError(f"Template not found: {tpl}")

    out_dir = Path(output_root) / date_iso
    out_path = out_dir / out_name
    wb = copy_template(tpl, out_path)

    # Write 96 points to 报价及预中标 sheet
    write_trading_review(
        wb,
        sheet_name="报价及预中标",
        power_values=cd_data.power_mw.values,
        price_values=cd_data.price.values,
    )

    save_and_close(wb, out_path)
    print(f"Saved: {out_path}")
    return out_path


def run(
    date_mmdd: str,
    source_path: Optional[str] = None,
    data_root: str = "data",
    output_root: str = "output",
    template_root: str = "assets/templates",
) -> Path:
    """Generate day-ahead trading review for one date.

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
        source_pattern="*日前交易结果查询*",
        template_name="日前机组组合收益复盘.xlsx",
        output_suffix="日前机组组合收益复盘",
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