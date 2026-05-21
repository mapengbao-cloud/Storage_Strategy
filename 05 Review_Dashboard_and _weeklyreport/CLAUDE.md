# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Energy storage revenue review data pipeline. Computes daily review data from per-date source Excel files and writes results into a master statistics workbook.

## How to run

```
python process_data.py [--day-ahead MMDD-MMDD] [--real-time MMDD-MMDD] [--settlement MMDD-MMDD]
```

- Without arguments: processes all source files found in `assets/`
- With one or more `--*-range` flags: only processes those source types for dates falling within the specified range (inclusive)
- Copies `assets/山东夏津储能收益统计表.xlsx` → `output/山东夏津储能收益统计表.xlsx`
- If the output file is locked (open in Excel), falls back to a timestamped filename
- The module is guarded by `if __name__ == '__main__'` — importing it will not execute the pipeline

## Data flow

Three source file types per date:

| File pattern | Target columns (润津 sheet) |
|---|---|
| `MMDD-日前机组组合收益复盘.xlsx` | B–R (column 2–18) |
| `MMDD-实时机组组合收益复盘.xlsx` | S–AI (column 19–35) |
| `MMDD-日结算收益复盘.xlsx` or `MMDD-日结算收益复盘-.xlsx` | AJ–BA (column 36–53), plus O6 value → AY (51) |

Source data is computed by `compute_summary_values()`, NOT read directly from `充放测算` row 4. Many source files contain Excel formulas without cached values, so `data_only=True` returns `None`. Instead, the function reads raw data from the `报价及预中标` sheet (columns J = electricity price, N = net demand per 15-minute period) and replicates the workbook's formula logic:

1. **Charge/discharge volumes** — sum of N where N≤0 (charge) / N≥0 (discharge), divided by 4 to convert from 15-min MW to MWh
2. **Weighted-average prices** — SUMPRODUCT of price × volume, divided by total volume
3. **Dependent values** — computed from the four base values plus parameters from `充放测算` I8–I14 (generation cost, assessment fees, deviation penalty, system fee) and a capacity allocation coefficient from `容量分摊系数`

The `报价及预中标` sheet is found by name substring (`'报价'` + `'预中标'`), not by index, because 日结算 files have extra sheets that shift the index.

Each source type maps its 17 computed values 1:1 to the target section, with 日结算 having an extra AY column (清分单收益 = N4 + C4) inserted between AX and AZ.

## Important constraints

- **Never modify the target file's formatting.** Only write raw data values — do not change number formats, column widths, row heights, merged cells, conditional formatting, or formulas.
- `综合效率` columns (Q/AH/AZ in target) keep full source precision; all other numeric values are rounded to 2 decimal places.
- All data must be numeric (`int` or `float`) so downstream formulas work correctly.

## Dependencies

openpyxl (read/write .xlsx files)
