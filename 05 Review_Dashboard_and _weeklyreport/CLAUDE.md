# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Energy storage revenue review data pipeline (阶段 05). Reads per-date source review workbooks from `assets/` and writes computed summary values into the master statistics workbook `山东夏津储能收益统计表.xlsx` using incremental update.

## How to run

```
python process_data.py [--day-ahead MMDD-MMDD] [--real-time MMDD-MMDD] [--settlement MMDD-MMDD]
```

- Without arguments: processes all source files found in `assets/`
- With filter flags: only processes matching source types within the date range (inclusive)
- Uses previous `output/山东夏津储能收益统计表.xlsx` as base, falls back to `assets/` template on first run
- If the output file is locked (open in Excel), falls back to a timestamped filename

## Target column mapping (润津 sheet)

| Source file type | Target columns | Compute function |
|---|---|---|
| `MMDD-日前机组组合收益复盘.xlsx` | B–R (col 2–18) | `compute_summary_values()` |
| `MMDD-实时机组组合收益复盘.xlsx` | S–AI (col 19–35) | `compute_summary_values()` |
| `MMDD-日结算收益复盘.xlsx` | AJ–BA (col 36–53) with AY(51)=O6 | `compute_settlement_values()` |

## Data source rule (critical)

Each column group in the statistics table corresponds EXACTLY to one source file type. Never cross-read:

- **日前 columns** → values from `日前机组组合收益复盘` file only
- **实时 columns** → values from `实时机组组合收益复盘` file only
- **日结算 columns** → values from `日结算收益复盘` file only

## compute_summary_values() — 日前/实时

Computes 17 values (A-Q) + O6 from the source workbook's `报价及预中标` sheet raw data:
- J column (电价) × N column (充放电需求) → charge/discharge volumes and weighted-average prices
- I8-I14 parameters from `充放测算`
- J_val (capacity coefficient) from `容量分摊系数` column J weighted by charging periods

This is correct for 日前/实时 files because their `充放测算` row 4 formulas reference `报价及预中标` internally.

## compute_settlement_values() — 日结算

Computes 17 values + O6 from the 日结算 file's settlement sheets:
- **Base values** read from `充电日清算费用` (Z29→charge vol, AA29→charge price, AB29→charge income) and `放电日清算费用` (P101→discharge price, AJ101→discharge vol, AK101→discharge income)
- **Parameters** I8-I14 + J4 read from `充放测算`
- **Dependent values** (D-Q) computed using the same formula logic as 充放测算 row 4

This is DIFFERENT from compute_summary_values() because the 日结算 file's `充放测算` formulas reference settlement data sheets (充电/放电日清算费用), NOT `报价及预中标`. Using the wrong function would compute values from market data instead of settlement data.

## Important constraints

- Never modify the target file's formatting — only write raw data values
- `综合效率` columns (Q/AH/AZ) keep full source precision; all other values rounded to 2 decimal places
- All data must be numeric (`int` or `float`)
- The target file A column stores dates as Excel serial numbers (e.g. 46163), not datetime objects

## Dependencies

openpyxl (read/write .xlsx files)
