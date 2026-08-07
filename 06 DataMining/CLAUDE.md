# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **注意：** 本目录是阶段 06 的子目录。项目整体架构、通用约定、阶段间依赖、天机数据库结构等信息见根目录 `CLAUDE.md`。本文件仅补充阶段 06 特有的细节。

## Project overview

天机数据库查询 + ECharts 可视化 + 电价/竞价空间分析（阶段 06）。包含数据库直查工具、96 点电价提取、日前/实时曲线对比、备用容量分析、潮流断面分析、相似日分析、预调度分析等。

## Scripts

### 数据库查询

| 脚本 | 用法 | 说明 |
|------|------|------|
| `db_viewer.py` | `python db_viewer.py [list\|preset_name\|custom]` | 通用数据库查询 → ECharts HTML。预设按业务分组：润津储能(`rj_*`)、全省电价(`unify_price`/`gen_price`)、负荷新能源(`dayahead_load`/`actual_load`/`new_energy_rt`)、备用(`reserve`)、预测(`clearing_price`/`supply_demand`/`boundary`)、约束(`trade_constraint`) |

### 电价与竞价空间

| 脚本 | 用法 | 说明 |
|------|------|------|
| `bidding_space_viz.py` | `python bidding_space_viz.py [start] [end]` | 预测竞价空间（默认），从 `shandong_px_spot_dayahead_load_info` 提取 |
| | `python bidding_space_viz.py --actual [start] [end]` | 真实竞价空间，从 `shandong_px_spot_actual_load_info` 提取 |
| | `python bidding_space_viz.py --compare [start] [end]` | 预测vs实际对比，偏差构成分析 |
| `similar_day_analysis.py` | `python similar_day_analysis.py compute` | 计算所有日期竞价空间特征（峰谷窗口、时段） |
| | `python similar_day_analysis.py YYYY-MM-DD` | 生成相似日分析 HTML（含 v2 增强：必开估算、调节机组出力、地板概率） |
| `_similar_day_v2.py` | `python _similar_day_v2.py YYYY-MM-DD` | 增强版相似日分析（独立版，含必开/调节机组估算） |
| `local_db.py` | `python local_db.py sync` | 从远程 MySQL 同步数据到本地 SQLite（data/cache/local.db） |
| | `python local_db.py status` | 查看本地数据库状态 |
| `extract_prices.py` | `python extract_prices.py` | 从 01/02/03 产出文件提取 96 点电价+竞价空间，生成 `电价对比_MMDD-MMDD.html`。修改 `DATES` 和 `DATE_LABELS` 指定范围 |
| `generate_analysis_html.py` | `python generate_analysis_html.py` | 生成竞价空间+电价+天气综合分析 HTML。依赖 `_tmp_html_data.json`（由外部数据提取流程生成）。搜索 `# DATE_RANGE:` 修改标题和输出文件名 |
| `_gen_clearing_panorama.py` | `python _gen_clearing_panorama.py MMDD` | 日前出清全景分析（见根目录 `日前出清全景分析.md`） |
| `_gen_daily_compare.py` | `python _gen_daily_compare.py` | 日运营复盘对比分析（见根目录 `日运营复盘对比分析.md`），修改脚本顶部 DATES 列表 |

### 日内出清计划

| 脚本 | 用法 | 说明 |
|------|------|------|
| `intraday_viz.py` | 直接运行 | 可视化 `shandong_px_intraday_clearing_plan_result` 最近一周数据 |

### 预调度分析（火电 & 储能）

| 脚本 | 用法 | 说明 |
|------|------|------|
| `gen_prescheduling_html.py` | `python gen_prescheduling_html.py` | 从 `_tmp_prescheduling.json`（单日 96 点数据）生成静态 HTML，含分类、排名表、分组曲线、叠加曲线 |
| `gen_prescheduling_page.py` | `python gen_prescheduling_page.py [_tmp_all_results.json] [out.html]` | 生成自包含交互式页面，嵌入所有历史日期预计算数据，支持日期下拉即时切换，无需服务器 |
| `prescheduling_server.py` | `python prescheduling_server.py` | 本地 HTTP 服务器（端口 8765），提供 `/api/dates` + `/api/data?date=` 端点，从数据库实时查询 |

**预调度分析数据管线：**
1. 从 `shandong_px_provincial_prescheduling_results` 全量提取所有日期 96 点数据 → `_tmp_all_prescheduling.json`
2. 预计算分类（classify 函数）→ `_tmp_all_results.json`（含 `dates` 日期列表 + `data` 各日期分类结果）
3. `gen_prescheduling_page.py` 读取 `_tmp_all_results.json` 生成自包含 HTML（嵌入全部数据，无需服务器）

**更新数据：** 数据库有新日期入库时，重新跑第 1-3 步即可刷新 `prescheduling_page.html`。

### 火电 / 地板价分析（研究脚本）

以下脚本用于火电出清、地板价形成机制、调节机组出力等专项研究，非日常管线脚本：

| 脚本 | 用途 |
|------|------|
| `_bikaki_season_analysis.py` | 必开机组季节变化分析（台数/出力/占比随季节变化，CV<5%=必开） |
| `_fire_peak_valley_benchmark.py` | 火电出清峰谷对标（5-7月，日前vs实际火电出清，含电价） |
| `_floor_day_regulating_units.py` | 地板价日调节机组统计（必开/调节分类，谷段出力，单台均值） |
| `_unit_regulating_vs_floor_v2.py` | 单台调节机组出力 vs 地板价区分度（修正版） |
| `_valley_regulating_vs_floor.py` | 谷段调节机组出力 vs 地板价（5-7月验证，核心假设验证） |
| `_gen_thermal_july_continuous.py` | 按连续时序模板生成火电+储能+电价 96 点连续数据 |

**预调度数据覆盖：** `预调度数据爬取情况.txt` 记录 `shandong_px_provincial_prescheduling_results` 数据情况：
- 176 天，2025-07~2026-07-24，3月30日~5月15日、6月9日~7月10日之间有显著缺口
- 稳定期（2026年1-3月）：火电 200-204 台，储能 60-68 台
- 5月恢复后：火电 192-193 台，储能 70 台

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

## 机组分类规则

`shandong_px_provincial_prescheduling_results` 表中机组分类规则：

- **火电机组** — `generator_name` 包含 `机` 或 `#`
- **储能机组** — `generator_name` 包含 `储能` 二字
- **其他** — 不满足以上两条的（风电、光伏、核电等）

连接信息硬编码在脚本中（`tianrun_new` @ RDS）。关键表见根 `CLAUDE.md` 中的天机数据库结构，以及 `天机数据库_常用表速查.md`（A-F 工作流分组速查）。

## 关键数据文件

| 文件 | 来源 | 用途 |
|------|------|------|
| `_tmp_html_data.json` | 外部数据提取流程 | `generate_analysis_html.py` 输入 |
| `_tmp_reserve_data.json` | `extract_reserve_data.py` | `gen_reserve_html.py` 输入 |
| `_tmp_powerflow_data.json` | 外部流程 | `gen_powerflow_html.py` 输入 |
| `_tmp_sysbackup_data.json` | 外部流程 | `gen_sysbackup_html.py` 输入 |
| `_tmp_thermal_data.json` | 外部流程 | `gen_thermal_backup_html.py` 输入 |
| `_tmp_similar_features.json` | `similar_day_analysis.py compute` | `similar_day_analysis.py` 输入（存储所有日期竞价空间特征） |
| `电价对比_*.html` | `extract_prices.py` | 96 点电价+竞价空间交互图表 |
| `output/竞价空间分析结果/预测竞价空间_*.html` | `bidding_space_viz.py` | 预测竞价空间（数据库直查）交互图表 |
| `output/竞价空间分析结果/相似日分析_*.html` | `similar_day_analysis.py` | 相似日分析交互页面（含竞价空间+电价叠加图、雷达图、Top-N 排名表） |

## HTML 输出风格约定

**所有生成的 HTML 文件统一使用白底 Windows 风格**，不使用暗色主题。配色规范：

- 背景色 `#ffffff`，文字色 `#333`，标题色 `#222`
- 图表容器背景 `#fff`，边框 `#ddd`
- 表格：表头 `#f5f5f5`，边框 `#e0e0e0`，文字 `#333`
- ECharts 图表背景 `#fff`，网格线 `#eee`，坐标轴标签 `#666`
- 统计卡片：背景 `#fafafa`，数值色 `#2c7be5`（蓝色强调）
- 不使用 `#0d1117`、`#161b22`、`#c9d1d9` 等暗色系配色
- 字体统一为 `"Microsoft YaHei", "Segoe UI", sans-serif`
- **配色规则：** 每条 series 的线条颜色和 tooltip 弹窗圆点颜色必须一致（`lineStyle.color` = `itemStyle.color` = 同一色值），不允许线和点颜色不一致。参见全局 `CLAUDE.md`「ECharts 图表配色规则」。

## 临时文件清理

天机临时查询脚本（如 `_tmp_query.py`）和 `_tmp_*.json` 用完需清理。

## 参考文档

- `电价分析操作手册.md` — 数据来源、数据结构、提取脚本用法、常见问题
- `策略复盘结论.md` — 策略规则汇总、竞价空间锚点、多日对比验证
- `表探索_shandong_pmos_spot_dayahead_supply_demand.md` — 供需表结构探索笔记
- `Peak-valley price difference analysis/rt_price_spread_analysis_2026.md` — 峰谷价差分析