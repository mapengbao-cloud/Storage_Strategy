"""Stage 01: Bidding space analysis (竞价空间分析).

Generates bidding space analysis from load forecast or actual grid data.

Usage (standalone):
    python -m src.stages.stage01_bidding_space 0522              # prediction
    python -m src.stages.stage01_bidding_space 0522 actual       # actual
    python -m src.stages.stage01_bidding_space 0522 <src_path>   # explicit

Usage (from pipeline):
    from src.stages.stage01_bidding_space import run
    run('0522')

Template: assets/templates/竞价空间分析.xlsx
Output:  output/YYYY-MM-DD/MMDD-竞价空间分析(预测|实际).xlsx
"""

import sys
from pathlib import Path
from typing import Optional

from src.data.readers import read_prediction_load_xls, read_actual_grid_xlsx
from src.data.writers import (
    copy_template, write_96point_data, save_and_close,
)
from src.utils.excel_utils import write_96point_formulas
from src.utils.date_utils import mmdd_to_date, date_to_iso


def run(
    date_mmdd: str,
    source_path: Optional[str] = None,
    is_actual: bool = False,
    data_root: str = "data",
    output_root: str = "output",
    template_root: str = "assets/templates",
) -> Path:
    """Generate bidding space analysis for one date.

    Args:
        date_mmdd: MMDD date string (e.g. '0522').
        source_path: Optional explicit path to source file.
        is_actual: If True, read actual grid data; else prediction.
        data_root: Root directory for source data.
        output_root: Root directory for output files.
        template_root: Root directory for templates.

    Returns:
        Path to the generated output file.

    Raises:
        FileNotFoundError: If source or template is missing.
    """
    d = mmdd_to_date(date_mmdd)
    date_iso = date_to_iso(d)
    suffix = "实际" if is_actual else "预测"
    out_name = f"{date_mmdd}-竞价空间分析({suffix}).xlsx"

    # Resolve source path
    if source_path:
        src = Path(source_path)
    else:
        data_dir = Path(data_root) / "raw" / date_iso
        if is_actual:
            candidates = list(data_dir.glob("*电网运行实际信息*"))
        else:
            candidates = list(data_dir.glob("*负荷信息预测*"))
        if not candidates:
            raise FileNotFoundError(
                f"No {'actual' if is_actual else 'prediction'} source "
                f"for {date_mmdd} in {data_dir}"
            )
        src = candidates[0]

    # Read data
    if is_actual:
        bs_data = read_actual_grid_xlsx(src)
    else:
        bs_data = read_prediction_load_xls(src)

    data_rows = [
        bs_data.dispatched_load.values,
        bs_data.tie_line_load.values,
        bs_data.wind_power.values,
        bs_data.solar_power.values,
    ]

    # Open template
    tpl = Path(template_root) / "竞价空间分析.xlsx"
    if not tpl.exists():
        raise FileNotFoundError(f"Template not found: {tpl}")

    out_dir = Path(output_root) / date_iso
    out_path = out_dir / out_name
    wb = copy_template(tpl, out_path)
    ws = wb["Sheet1"]

    # Write 96-point data to rows 3-6
    write_96point_data(ws, data_rows, start_row=3, start_col=2)

    # Write bidding space formulas to row 7
    write_96point_formulas(ws, row=7, formula_template="{col}3-{col}4-{col}5-{col}6")

    save_and_close(wb, out_path)
    print(f"Saved: {out_path}")
    return out_path


# ── CLI entry point (backward compatible) ────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    date_str = sys.argv[1]
    is_actual = len(sys.argv) > 2 and sys.argv[2] == "actual"
    src = None

    if is_actual:
        if len(sys.argv) > 3:
            src = sys.argv[3]
    else:
        if len(sys.argv) > 2:
            src = sys.argv[2]

    run(date_str, src, is_actual)