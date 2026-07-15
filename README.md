# 润津储能交易策略与复盘系统

山东润津独立储能电站（德州润津储能科技有限公司）现货市场收益复盘与竞价空间分析数据管线。

## 快速开始

```bash
# 1. 配置
cp .env.example .env
# 编辑 .env 填入数据库密码

# 2. 迁移历史数据（首次）
python -m src.data.migrate --copy --run

# 3. 运行管线
python -m src.cli run 0605                    # 单日全流程
python -m src.cli run 0605-0612               # 日期范围
python -m src.cli run 0605 --stages 01,02,03  # 指定阶段
python -m src.cli run 0605 --dry-run          # 预览模式

# 4. 单日策略评估
python -m src.cli evaluate 0605

# 5. 策略回测
python -m src.cli backtest 0518-0603
```

## 项目结构

```
Storage_Strategy/
├── config/                    # 配置文件
│   ├── settings.yaml          # 主配置（DB、路径、member_id）
│   ├── parameters.yaml        # 业务参数（成本、策略阈值）
│   └── .env.example           # 密钥模板
│
├── src/                       # 共享 Python 代码
│   ├── config.py              # 配置加载器
│   ├── cli.py                 # 统一 CLI 入口
│   ├── data/                  # 数据层
│   │   ├── models.py          # 统一数据模型
│   │   ├── db.py              # 数据库连接 + 预设查询
│   │   ├── readers.py         # 统一文件读取器
│   │   ├── writers.py         # 安全 Excel 写入器
│   │   └── migrate.py         # 数据迁移工具
│   ├── business/              # 核心业务逻辑
│   │   ├── revenue.py         # 收益计算（唯一真相源）
│   │   ├── capacity.py        # 容量分摊系数(J4)
│   │   ├── bidding_space.py   # 竞价空间计算
│   │   ├── strategy.py        # 策略规则引擎
│   │   └── validation.py      # 交叉验证
│   ├── pipeline/              # 管线编排
│   │   ├── orchestrator.py    # 主编排器
│   │   ├── stages.py          # 阶段定义 + 依赖
│   │   └── state.py           # 运行状态追踪
│   ├── stages/                # 各阶段实现
│   │   ├── stage01_bidding_space.py
│   │   ├── stage02_dayahead.py
│   │   ├── stage03_realtime.py
│   │   ├── stage04_settlement.py
│   │   ├── stage05_dashboard.py
│   │   └── stage06_datamining/
│   ├── backtesting/           # 策略回测
│   │   ├── engine.py
│   │   └── metrics.py
│   └── utils/                 # 工具函数
│       ├── excel_utils.py
│       ├── date_utils.py
│       ├── numerics.py
│       └── weather.py
│
├── assets/templates/          # 集中管理的 Excel 模版
│   ├── 竞价空间分析.xlsx
│   ├── 日前机组组合收益复盘.xlsx
│   ├── 实时机组组合收益复盘.xlsx
│   ├── 日结算收益复盘.xlsx
│   └── 山东夏津储能收益统计表.xlsx
│
├── data/raw/YYYY-MM-DD/       # 按日期组织的源文件
├── output/YYYY-MM-DD/         # 按日期组织的产出
├── output/reports/            # 汇总报告和可视化
│
├── tests/                     # 单元测试
├── docs/                      # 文档
│
├── 01-06 */                   # 旧阶段目录（保留兼容）
└── CLAUDE.md                  # 项目说明（给 Claude）
```

## 6 阶段管线

| 阶段 | 说明 | 依赖 | 输入 |
|------|------|------|------|
| 01 竞价空间 | 负荷预测 → 竞价空间 | — | 负荷信息预测.xls |
| 02 日前复盘 | 日前交易结果 → 复盘 | — | 日前交易结果查询.xls |
| 03 实时复盘 | 实时交易结果 → 复盘 | — | 实时交易结果查询.xls |
| 04 日结算 | 结算单 + 实时复盘 → 日结算 | 03 | 结算单 + 实时复盘 |
| 05 统计表 | 全部复盘 → 主表 | 02,03,04 | 全部复盘文件 |
| 06 分析 | 可视化 + 电价对比 | 01,02,03 | 复盘产出 |

**并行执行：** 01、02、03 可同时运行，无需互相等待。

## 收益计算

所有收益计算通过 `src/business/revenue.py` 的 `compute_revenue()` 函数统一执行，替代了原来分散在 Excel 公式中的逻辑。已通过 0607 日结算数据与旧管线输出逐项验证（偏差 < 0.01）。

## 策略规则

3 条件同时满足才触发交易信号：

1. 竞价空间 2h 峰谷差 >= 23,000 MW
2. 谷值时段在 08:45-14:00（中午谷值型）
3. 日前电价价差 >= 200 元/MWh

策略参数可在 `config/parameters.yaml` 中调整。

## 技术栈

- Python 3.14
- pandas + openpyxl + pymysql + PyYAML
- 包管理: `nv`
- 数据库: MySQL (天机 tianrun_new, 阿里云 RDS)

## 旧阶段目录

`01-06` 开头的旧阶段目录保留用于向后兼容。新代码统一使用 `src/stages/` 下的模块。旧脚本可继续独立运行，但建议逐步迁移到统一 CLI。