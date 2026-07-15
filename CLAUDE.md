# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 关键行为规则（最高优先级）

**任务执行前置检查：** 本项目为重复性数据处理工作，绝大部分任务已有明确文档。执行任何任务前，**必须先**：
1. 检索 `memory/` 中是否有相关记忆
2. 检索项目根目录 `*.md` 文档（`收益测算工作流程.md`、`竞价空间分析工作流程.md` 是最核心的两份工作流程文档）
3. 检索 `CLAUDE.md` 中是否有对应流程说明
4. 查看相关脚本/代码的已有实现模式

**禁止**在未查阅文档的情况下直接探索文件结构、读取 Excel 内容、询问用户已有明确答案的问题。先查文档，再动手。

**任务完成即停止：** 任何脚本/命令执行完成后，如果输出中显示成功标志（如 `Saved:`、`done`、退出码 0），任务即为完成。立即告知用户结果并停止，**绝对禁止**以下行为：
- 禁止运行验证命令（如 `echo "done"`、`python -c "import openpyxl..."` 等）
- 禁止反复确认文件是否生成
- 禁止循环检查输出内容
- 禁止在成功后追加任何额外操作

一次任务 = 一次执行 + 一次结果汇报。**没有验证环节**。脚本的输出本身就是验证。

## Project overview

山东电力现货市场储能电站（德州润津储能科技有限公司）收益复盘与竞价空间分析数据管线。6 个阶段按顺序串行：

```
01 biddingSpace_analysis    → 竞价空间分析（负荷预测 → 竞价空间计算）
02 Dayahead_Trading_Review  → 日前机组组合收益复盘
03 Real-time_Trading_Review → 实时机组组合收益复盘
04 Daily_Settlement_Review  → 日结算收益复盘（汇总结算单 + 日前/实时复盘）
05 Review_Dashboard         → 周报/收益统计表（汇总各阶段复盘结果到主表）
06 DataMining              → 天机数据库查询 + ECharts 可视化 + 峰谷价差分析
```

## 新架构（src/ — 推荐使用）

`src/` 是统一重构后的代码，包含共享模块、业务逻辑、管线编排、CLI 入口。

### 统一 CLI

```bash
python -m src.cli run 0605                    # 单日全流程（6 阶段）
python -m src.cli run 0605-0612               # 日期范围
python -m src.cli run 0605 --stages 01,02,03  # 指定阶段
python -m src.cli run 0605 --dry-run          # 预览（不执行）
python -m src.cli run 0605 --force            # 重跑已完成的阶段
python -m src.cli evaluate 0605               # 单日策略评估
python -m src.cli evaluate 0605 --with-risk  # 含 DA-RT 偏差风险评估
python -m src.cli backtest 0518-0603          # 策略回测
python -m src.cli risk-profile 0518-0603      # DA-RT 偏差风险画像
python -m src.cli validate 0522-0531          # 检查缺失源文件
python -m src.cli status                      # 管线状态
python -m src.cli stage 03 0605               # 单跑一个阶段（stage 01-05）
```

> `stage` 子命令只覆盖 01-05；阶段 06（数据挖掘）是 `src/stages/stage06_datamining/` 子包，独立于 CLI 管线，用 `06 DataMining/` 下脚本直接运行。

### 核心模块

| 模块 | 路径 | 职责 |
|------|------|------|
| 配置 | `config/settings.yaml`, `parameters.yaml` | 数据库连接、业务参数、策略阈值 |
| 数据模型 | `src/data/models.py` | `TimeSeries96`, `DailyRevenue`, `StrategySignal` 等 10 个 dataclass |
| 数据库 | `src/data/db.py` | 连接池 + 8 个预设查询（价格、结算、供需、备用等） |
| 文件读取 | `src/data/readers.py` | 6 个统一读取器（预测负荷、实际负荷、交易结果、结算单、电价、竞价空间） |
| 文件写入 | `src/data/writers.py` | 安全 Excel 写入（跳过 MergedCell + 公式保护） |
| 收益计算 | `src/business/revenue.py` | `compute_revenue()` — **唯一真相源**，所有阶段共用 |
| 容量分摊 | `src/business/capacity.py` | `compute_J_val()` / `compute_J_val_from_workbook()` |
| 竞价空间 | `src/business/bidding_space.py` | `compute_bidding_space()`, `find_peak_valley_window()` |
| 策略引擎 | `src/business/strategy.py` | `evaluate_strategy()` — 3 条件策略评估 |
| 验证 | `src/business/validation.py` | `validate_revenue_vs_excel()` — 与 Excel 公式交叉验证 |
| 管线编排 | `src/pipeline/orchestrator.py` | 自动化执行全部 6 阶段 |
| 策略回测 | `src/backtesting/engine.py` | 历史数据回测 + 绩效指标 |
| Excel 工具 | `src/utils/excel_utils.py` | `is_merged()`, `safe_write_cell()`, `copy_sheet_data()` |
| 日期工具 | `src/utils/date_utils.py` | MMDD/ISO/Excel 序列号转换，96 点时间标签 |
| 数值工具 | `src/utils/numerics.py` | `safe_float/int`, `round_value`, `PCT_COLUMNS` |
| 气象 | `src/utils/weather.py` | Open-Meteo API 客户端 |

**src/ 未在上方列出的补充模块**（在各自子包内，按需使用）：
- `src/business/revenue_types.py`、`conditions.py`、`risk.py` — 收益类型定义、策略条件、DA-RT 偏差风险
- `src/pipeline/stages.py`、`state.py` — 阶段分发与管线状态持久化
- `src/backtesting/metrics.py` — 回测绩效指标
- `src/stages/stage06_datamining/visualize.py` — 阶段 06 数据可视化

### 模版

所有 Excel 模版集中在 `assets/templates/`，按业务功能分子目录：

| 子目录 | 内容 | 说明 |
|--------|------|------|
| `竞价空间/` | `竞价空间分析.xlsx` | 阶段 01 竞价空间分析 |
| `收益测算/` | 日前/实时/日结算收益复盘模板（1-7月） | 按月匹配，不同月份列数不同 |
| `月报周报/` | 统计表、周报模板、周报要求 | 阶段 05 统计表 + 周报生成 |
| `调频测算/` | 调频收益及报价测算模板、策略文档 | 调频策略分析 |

**关键：** 收益测算模板按月份和结算单版本区分：
- 日结算：1-7月各有独立模板，5月25日起结算单增加2列（充电）和5列（放电），模板分「日前」和「日后」
- 实时/日前出清：1-7月各有独立模板，每月参数（H12/H13等）不同，必须严格按月份对齐

### 数据目录

- `data/raw/YYYY-MM-DD/` — 按日期组织的源文件（已通过 `python -m src.data.migrate --copy --run` 迁移）
- `data/cache/` — SQLite 数据库查询缓存（`local.db`）
- `output/日结算单收益测算/` — 日结算复盘 + 月度汇总
- `output/实时出清收益测算/` — 实时出清收益测算
- `output/日前出清收益测算/` — 日前出清收益测算
- `output/竞价空间分析结果/` — 竞价空间 HTML 可视化
- `output/reports/` — 汇总报告和可视化
- `output/日结算单收益测算_周报_MMDD-MMDD.xlsx` — 周报文件（根目录）

### 收益计算验证

`compute_revenue()` 已通过 0607 日结算数据与旧管线输出逐项交叉验证，14 项全匹配（偏差 < 0.01）。

## 旧阶段目录（01-06 — 保留兼容）

旧阶段目录保留，其脚本可独立运行。新任务优先使用 `src/` 模块和 CLI。

## 三大收益测算体系（核心工作流）

详见 `收益测算工作流程.md`。三大体系共享同一套模式：**天机 MySQL 取数 → 按月匹配模板 → 写入 Excel → COM 刷新公式 → openpyxl 读取 → SQLite 入库**。

### 日结算单复盘

- **数据源**：充放电结算单 Excel（`6052-YYYY-MM-DD德州润津储能科技有限公司结算单-.xlsx`）
- **模板**：`assets/templates/收益测算/日结算收益复盘-X月.xlsx`（按月 + 结算单版本匹配）
- **输出**：`output/日结算单收益测算/MMDD-日结算收益复盘.xlsx`
- **入库表**：`日结算单收益测算`（19列）、`用电结算单`（25行/天）、`发电结算单`（97行/天）

### 实时出清收益测算

- **数据源**：天机 MySQL `shandong_px_realtime_clearing_results_query`（润津 96 点）
- **模板**：`assets/templates/收益测算/实时出清收益测算-X月.xlsx`
- **输出**：`output/实时出清收益测算/MMDD-实时出清收益测算.xlsx`
- **入库表**：`实时出清收益测算`（17列）、`润津实时出清结果`（原始数据）

### 日前出清收益测算

- **数据源**：天机 MySQL `shandong_px_reliable_clearing_unit_data`（润津主单元，96 点）
- **模板**：`assets/templates/收益测算/日前出清收益测算-X月.xlsx`
- **输出**：`output/日前出清收益测算/MMDD-日前出清收益测算.xlsx`
- **入库表**：`日前出清收益测算`（17列）、`润津日前出清结果`（原始数据）

> **重要：** 实时/日前出清生成 Excel 时必须从**天机远程 MySQL** 直接取数，不能从本地库取数。生成 Excel 后再同步原始数据到本地库。

### COM 刷新（必须步骤）

所有收益测算 Excel 的 Row 4 全是跨 sheet 公式，openpyxl 无法计算。必须用 `win32com` 调用 Excel 引擎打开、计算、保存后，`openpyxl(data_only=True)` 才能读到缓存值：

```python
import win32com.client, pythoncom
excel = win32com.client.Dispatch('Excel.Application', pythoncom.CoInitialize())
excel.Visible = False; excel.DisplayAlerts = False
wb = excel.Workbooks.Open(path)
wb.RefreshAll(); excel.CalculateUntilAsyncQueriesDone()
wb.Save(); wb.Close()
excel.Quit()
```

### 本地数据库

SQLite 数据库位于 `data/cache/local.db`，共 7 张表：

| 表名 | 说明 |
|------|------|
| `日结算单收益测算` | 日结算复盘（充放测算 Row 4，19列） |
| `用电结算单` | 充电日清算费用（25行/天） |
| `发电结算单` | 放电日清算费用（97行/天） |
| `实时出清收益测算` | 实时出清收益（17列） |
| `日前出清收益测算` | 日前出清收益（17列） |
| `润津实时出清结果` | 天机实时出清原始数据 |
| `润津日前出清结果` | 天机日前出清原始数据 |

## 竞价空间分析体系

详见 `竞价空间分析工作流程.md`。四层分析：预测 → 实际 → 对比 → 相似日。

### 数据同步

```bash
cd "06 DataMining"
python local_db.py sync --tables bidding_space,price --start YYYY-MM-DD --end YYYY-MM-DD
```

本地表：`bidding_space_forecast`、`bidding_space_actual`、`dayahead_price`、`realtime_price`

### 可视化生成

```bash
python bidding_space_viz.py                              # 预测竞价空间
python bidding_space_viz.py --actual                     # 实际竞价空间
python bidding_space_viz.py --compare                    # 预测 vs 实际对比
python bidding_space_viz.py --local                      # 读本地 SQLite（不走远程）
```

### 相似日分析

```bash
python similar_day_analysis.py compute                   # 计算所有日期特征
python similar_day_analysis.py 2026-06-21                # 生成相似日分析 HTML
```

5 维度加权：2h谷值(30%) + 2h峰值(25%) + 谷值时段(15%) + 峰值时段(10%) + 曲线形状(20%)

## 周报生成

### 日结算单收益测算周报

1. 确认 `local.db` 中已有目标日期范围的日结算数据
2. 复制上周周报模板 → `output/日结算单收益测算_周报_MMDD-MMDD.xlsx`
3. 逐行写入 Row 2-8 的 A-T 列（20列），Row 9 公式自动计算
4. 生成文本周报 → `output/日结算单收益测算_周报_MMDD-MMDD.txt`

文本周报格式（数据来源：周报 Excel 的 Row 9 公式计算值）：
```
MMDD-MMDD
上周收益：P9/10000万（其中过网费、容量分摊等|S9|/10000万）
实时市场：Q9/10000万（充电量：|C9|MWh；放电量：L9MWh；价差：O9元/MWh）
```

### 周报要求

模板：`assets/templates/月报周报/周报要求.txt`

## 调频收益测算

模板：`assets/templates/调频测算/调频收益及报价测算_20260527.xlsx`（7 sheets）
策略文档：`assets/templates/调频测算/调频策略.md`

核心公式：**最低申报价格 = -(现货损益均值 + 容量分摊费用均值) / 综合性能指标均值 / 调节深度均值**

> 润津储能目前**没有调频收入**。调频相关表无对应润津数据。

## 项目级约定

### 数据格式规则

1. **源数据必须转为数字格式** — 从 `.xls`/`.xlsx` 源文件读取的所有数据，写入目标文件前必须转为 `int` 或 `float`，确保可直接参与 Excel 公式计算，绝不能保留文本格式。使用 `pd.to_numeric()`、`.astype(float)`、`int()`、`float()` 等转换。遇到 `None`、空单元格、非数字字符串时，按上下文决定填 `0` 或抛出明确错误。
2. **模版保护** — `assets/` 中以 `输出模版-` 前缀命名的文件是输出模版。生成输出时仅替换数据内容，不改变模版的数字格式、单元格样式（字体/边框/填充/对齐）、列宽行高、合并单元格、条件格式和公式。使用选择性覆写（只写源数据有值的单元格），不用全清再填充。

### openpyxl 关键陷阱

- **MergedCell 不可写** — 包含合并单元格的 sheet 中，被合并区域内的非左上角单元格是 `MergedCell` 类型，写入会抛 `'MergedCell' object attribute 'value' is read-only`。遍历时用 `ws.cell(row=r, column=c)` 语法（而非 bracket `ws['A1']`），并通过 `type(cell).__name__ == 'MergedCell'` 检查并跳过。这是阶段 01/03/04 的常见坑。
- **跨文件公式无法解析** — 源文件中的公式引用其他工作簿时，`data_only=True` 也会返回 `None`（无缓存值）。此时需用 `data_only=False` 读取原始数据，在代码中复现公式计算逻辑（见阶段 05 的 `compute_summary_values()`）。
- **`data_only=True` vs `data_only=False`** — 读取有公式的源文件时要判断：如果公式的缓存值有效，用 `data_only=True`；如果缓存为空（跨文件公式），用 `data_only=False` 读公式引用的原始数据自行计算。
- **电网运行实际信息文件中的数据是字符串** — `MMDD-电网运行实际信息.xlsx` 的 `负荷信息` sheet 中，所有数值（直调负荷、联络线受电、风电、光伏等）以**字符串格式**存储（如 `"62191.80"`）。读取时需用 `float(val)` 转换，不能按 `isinstance(val, str)` 判断为无效值。

### 目录约定

- `assets/` — 源数据文件（`.xls`/`.xlsx`）和输出模版（`输出模版-*.xlsx`）
- `output/` — 生成的结果文件，按 `MMDD-*.xlsx` 格式命名

### ECharts 图表配色规则

**所有 HTML 图表的每条 series，其线条颜色、tooltip 弹窗中的圆点颜色、symbol 颜色必须保持一致，使用同一颜色。**

- `lineStyle.color` = `itemStyle.color` = 同一色值，不可出现线条和弹窗点颜色不一致的情况
- 多系列图表中，每条 series 独立配色，但自己内部线+点同色
- 此规则适用于所有 HTML 生成脚本（`_gen_clearing_panorama.py`、`bidding_space_viz.py`、`similar_day_analysis.py`、`generate_analysis_html.py` 等）

### 依赖

所有脚本仅依赖 Python 标准库 + `pandas` + `openpyxl` + `pymysql`（均已预装，Python 3.14）。Python 包管理统一用 `nv` 命令（`nv list`、`nv install`、`nv uninstall`），不用 `pip`。

## 各阶段脚本

| 阶段 | 脚本 | 用法 |
|------|------|------|
| 01 | `01 biddingSpace_analysis/generate.py` | `python generate.py MMDD [actual] [src_path]` |
| 02 | `02 Dayahead_Trading_Review/generate.py` | `python generate.py MMDD [src_path]`（用日期特定模版） |
| 02 | `02 Dayahead_Trading_Review/batch_generate.py` | `python batch_generate.py`（批量处理，用固定模版 `输出模版-0505-日前机组组合收益复盘.xlsx`） |
| 03 | `src/stages/stage03_realtime.py` | 复用 Stage 02 共享函数，仅 40 行 |
| 04 | `04 Daily_Settlement_Review/generate_review.py` | `python generate_review.py`（批量处理脚本内 DATES 列表） |
| 05 | `05 Review_Dashboard_and _weeklyreport/process_data.py` | `python process_data.py [--day-ahead MMDD-MMDD] [--real-time MMDD-MMDD] [--settlement MMDD-MMDD]` |
| 06 | `06 DataMining/db_viewer.py` | `python db_viewer.py [list|preset_name|custom]` — 天机数据库查询 + ECharts HTML 可视化 |
| 06 | `06 DataMining/extract_prices.py` | `python extract_prices.py` — 提取日前/实时电价 + 竞价空间 96 点数据，生成 ECharts 交互 HTML |
| 06 | `06 DataMining/generate_analysis_html.py` | `python generate_analysis_html.py` — 生成竞价空间+电价+天气综合分析 HTML（日期范围见 `DATE_RANGE:` 标注）|
| 06 | `06 DataMining/intraday_viz.py` | 可视化 `shandong_px_intraday_clearing_plan_result` 最近一周日内出清计划数据 |
| 06 | `06 DataMining/extract_reserve_data.py` | 从 tianrun_new 提取备用容量数据（日前/实际正负备用），输出 `_tmp_reserve_data.json` |
| 06 | `06 DataMining/gen_reserve_html.py` | 读取 `_tmp_reserve_data.json`，生成备用容量分析 HTML |
| 06 | `06 DataMining/gen_powerflow_html.py` | 读取 `_tmp_powerflow_data.json`，生成潮流断面利用率分析 HTML |
| 06 | `06 DataMining/gen_sysbackup_html.py` | 读取 `_tmp_sysbackup_data.json`，生成系统实时备用容量分析 HTML |
| 06 | `06 DataMining/gen_thermal_backup_html.py` | 读取 `_tmp_thermal_data.json`，生成火电备用对比分析 HTML |
| 06 | `06 DataMining/gen_prescheduling_html.py` | `python gen_prescheduling_html.py` — 从 `_tmp_prescheduling.json` 生成火电&储能预调度分析静态 HTML |
| 06 | `06 DataMining/gen_prescheduling_page.py` | `python gen_prescheduling_page.py [_tmp_all_results.json] [out.html]` — 生成自包含交互式预调度分析页面，嵌入所有历史日期数据，支持日期下拉切换 |
| 06 | `06 DataMining/prescheduling_server.py` | `python prescheduling_server.py` — 本地 HTTP 服务器（端口 8765），提供 `/api/dates` 和 `/api/data?date=` 端点，供页面实时从数据库刷新 |
| 06 | `06 DataMining/bidding_space_viz.py` | `python bidding_space_viz.py [START END]`（预测）/ `--actual`（真实）/ `--compare`（对比）/ `--local`（读本地 SQLite 不走远程 MySQL）。从天机库查竞价空间 + 润津电价，生成 ECharts HTML |
| 06 | `06 DataMining/similar_day_analysis.py` | `python similar_day_analysis.py compute`（重算特征 → `_tmp_similar_features.json`）/ `python similar_day_analysis.py YYYY-MM-DD [--top N] [--recompute]`（生成相似日分析 HTML，含竞价空间+电价叠加图、雷达图、可排序 Top-N 表） |
| 06 | `06 DataMining/local_db.py` | `python local_db.py sync [--start --end --tables bidding_space|price|...]` / `python local_db.py status` — 远程 MySQL → 本地 SQLite (`data/cache/local.db`) 同步 |
| 06 | `06 DataMining/_gen_weekly_weather.py` | `python _gen_weekly_weather.py` — Open-Meteo 抓取山东 7 市周气象预报，生成 `{MMDD-MMDD}周气象预报.html` |

阶段 03 **已脚本化**：`src/stages/stage03_realtime.py`（复用 Stage 02 的共享 `_generate_trading_review()` 函数，仅 40 行）。

**阶段 06 `extract → gen` 日期范围改法：** 多数 `extract_*.py` / `gen_*.html.py` 在脚本顶部用 `START_DATE`/`END_DATE` 或 `DATES` 列表控制范围，`generate_analysis_html.py` 用 `# DATE_RANGE:` 注释标记。改完 extract 须重跑 extract→gen 两步。

**阶段 01 竞价空间分析文件命名规则（重要）：**

| 数据源 | 输出文件名格式 | 说明 |
|--------|---------------|------|
| 负荷预测信息（`负荷信息预测.xls`） | `MMDD-竞价空间分析(预测).xlsx` | 基于日前预测数据 |
| 电网运行实际信息（`电网运行实际信息.xlsx`） | `MMDD-竞价空间分析(实际).xlsx` | 基于事后真实运行数据 |

> 预测和实际文件必须严格区分命名，不可混淆。实际数据用于事后验证预测准确性和策略复盘。

**阶段 02 `generate.py` vs `batch_generate.py`：** 前者用日期特定模版（`assets/MMDD-日前机组组合收益复盘.xlsx`），后者用固定模版 `输出模版-0505-日前机组组合收益复盘.xlsx` 且自动处理带编号后缀的源文件（如 `0509-发电侧日前交易结果查询 (1).xls`）。

**阶段 04 模版（3-4 sheet）：** 模板位于 `assets/templates/收益测算/`，按月份匹配（如 `日结算收益复盘-6月.xlsx`）。含 3-4 个 sheet：`充放测算`、`充电日清算费用`、`放电日清算费用`、`容量分摊系数`（部分模板）。生成需要三个数据源：充电结算单 `.xlsx`（→ `充电日清算费用`）、放电结算单 `.xlsx`（→ `放电日清算费用`）、实时复盘 `.xlsx`（→ J4 容量分摊系数 + I8-I14 参数）。J4 通过 `compute_J4()` 从实时复盘文件的 `容量分摊系数` 和 `报价及预中标` 加权计算得到。

**阶段 06 `db_viewer.py`：** 通过 pymysql 连接天机数据库（`tianrun_new`），支持预设查询（`clearing_price` / `supply_demand` / `boundary`）和自定义 SQL，生成 ECharts 交互式折线图 HTML。`Peak-valley price difference analysis/` 下有峰谷价差分析 HTML。天机临时查询脚本用完需清理（如 `_tmp_query.py`）。

**阶段 06 天机数据库结构：** 参考 `天机数据库_山东相关表分类.txt`（120+ 张山东相关表的分类索引）。关键表：
- `shandong_px_spot_dayahead_clearing_price` — **日前出清价格**（统一结算价），按 `member_id` 区分电站，96 时段。无储能电站字段；润津 member_id = `b9e64e64a713458eba94c9af05c0a757`
- `shandong_px_spot_dayahead_clearing_quantity` — 日前出清电量，同上结构
- `shandong_px_spot_realtime_clearing_price` / `_quantity` — 实时出清（同上）
- `shandong_px_intraday_clearing_plan_result` — 储能充放电计划
- `shandong_px_statement_spot_daily_v2` — 每日结算单（98 行，含日前/实时清算量价差、调频分摊等字段，但润津的调频字段均为 NULL）
- `shandong_px_statement_spot_daily_v3` — **当前主力日结算数据源**（96 点 × 36 个 `analysis_field`），按 `current_unit` 区分「发电」（96 时段）和「用电」（24 整点时段）。关键字段：f14=实时清算量，f15=清算价合计，f16=收入/支出，f19=电价(元/MWh)，f35=结算量，f36=结算收入。净收益 = 发电 f36 - 用电 f36。润津 member_id = `b9e64e64a713458eba94c9af05c0a757`
- `shandong_px_spot_surveillance_dayahead_generation_price_v2` — 全省经济性出清电价
- `shandong_pmos_spot_dayahead_supply_demand` / `shandong_pmos_spot_actual_supply_demand` — 供需（预测/实际）
- `shandong_px_spot_dayahead_load_info` / `shandong_px_spot_actual_load_info` — 负荷（日前/实际）
- `shandong_px_tuning_market_dayahead_clearing_price` — 调频市场日前出清价格

**阶段 06 输出页面：**
- `润津储能_2026年6月_日结算汇总.html` — 全月日结算汇总（v3 数据源），汇总表 + 每日 4 图（用电在上、发电在下），日期切换
- `0612-0618周气象预报.html` — 山东 7 市均值周气象预测（Open-Meteo），含辐照度/风速/温湿度/云量热力图
- `竞价空间_电价_天气综合分析_0517-0607.html` — 竞价空间+电价+天气综合分析（`generate_analysis_html.py` 生成）

**阶段 06 `generate_analysis_html.py`：** 生成竞价空间+电价+天气综合分析 HTML。依赖外部数据提取流程生成的 `_tmp_html_data.json`（放在项目根目录），含 3 个字段：`data`（96 点曲线数组）、`weather`（Open-Meteo 天气日数据）、`timeLabels`（96 个时间标签）。搜索 `# DATE_RANGE:` 可找到需要修改日期范围的 2 处（标题 + 输出文件名）。

**阶段 06 `extract_prices.py`：** 提取日前/实时电价 + 竞价空间 96 点数据，生成 `电价对比_MMDD-MMDD.html`（ECharts 交互图表，支持日期切换、四条曲线独立开关、统计栏）。修改脚本顶部的 `DATES` 列表和 `DATE_LABELS` 字典指定日期范围。数据源：
- 日前/实时电价：从 `02/03 Dayahead/Real-time_Trading_Review/output/MMDD-*-复盘.xlsx` 的 `报价及预中标` sheet 读取 J 列（行 2-97）
- 竞价空间：从 `01 biddingSpace_analysis/output/MMDD-竞价空间分析.xlsx` 的 `Sheet1` 读取行 3-6（直调负荷、联络线受电、风电总加、光伏总加），计算 `行3 - 行4 - 行5 - 行6`（行 7 是公式，`data_only=True` 读取返回 None，需手动计算）

**阶段 06 策略分析文档：**
- `电价分析操作手册.md` — 数据来源、数据结构、提取脚本用法、常见问题
- `策略复盘结论.md` — 策略规则汇总、竞价空间锚点、多日对比验证

**阶段 06 extract → gen 数据管线：** 5 个 `extract_*.py` / `gen_*.html.py` 配对脚本遵循统一模式：extract 从数据库查询数据写入项目根目录 `_tmp_*.json`，gen 读取 JSON 生成 ECharts HTML。修改日期范围只需编辑 extract 脚本顶部的 `START_DATE`/`END_DATE`，然后重新运行 extract + gen 即可。

**阶段 05 增量更新机制：** `process_data.py` 以上一轮 `output/` 中的文件为基础进行增量更新。带 filter 的单类型更新不会覆盖其他类型已写入的数据。首次运行需从 `assets/` 的模版开始。

**阶段 05 `compute_settlement_values()` 列映射（已修正）：** 模板公式对应的正确列号：
- `A4` = 充电日清算费用!**AC29** (col 29), `B4` = -**AB29** (col 28), `C4` = -**AD29** (col 30)
- `M4` = 放电日清算费用!**AO101** (col 41), `N4` = **Q101** (col 17)

**阶段 05 文件锁定回退：** 输出文件被 Excel 占用时自动回退到带时间戳文件名。运行前需关闭 Excel。

**阶段 05 源文件位置：** `process_data.py` 从自己的 `assets/` 目录读取源文件。运行前需将 02/03/04 的产出文件复制到 05 的 `assets/` 下。

**目标文件日期格式：** 统计表 A 列日期存储为 Excel 整数序列号（如 `46163`），`find_date_in_target()` 已同时支持 `datetime` 和序列号两种格式。

## 日结算文件命名变体

阶段 05 的源文件匹配同时接受两种文件名：
- `MMDD-日结算收益复盘.xlsx`（标准）
- `MMDD-日结算收益复盘-.xlsx`（尾部带 `-` 的变体）

## 结算单文件命名规则（阶段 04）

从下载目录拷入的结算单通常没有 `-充电`/`-放电` 后缀，按文件大小区分：
- **~11KB → `-充电`**（含「日清算数据」sheet）
- **~21KB → `-放电`**（含「日清算费用」sheet）

带 ` (1)` 编号后缀的文件同理处理，重命名时移除 ` (1)` 再加对应后缀。

## 源文件来源

用户提供的源数据文件常位于 `d:\Personal\下载\`（带编号后缀如 ` (1)`, ` (2)`），处理时直接使用绝对路径读取，无需复制到项目目录。生成结果写入对应阶段的 `output/` 目录。

## 权限配置

项目根目录 `.claude/settings.local.json` 已预配 Bash（python/git/ls）、Read/Write/Edit（项目 + d:\Personal）、Glob/Grep 权限，覆盖本项目常见操作，减少确认步骤。

## 数据流向（阶段间依赖）

- 02 的产出 → 05 的「日前」列（B-R），同时也被 04 引用
- 03 的产出 → 05 的「实时」列（S-AI），同时也被 04 引用（J4 容量分摊系数）
- 04 的产出 → 05 的「日结算」列（AJ-BA）

**数据源归属规则（不可更改）：** 统计表「润津」sheet 第一行标注了各列分组归属。取数必须严格对应：
- **日前列（B-R）** → 来自 `日前机组组合收益复盘` 文件 — `compute_summary_values()` 从 `报价及预中标` J/N 列计算
- **实时列（S-AI）** → 来自 `实时机组组合收益复盘` 文件 — `compute_summary_values()` 从 `报价及预中标` J/N 列计算
- **日结算列（AJ-BA）** → 来自 `日结算收益复盘` 文件 — `compute_settlement_values()` 从 `充电日清算费用`/`放电日清算费用` 取基础值后计算（因日结算的 `充放测算` row 4 公式引用结算单数据，而非 `报价及预中标`）

`compute_summary_values()` 和 `compute_settlement_values()` 分别对应不同的数据来源，不能混用。

**统计表写入格式规则：** 更新目标文件中任何行数据时，写入值后必须从**上一行**（已有数据）拷贝 `cell.number_format` 到新行对应列。值保留原始全精度不取整，由 Excel 格式控制显示精度。严禁写入后对值做 `round()`。

## 月度日结算收益复盘汇总 拷贝流程

**场景：** 将日结算源文件（`MMDD-日结算收益复盘.xlsx`）的「充放测算」第4行数值拷贝到目标文件（`月度日结算收益复盘汇总_2026年X月.xlsx`）对应日期行。

**关键问题：** 源文件第4行全是跨 sheet 公式，openpyxl 无公式计算引擎，`data_only=True` 直接读到的缓存值为 `None`。**必须先用 Excel COM 打开源文件让公式计算并保存**，再用 openpyxl 读取。

**步骤：** 见上方「COM 刷新」示例代码，批量刷新后 openpyxl 读取写入。

**文件位置：**
- 源文件：`output/日结算单收益测算/MMDD-日结算收益复盘.xlsx`
- 目标文件：`output/日结算单收益测算/月度日结算收益复盘汇总_2026年X月.xlsx`

**硬性约束：**
- 只写值，不修改目标文件的格式/公式/结构/列宽/合并单元格
- 源 A→目标 B, 源 B→目标 C, ..., 源 S→目标 T（目标 A 列是日期，从 B 列开始写）
- 不存在的源文件日期跳过，不报错
