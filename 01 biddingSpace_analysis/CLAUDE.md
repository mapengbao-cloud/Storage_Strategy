# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Script

```
python generate.py MMDD                          # 预测（自动查找源文件）
python generate.py MMDD <source_path>            # 显式指定源文件
python generate.py MMDD actual                   # 实际（自动查找）
python generate.py MMDD actual <source_path>     # 显式指定实际源文件
```

## Sheet mapping（源 → 模版 Sheet1）

**预测文件**（`YYYY-MM-DD负荷信息预测.xls`，4 sheets，row-oriented，`df.iloc[2, 1:]` 取 96 值）：

| Source sheet | Target row |
|---|---|
| 直调负荷 | Row 3 |
| 联络线受电负荷 | Row 4 |
| 风电总加 | Row 5 |
| 光伏总加 | Row 6 |

**实际文件**（`MMDD-电网运行实际信息.xlsx`，1 sheet `负荷信息`，column-oriented，rows 1-96）：

| Source column | Target row |
|---|---|
| C (2) 直调负荷 | Row 3 |
| D (3) 联络线受电 | Row 4 |
| E (4) 风电 | Row 5 |
| F (5) 光伏 | Row 6 |

Row 7（竞价空间）为公式 `=<col>3-<col>4-<col>5-<col>6`，由 `_write_formulas()` 写入。

> **竞价空间标准定义（5 项）**：直调负荷 − (联络线受电 + 风电 + 光伏 + 核电 + 自备机组)。
> 本脚本 Excel 源文件仅含 4 个分项（无核电/自备），故模板 Row 7 公式为 4 项子集。
> 完整 5 项定义用于数据库路径：`src/business/bidding_space.py` 与 `06 DataMining/local_db.py`。

## Template

`assets/输出模版-0521-竞价空间分析.xlsx` — Sheet1: 97 cols (A=label, B-CS=96 time points), 7 rows. 只覆写 rows 3-6 数据值 + row 7 公式，其他不变。

## 关键陷阱

- 实际文件的 `负荷信息` sheet 中所有数值以**字符串**存储（如 `"62191.80"`），`_read_actual()` 已用 `float()` 转换，不要额外判断 `isinstance(val, str)`。
- 模版包含合并单元格（row 1-2 的标题区），脚本只写 rows 3-7，不涉及 MergedCell 区域。