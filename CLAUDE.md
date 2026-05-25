# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

山东电力现货市场储能电站（德州润津储能科技有限公司）收益复盘与竞价空间分析数据管线。5 个阶段按顺序串行：

```
01 biddingSpace_analysis    → 竞价空间分析（负荷预测 → 竞价空间计算）
02 Dayahead_Trading_Review  → 日前机组组合收益复盘
03 Real-time_Trading_Review → 实时机组组合收益复盘
04 Daily_Settlement_Review  → 日结算收益复盘（汇总结算单 + 日前/实时复盘）
05 Review_Dashboard         → 周报/收益统计表（汇总各阶段复盘结果到主表）
```

每个阶段是独立子目录，有自己的 `CLAUDE.md`（含该阶段的详细 sheet mapping 和处理逻辑）、`assets/`（源数据 + 输出模版）、`output/`（生成文件）。

## 项目级约定

### 数据格式规则

1. **源数据必须转为数字格式** — 从 `.xls`/`.xlsx` 源文件读取的所有数据，写入目标文件前必须转为 `int` 或 `float`，确保可直接参与 Excel 公式计算，绝不能保留文本格式。使用 `pd.to_numeric()`、`.astype(float)`、`int()`、`float()` 等转换。遇到 `None`、空单元格、非数字字符串时，按上下文决定填 `0` 或抛出明确错误。
2. **模版保护** — `assets/` 中以 `输出模版-` 前缀命名的文件是输出模版。生成输出时仅替换数据内容，不改变模版的数字格式、单元格样式（字体/边框/填充/对齐）、列宽行高、合并单元格、条件格式和公式。使用选择性覆写（只写源数据有值的单元格），不用全清再填充。

### openpyxl 关键陷阱

- **MergedCell 不可写** — 包含合并单元格的 sheet 中，被合并区域内的非左上角单元格是 `MergedCell` 类型，写入会抛 `'MergedCell' object attribute 'value' is read-only`。遍历时用 `ws.cell(row=r, column=c)` 语法（而非 bracket `ws['A1']`），并通过 `type(cell).__name__ == 'MergedCell'` 检查并跳过。这是阶段 01/03/04 的常见坑。
- **跨文件公式无法解析** — 源文件中的公式引用其他工作簿时，`data_only=True` 也会返回 `None`（无缓存值）。此时需用 `data_only=False` 读取原始数据，在代码中复现公式计算逻辑（见阶段 05 的 `compute_summary_values()`）。
- **`data_only=True` vs `data_only=False`** — 读取有公式的源文件时要判断：如果公式的缓存值有效，用 `data_only=True`；如果缓存为空（跨文件公式），用 `data_only=False` 读公式引用的原始数据自行计算。

### 目录约定

- `assets/` — 源数据文件（`.xls`/`.xlsx`）和输出模版（`输出模版-*.xlsx`）
- `output/` — 生成的结果文件，按 `MMDD-*.xlsx` 格式命名

### 依赖

所有脚本仅依赖 Python 标准库 + `pandas` + `openpyxl`（均已预装，Python 3.14）。

## 各阶段脚本

| 阶段 | 脚本 | 用法 |
|------|------|------|
| 01 | 无（Claude 直接操作 openpyxl） | 读取负荷预测 `.xls` → 写入竞价空间模版 |
| 02 | `02 Dayahead_Trading_Review/generate.py` | `python generate.py MMDD [src_path]`（用日期特定模版） |
| 02 | `02 Dayahead_Trading_Review/batch_generate.py` | `python batch_generate.py`（批量处理 0508-0520，用固定模版 `0505-日前机组组合收益复盘.xlsx`） |
| 03 | 无（Claude 直接操作 openpyxl） | 读取实时交易 `.xls` → 写入实时复盘模版 |
| 04 | `04 Daily_Settlement_Review/generate_review.py` | `python generate_review.py`（批量处理脚本内 DATES 列表） |
| 05 | `05 Review_Dashboard_and _weeklyreport/process_data.py` | `python process_data.py [--day-ahead MMDD-MMDD] [--real-time MMDD-MMDD] [--settlement MMDD-MMDD]` |

阶段 01 和 03 无独立脚本，由 Claude 按对应 `CLAUDE.md` 中的 sheet mapping 直接操作 `openpyxl` 完成。

**阶段 02 `generate.py` vs `batch_generate.py`：** 前者用日期特定模版（`assets/MMDD-日前机组组合收益复盘.xlsx`），后者用固定模版 `0505` 且自动处理带编号后缀的源文件（如 `0509-发电侧日前交易结果查询 (1).xls`）。

**阶段 05 增量更新机制：** `process_data.py` 以上一轮 `output/` 中的文件为基础进行增量更新（而非每次从干净模版重新生成）。首次运行时 `output/` 为空，则从 `assets/` 中的模版开始。这样带 filter 的单类型更新（如 `--settlement 0518-0518`）不会覆盖其他类型已写入的数据。

**阶段 05 文件锁定回退：** 如果输出文件 `山东夏津储能收益统计表.xlsx` 被 Excel 占用，`process_data.py` 自动回退到带时间戳的文件名（如 `山东夏津储能收益统计表_20260521_143000.xlsx`）。运行前需关闭 Excel。

**阶段 05 源文件位置：** `process_data.py` 从自己的 `assets/` 目录读取源文件，不是从各阶段的 `output/` 读取。运行前需将 02/03/04 的产出文件复制到 05 的 `assets/` 下。

**目标文件日期格式：** 统计表 `山东夏津储能收益统计表.xlsx` 中 A 列日期存储为 Excel 整数序列号（如 `46163`），不是 `datetime` 对象。`process_data.py` 中的 `find_date_in_target()` 已同时支持两种格式。

## 日结算文件命名变体

阶段 05 的源文件匹配同时接受两种文件名：
- `MMDD-日结算收益复盘.xlsx`（标准）
- `MMDD-日结算收益复盘-.xlsx`（尾部带 `-` 的变体）

## 阶段 04 模版命名

模版文件为 `assets/输出模版-0504-日结算收益复盘.xlsx`（带 `输出模版-` 前缀），`generate_review.py` 中引用为 `0504-日结算收益复盘.xlsx`，需注意名称匹配。

阶段 04 生成需要三个数据源：充电结算单 `.xlsx`、放电结算单 `.xlsx`、对应日期的实时复盘 `.xlsx`（从 03 的 `output/` 获取）。

## 源文件来源

用户提供的源数据文件常位于 `d:\Personal\下载\`（带编号后缀如 ` (1)`, ` (2)`），处理时直接使用绝对路径读取，无需复制到项目目录。生成结果写入对应阶段的 `output/` 目录。

## 权限配置

项目根目录 `.claude/settings.local.json` 已预配 Bash（python/git/ls）、Read/Write/Edit（项目 + d:\Personal）、Glob/Grep 权限，覆盖本项目常见操作，减少确认步骤。

## 数据流向（阶段间依赖）

- 02 的产出 → 05 的「日前」列（B-R），同时也被 04 引用
- 03 的产出 → 05 的「实时」列（S-AI），同时也被 04 引用
- 04 的产出 → 05 的「日结算」列（AJ-BA），同时从 02/03 的复盘文件中读取 `报价及预中标` 原始数据重新计算汇总值（因跨文件公式无法解析，用 `compute_summary_values()` 复现计算逻辑）
- `compute_summary_values()` 从 `报价及预中标` sheet 原始数据（J 列电价、N 列充放电需求）和 `充放测算` I8-I14 参数重新计算 17 个汇总值，等价于源文件中 row 4 的公式结果。该 sheet 通过名称子串 `'报价'` + `'预中标'` 定位（非索引），因为日结算文件比日前/实时文件多出额外 sheet。
