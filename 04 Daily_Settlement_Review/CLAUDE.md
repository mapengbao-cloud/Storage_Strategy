# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Daily settlement review (阶段 04) — consolidates charge/discharge settlement statements into a daily review workbook.

## Architecture (新架构 — 2026-06-25 更新)

**模板从 `assets/templates/` 按月选择，输出到 `output/日结算单收益测算/`。不再依赖 RT review。**

### Template selection（按月份）

| 月份 | 模板 |
|------|------|
| 1月 | `日结算收益复盘-1月.xlsx` |
| 2月 | `日结算收益复盘-2月.xlsx` |
| 3月 | `日结算收益复盘-3月.xlsx` |
| 4月 | `日结算收益复盘-4月.xlsx` |
| 5月 | `日结算收益复盘-20260525日前.xlsx` |
| 6月 | `日结算收益复盘-6月.xlsx` |

> 模板路径：`assets/templates/`（项目根目录），由 `_get_template(month)` 自动选择。

### Template structure（4 sheets）

| Sheet | 说明 |
|-------|------|
| 充放测算 | 公式计算收益汇总，Row 4 为结果行（19列），自包含公式 |
| 充电日清算费用 | 用电结算单数据（30列，25行 = 24小时+合计） |
| 放电日清算费用 | 发电结算单数据（42列，97行 = 96时段+合计） |
| 容量分摊系数 | 容量分摊计算参数（32行），公式引用充电日清算费用 |

### 不再依赖 RT review

模板 `充放测算` 的 J4 和 I8-I14 参数已自包含，`容量分摊系数` sheet 的公式直接引用 `充电日清算费用` sheet 数据计算。`compute_J4()` 函数已移除。

## Generate a review file

```bash
# Single date
python generate_review.py 0621

# Batch (edit DATES list in script)
python generate_review.py
```

### Per-date inputs

1. `6052-YYYY-MM-DD德州润津储能科技有限公司结算单-充电.xlsx`（~11KB，含「日清算数据」sheet）
2. `6052-YYYY-MM-DD德州润津储能科技有限公司结算单-放电.xlsx`（~21KB，含「日清算费用」sheet）

结算单文件放在 `04 Daily_Settlement_Review/assets/`，从下载目录拷入时按大小区分充/放电。

### Generation logic

1. `_get_template(month)` 选择正确模板
2. `shutil.copy2(template, output_path)` 复制模板到 `output/日结算单收益测算/MMDD-日结算收益复盘.xlsx`
3. 充电日清算费用 ← 充电结算单 `日清算数据`（hardcoded values, no formulas）
4. 放电日清算费用 ← 放电结算单 `日清算费用`（hardcoded values, no formulas）
5. `convert_to_numeric()` 确保数据为数值格式
6. 保存输出（模板公式自动引用结算单数据计算）

### Key rules

- All data written to target must be numeric (`int`/`float`)
- `copy_sheet_data()` skips MergedCells and never overwrites formulas in the target
- `convert_to_numeric()` converts string numbers to float/int, skipping formula cells

## 入库流程

参考 `收益测算工作流程.md`：
1. COM 刷新（`win32com` 打开 Excel → 计算 → 保存）
2. `openpyxl(data_only=True)` 读取「充放测算」Row 4 的 19 列计算值
3. 写入本地库 `data/cache/local.db` 的 `日结算单收益测算` 表

## Dependencies

- Python 3.14 with `openpyxl`, `win32com`（入库用）