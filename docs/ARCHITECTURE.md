# 架构文档

## 设计原则

1. **数据与逻辑分离** — 文件 I/O 只在 `src/data/` 和 `src/stages/` 中发生，业务逻辑层 (`src/business/`) 是纯函数
2. **单一真相源** — 收益计算 `compute_revenue()` 是所有阶段的唯一入口
3. **配置驱动** — 所有可变参数集中在 `config/`，代码中不硬编码
4. **管线独立** — 每个阶段可独立运行，也可通过编排器串行/并行
5. **Excel 兼容** — 安全写入（跳过 MergedCell + 公式），新旧管线输出一致

## 数据流

```
[交易中心 Excel/PDF] ─→ data/raw/YYYY-MM-DD/ ─→ readers.py ─→ models.py
[天机 MySQL DB]      ─→ db.py ────────────────→ models.py
[Open-Meteo API]     ─→ weather.py ───────────→ models.py
                                                      │
                                                      ▼
                                              business/*.py (纯函数计算)
                                                      │
                                                      ▼
                                              stages/*.py (I/O + 编排)
                                                      │
                                                      ▼
                                              output/YYYY-MM-DD/ + reports/
```

## 模块职责

### 配置层 (`config/`)
- `settings.yaml` — 静态配置（DB 连接、路径、member_id、月份列映射）
- `parameters.yaml` — 可调参数（成本、策略阈值、精度）
- `.env` — 密钥（不入库）

### 数据层 (`src/data/`)
- `models.py` — 10 个 dataclass，定义所有核心数据结构
- `db.py` — 数据库连接池 + 8 个预设查询函数
- `readers.py` — 6 个文件读取器，统一转换为模型
- `writers.py` — 安全 Excel 写入器，保护模版公式/合并单元格
- `migrate.py` — 历史数据迁移工具

### 业务层 (`src/business/`)
- `revenue.py` — `compute_revenue()` 单一入口，17 个收益值计算
- `capacity.py` — `compute_J_val()` 容量分摊系数加权平均
- `bidding_space.py` — 竞价空间 = 直调 - 联络线 - 风电 - 光伏 - 核电 - 自备
- `strategy.py` — 3 条件策略评估 + 竞价空间形态分类
- `validation.py` — Excel 交叉验证 + Golden File 生成

### 管线层 (`src/pipeline/`)
- `stages.py` — 6 阶段定义 + 拓扑排序 + 并行分组
- `state.py` — JSON 持久化状态追踪
- `orchestrator.py` — 主编排器，支持断点续跑

### 阶段实现 (`src/stages/`)
- `stage01_bidding_space.py` — 竞价空间分析
- `stage02_dayahead.py` — 日前机组组合收益复盘（含共享 `_generate_trading_review()`）
- `stage03_realtime.py` — 实时机组组合收益复盘（复用 Stage 02 核心函数）
- `stage04_settlement.py` — 日结算收益复盘
- `stage05_dashboard.py` — 收益统计表更新

### 回测 (`src/backtesting/`)
- `engine.py` — 按日期遍历历史数据，评估策略信号
- `metrics.py` — 胜率、平均收益、VaR 95%、Sharpe ratio

### 工具 (`src/utils/`)
- `excel_utils.py` — MergedCell 检测、安全写入、公式写入
- `date_utils.py` — MMDD/ISO/Excel 序列号转换
- `numerics.py` — 安全数值转换、精度规则
- `weather.py` — Open-Meteo API 客户端

## 依赖关系

```
config.py ──→ 所有模块
models.py ──→ business/*, readers.py, writers.py, stages/*
utils/* ────→ data/*, business/*, stages/*
business/* ─→ stages/*, backtesting/*
pipeline/* ─→ stages/*
```

## 格式转换注意事项

交易中心的 Excel 格式经常变化，页面也经常升级。不同时间的数据格式可能不同。`readers.py` 和 `writers.py` 是适配层，格式变化时只需修改这两个文件，业务逻辑层不受影响。