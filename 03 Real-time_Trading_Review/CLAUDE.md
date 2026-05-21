# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

山东电力现货市场储能电站收益复盘工具。从发电侧实时交易结果查询文件中提取出力/电价数据，填入机组组合收益复盘模板，生成日报。

## Data Flow

```
assets/发电侧实时交易结果查询.xls  ──→  出力列 → 充放电曲线列
                                     ──→  电价列 → 统一结算日前 + 节点日前电价列
assets/0505-实时机组组合收益复盘.xlsx  ──→  (模板)
                                     ──→  output/MMDD-实时机组组合收益复盘.xlsx
```

### Sheet Mapping

源文件 sheet 0（苏留润津独立储能电站）96 个时点（00:15~24:00）：

| 源列 | → 模板列 (sheet 1「报价及预中标」, row 2-97) |
|------|---------------------------------------------|
| col 1 出力 | col N (14) 充放电曲线 |
| col 3 电价 | col J (10) 统一结算日前 |
| col 3 电价 | col K (11) 节点日前电价 |

## Processing

使用 pandas 读取 `.xls` 源数据，openpyxl 读写 `.xlsx` 模板（保留格式）。模板 sheet 1 中列 J/K/N 的第 2~97 行为时点数据行。

## Directory Convention

- `assets/` — 源数据 `.xls` 和复盘模板 `.xlsx`
- `output/` — 生成的复盘文件，按日期命名 `MMDD-实时机组组合收益复盘.xlsx`
