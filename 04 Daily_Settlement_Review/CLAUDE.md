# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Daily settlement review (阶段 04) — consolidates charge/discharge settlement statements with real-time trading parameters into a daily review workbook.

## Template

`assets/输出模版-0504-日结算收益复盘.xlsx` — 3 sheets only:

| Sheet | Source | Description |
|-------|--------|-------------|
| `充放测算` | Self-contained formulas + RT review (J4, I8-I14) | Charge/discharge profit calculation; all row 4 formulas reference the two settlement sheets below |
| `充电日清算费用` | 充电结算单 → `日清算数据` | Charging side settlement data (29 rows × 28 cols) |
| `放电日清算费用` | 放电结算单 → `日清算费用` | Discharging side settlement data (108 rows × 37 cols) |

## Generate a review file

```
python generate_review.py
```

Edit the `DATES` list in the script to control which dates to process.

### Per-date inputs

1. `6052-YYYY-MM-DD德州润津储能科技有限公司结算单-充电.xlsx`
2. `6052-YYYY-MM-DD德州润津储能科技有限公司结算单-放电.xlsx`
3. `MMDD-实时机组组合收益复盘.xlsx` (from stage 03 `output/`)

### Generation logic

1. Copy template → `output/MMDD-日结算收益复盘.xlsx`
2. 充电日清算费用 ← full copy from 充电结算单 `日清算数据` (hardcoded values, no formulas)
3. 放电日清算费用 ← full copy from 放电结算单 `日清算费用` (hardcoded values, no formulas)
4. 充放测算: only update **J4** (容量分摊系数, computed via `compute_J4()` from RT review) and **I8, I9, I12, I13, I14** (parameters from RT review 充放测算)
5. **Never** overwrite 充放测算 row 4 or row 6-8 formulas

### J4 computation

`compute_J4()` reads the RT review file's `容量分摊系数` (column J = 5月, rows 8-103) and `报价及预中标` (column N, rows 2-97) to compute the weighted-average capacity allocation coefficient during charging periods.

### Key rules

- All data written to target must be numeric (`int`/`float`)
- `copy_sheet_data()` skips MergedCells and never overwrites formulas in the target
- `convert_to_numeric()` converts string numbers to float/int, skipping formula cells

## Dependencies

- Python 3.14 with `openpyxl`
