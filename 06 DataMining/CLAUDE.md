# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

天机数据库查询 + ECharts 可视化 + 电价/竞价空间分析（阶段 06）。包含数据库直查工具、96 点电价提取、日前/实时曲线对比、备用容量分析、潮流断面分析等。

## Scripts

### 数据库查询

| 脚本 | 用法 | 说明 |
|------|------|------|
| `db_viewer.py` | `python db_viewer.py [list\|preset_name\|custom]` | 通用数据库查询 → ECharts HTML。预设：`clearing_price` / `supply_demand` / `boundary` |

### 电价与竞价空间

| 脚本 | 用法 | 说明 |
|------|------|------|
| `extract_prices.py` | `python extract_prices.py` | 从 01/02/03 产出文件提取 96 点电价+竞价空间，生成 `电价对比_MMDD-MMDD.html`。修改 `DATES` 和 `DATE_LABELS` 指定范围 |
| `generate_analysis_html.py` | `python generate_analysis_html.py` | 生成竞价空间+电价+天气综合分析 HTML。依赖 `_tmp_html_data.json`（由外部数据提取流程生成）。搜索 `# DATE_RANGE:` 修改标题和输出文件名 |

### 日内出清计划

| 脚本 | 用法 | 说明 |
|------|------|------|
| `intraday_viz.py` | 直接运行 | 可视化 `shandong_px_intraday_clearing_plan_result` 最近一周数据 |

### extract → gen 数据管线

5 对 extract/gen 脚本遵循统一模式：extract 从数据库查询 → 写 `_tmp_*.json` 到项目根目录 → gen 读取 JSON 生成 ECharts HTML。

| Extract | Gen | 数据内容 | 输出 |
|---------|-----|---------|------|
| `extract_reserve_data.py` | `gen_reserve_html.py` | 备用容量（日前/实际正负备用） | `_tmp_reserve_data.json` → HTML |
| （外部流程） | `gen_powerflow_html.py` | 潮流断面利用率 | `_tmp_powerflow_data.json` → HTML |
| （外部流程） | `gen_sysbackup_html.py` | 系统实时备用容量 | `_tmp_sysbackup_data.json` → HTML |
| （外部流程） | `gen_thermal_backup_html.py` | 火电备用对比 | `_tmp_thermal_data.json` → HTML |

**修改日期范围：** 编辑 extract 脚本顶部的 `START_DATE` / `END_DATE`，然后依次运行 extract → gen。

### DATE_RANGE 标记约定

多个脚本使用 `# DATE_RANGE:` 注释标记需要修改日期的地方，搜索此标记即可定位所有需要改日期的位置。

## 天机数据库

连接信息硬编码在脚本中（`tianrun_new` @ RDS）。关键表见根 CLAUDE.md 中的天机数据库结构。

## 关键数据文件

| 文件 | 来源 | 用途 |
|------|------|------|
| `_tmp_html_data.json` | 外部数据提取流程 | `generate_analysis_html.py` 输入 |
| `_tmp_reserve_data.json` | `extract_reserve_data.py` | `gen_reserve_html.py` 输入 |
| `_tmp_powerflow_data.json` | 外部流程 | `gen_powerflow_html.py` 输入 |
| `_tmp_sysbackup_data.json` | 外部流程 | `gen_sysbackup_html.py` 输入 |
| `_tmp_thermal_data.json` | 外部流程 | `gen_thermal_backup_html.py` 输入 |
| `电价对比_*.html` | `extract_prices.py` | 96 点电价+竞价空间交互图表 |

## 临时文件清理

天机临时查询脚本（如 `_tmp_query.py`）和 `_tmp_*.json` 用完需清理。

## 参考文档

- `电价分析操作手册.md` — 数据来源、数据结构、提取脚本用法、常见问题
- `策略复盘结论.md` — 策略规则汇总、竞价空间锚点、多日对比验证
- `表探索_shandong_pmos_spot_dayahead_supply_demand.md` — 供需表结构探索笔记
- `Peak-valley price difference analysis/rt_price_spread_analysis_2026.md` — 峰谷价差分析