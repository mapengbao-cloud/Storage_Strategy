# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **daily settlement review** step (04) of a multi-stage energy storage trading pipeline for **德州润津储能科技有限公司** (Dezhou Runjin Energy Storage Technology Co.).

```
01 biddingSpace_analysis → 02 Dayahead_Trading_Review → 03 Real-time_Trading_Review → 04 Daily_Settlement_Review
```

Each stage corresponds to a sibling directory under `E:\DataWork\Storage\`.

## File Naming Conventions

- **结算单 (Settlement statements)**: `6052-YYYY-MM-DD德州润津储能科技有限公司结算单-{充电|放电}.xlsx`
  - `充电` = charging (购买侧/purchase side)
  - `放电` = discharging (发电侧/generation side)
- **日结算收益复盘 (Daily settlement review)**: `MMDD-日结算收益复盘.xlsx`
- **实时机组组合收益复盘 (Real-time unit commitment review)**: `MMDD-实时机组组合收益复盘.xlsx`

All source files live in `assets/`. Output files go to `output/`.

## Key Data Relationships

### 日结算收益复盘 workbook (the central consolidation target)

| Sheet | Source | Description |
|-------|--------|-------------|
| `充电日清算费用` | 结算单-充电 → `日清算数据` | Charging side settlement: 29 rows × 28 cols (售电侧, by hour) |
| `放电日清算费用` | 结算单-放电 → `日清算费用` | Discharging side settlement: 108 rows × 37 cols (发电侧, by 15-min) |
| `充放测算` | Self-contained + real-time review | Charge/discharge profit calculation; J4 = 容量分摊系数 |
| `报价及预中标` | From day-ahead stage | Bidding and pre-clearing data |
| `容量分摊系数` | From real-time stage | Capacity allocation coefficient lookup table |

### 容量分摊系数 (Capacity allocation coefficient)

- In `实时机组组合收益复盘.xlsx`, `充放测算` sheet J4 references `=容量分摊系数!G3` (formula, not hardcoded value).
- The computed value (e.g. `0.1193...`) should be written into `日结算收益复盘.xlsx` `充放测算` sheet J4 as a hardcoded value.

## Template Rule

**日结算收益复盘输出必须以 `assets/0504-日结算收益复盘.xlsx` 为模版生成。** 该文件中的表单结构、格式（合并单元格、列宽、行高、字体、边框、填充色、数字格式、对齐方式）均不可改动。生成新日期的复盘文件时，应在 0504 模版基础上仅替换数据内容（结算单数据 + 实时测算数据），保留所有原始格式。

## Common Operations

### Daily settlement data refresh

Replace settlement data in the review workbook with latest settlement statements:

```python
# Use openpyxl (pre-installed in Python 3.14)
# Load settlement statements with data_only=False (to preserve formatting)
# Load real-time review with data_only=True (to resolve formulas to values)

import openpyxl
from copy import copy

def copy_sheet_data(source_ws, target_ws):
    # 1. Unmerge target merged cells
    # 2. Copy cell values + styles (font, border, fill, number_format, alignment)
    # 3. Re-merge cells matching source
    # 4. Copy column/row dimensions
```

### Template data overlay (NOT full replacement)

**Do NOT clear all cell values before writing source data.** The template contains cells that have no corresponding data in the source files (e.g. `充放测算` N6:O8 = 日总值调整/高频调整/偏差调整, which are settlement-review-specific formulas). Use a selective overwrite approach: only write non-None values from the source into the template, preserving template-only cells untouched.

```
# WRONG: clear all then write
clear_sheet_values(target_ws)
write_values(target_ws, source_ws)

# RIGHT: only overwrite cells where source has data
for src_cell in source_cells:
    if src_cell.value is not None:
        target_cell.value = src_cell.value
```

### MergedCell gotcha

When reading/writing sheets with merged cells, use `ws.cell(row=r, column=c)` syntax and check `type(cell).__name__ == 'MergedCell'` to skip non-writable merged cells. Never use bracket notation `ws['A1']` which will raise `'MergedCell' object attribute 'value' is read-only` on merged-cell positions.

### Numeric conversion

All data read from source files must be converted to numeric types (`int` or `float`) before writing to the target workbook. This ensures the written values can be used directly in formula calculations without type errors. Use `int()` for integer values and `float()` for decimal values (including prices, coefficients, percentages). Handle `None`, empty cells, and non-numeric strings gracefully — default to `0` or raise a clear error depending on the context.

### Formula resolution

Formulas from source workbooks must be resolved to values before writing to the target. Load the source with `data_only=True` when reading formula cells. The target should receive hardcoded values, not cross-sheet references that won't resolve in the output file.

## Dependencies

- Python 3.14 with `openpyxl`
- No virtual environment or package manager configured
- No build step, linting, or test suite in this project
