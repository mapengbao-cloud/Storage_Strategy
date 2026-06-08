# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 关键行为规则（最高优先级）

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

每个阶段是独立子目录，有自己的 `CLAUDE.md`（含该阶段的详细 sheet mapping 和处理逻辑）、`assets/`（源数据 + 输出模版）、`output/`（生成文件）。

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

### 依赖

所有脚本仅依赖 Python 标准库 + `pandas` + `openpyxl` + `pymysql`（均已预装，Python 3.14）。Python 包管理统一用 `nv` 命令（`nv list`、`nv install`、`nv uninstall`），不用 `pip`。

## 各阶段脚本

| 阶段 | 脚本 | 用法 |
|------|------|------|
| 01 | `01 biddingSpace_analysis/generate.py` | `python generate.py MMDD [actual] [src_path]` |
| 02 | `02 Dayahead_Trading_Review/generate.py` | `python generate.py MMDD [src_path]`（用日期特定模版） |
| 02 | `02 Dayahead_Trading_Review/batch_generate.py` | `python batch_generate.py`（批量处理，用固定模版 `输出模版-0505-日前机组组合收益复盘.xlsx`） |
| 03 | 无（Claude 直接操作 openpyxl） | 读取实时交易 `.xls` → 写入实时复盘模版 |
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

阶段 03 无独立脚本，由 Claude 按对应 `CLAUDE.md` 中的 sheet mapping 直接操作 `openpyxl` 完成。

**阶段 01 竞价空间分析文件命名规则（重要）：**

| 数据源 | 输出文件名格式 | 说明 |
|--------|---------------|------|
| 负荷预测信息（`负荷信息预测.xls`） | `MMDD-竞价空间分析(预测).xlsx` | 基于日前预测数据 |
| 电网运行实际信息（`电网运行实际信息.xlsx`） | `MMDD-竞价空间分析(实际).xlsx` | 基于事后真实运行数据 |

> 预测和实际文件必须严格区分命名，不可混淆。实际数据用于事后验证预测准确性和策略复盘。

**阶段 02 `generate.py` vs `batch_generate.py`：** 前者用日期特定模版（`assets/MMDD-日前机组组合收益复盘.xlsx`），后者用固定模版 `输出模版-0505-日前机组组合收益复盘.xlsx` 且自动处理带编号后缀的源文件（如 `0509-发电侧日前交易结果查询 (1).xls`）。

**阶段 04 模版（3 sheet）：** 模版为 `assets/输出模版-0525-日结算收益复盘.xlsx`，仅含 3 个 sheet：`充放测算`、`充电日清算费用`、`放电日清算费用`。生成需要三个数据源：充电结算单 `.xlsx`（→ `充电日清算费用`）、放电结算单 `.xlsx`（→ `放电日清算费用`）、实时复盘 `.xlsx`（→ J4 容量分摊系数 + I8-I14 参数）。J4 通过 `compute_J4()` 从实时复盘文件的 `容量分摊系数` 和 `报价及预中标` 加权计算得到。

**阶段 06 `db_viewer.py`：** 通过 pymysql 连接天机数据库（`tianrun_new`），支持预设查询（`clearing_price` / `supply_demand` / `boundary`）和自定义 SQL，生成 ECharts 交互式折线图 HTML。`Peak-valley price difference analysis/` 下有峰谷价差分析 HTML。天机临时查询脚本用完需清理（如 `_tmp_query.py`）。

**阶段 06 天机数据库结构：** 参考 `天机数据库_山东相关表分类.txt`（120+ 张山东相关表的分类索引）。关键表：
- `shandong_px_spot_dayahead_clearing_price` — **日前出清价格**（统一结算价），按 `member_id` 区分电站，96 时段。无储能电站字段；润津 member_id = `b9e64e64a713458eba94c9af05c0a757`
- `shandong_px_spot_dayahead_clearing_quantity` — 日前出清电量，同上结构
- `shandong_px_spot_realtime_clearing_price` / `_quantity` — 实时出清（同上）
- `shandong_px_intraday_clearing_plan_result` — 储能充放电计划
- `shandong_px_statement_spot_daily_v2` — 每日结算单放电部分（充电部分暂未录入）
- `shandong_px_spot_surveillance_dayahead_generation_price_v2` — 全省经济性出清电价
- `shandong_pmos_spot_dayahead_supply_demand` / `shandong_pmos_spot_actual_supply_demand` — 供需（预测/实际）
- `shandong_px_spot_dayahead_load_info` / `shandong_px_spot_actual_load_info` — 负荷（日前/实际）
- `shandong_px_tuning_market_dayahead_clearing_price` — 调频市场日前出清价格

**阶段 06 `generate_analysis_html.py`：** 生成竞价空间+电价+天气综合分析 HTML。依赖外部数据提取流程生成的 `_tmp_html_data.json`（放在项目根目录），含 3 个字段：`data`（96 点曲线数组）、`weather`（Open-Meteo 天气日数据）、`timeLabels`（96 个时间标签）。搜索 `# DATE_RANGE:` 可找到需要修改日期范围的 2 处（标题 + 输出文件名）。

**阶段 06 `extract_prices.py`：** 提取日前/实时电价 + 竞价空间 96 点数据，生成 `电价对比_MMDD-MMDD.html`（ECharts 交互图表，支持日期切换、四条曲线独立开关、统计栏）。修改脚本顶部的 `DATES` 列表和 `DATE_LABELS` 字典指定日期范围。数据源：
- 日前/实时电价：从 `02/03 Dayahead/Real-time_Trading_Review/output/MMDD-*-复盘.xlsx` 的 `报价及预中标` sheet 读取 J 列（行 2-97）
- 竞价空间：从 `01 biddingSpace_analysis/output/MMDD-竞价空间分析.xlsx` 的 `Sheet1` 读取行 3-6（直调负荷、联络线受电、风电总加、光伏总加），计算 `行3 - 行4 - 行5 - 行6`（行 7 是公式，`data_only=True` 读取返回 None，需手动计算）

**阶段 06 策略分析文档：**
- `电价分析操作手册.md` — 数据来源、数据结构、提取脚本用法、常见问题
- `策略复盘结论.md` — 策略规则汇总、竞价空间锚点、多日对比验证

**阶段 06 extract → gen 数据管线：** 5 个 `extract_*.py` / `gen_*.html.py` 配对脚本遵循统一模式：extract 从数据库查询数据写入项目根目录 `_tmp_*.json`，gen 读取 JSON 生成 ECharts HTML。修改日期范围只需编辑 extract 脚本顶部的 `START_DATE`/`END_DATE`，然后重新运行 extract + gen 即可。

**阶段 05 增量更新机制：** `process_data.py` 以上一轮 `output/` 中的文件为基础进行增量更新。带 filter 的单类型更新不会覆盖其他类型已写入的数据。首次运行需从 `assets/` 的模版开始。

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
