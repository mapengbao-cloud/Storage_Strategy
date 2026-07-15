"""Pipeline stage definitions — dependencies, inputs, outputs.

Each stage declares:
- name: Unique identifier
- requires: List of stage names that must complete first
- description: Human-readable description
- input_patterns: Source file glob patterns needed
- output_patterns: Output file patterns produced

The dependency graph is:
    01 ─────────────┐
    02 ─────────────┤
    03 ──────┐      │
             ├─ 04 ─┤
             │      │
             └──────┼─ 05 ── 06
"""

from dataclasses import dataclass, field
from enum import Enum


class StageStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Stage:
    name: str
    description: str
    requires: list[str] = field(default_factory=list)
    input_patterns: list[str] = field(default_factory=list)
    output_patterns: list[str] = field(default_factory=list)

    @property
    def is_parallelizable(self) -> bool:
        """True if this stage has no dependencies and can run in parallel."""
        return len(self.requires) == 0


# All pipeline stages in dependency order
ALL_STAGES: dict[str, Stage] = {
    "01_bidding_space": Stage(
        name="01_bidding_space",
        description="竞价空间分析 — 负荷预测/实际数据 → 竞价空间计算",
        requires=[],
        input_patterns=["*负荷信息预测*", "*电网运行实际信息*"],
        output_patterns=["*-竞价空间分析(预测).xlsx", "*-竞价空间分析(实际).xlsx"],
    ),
    "02_dayahead": Stage(
        name="02_dayahead",
        description="日前机组组合收益复盘 — 日前交易结果 → 复盘文件",
        requires=[],
        input_patterns=["*日前交易结果查询*"],
        output_patterns=["*-日前机组组合收益复盘.xlsx"],
    ),
    "03_realtime": Stage(
        name="03_realtime",
        description="实时机组组合收益复盘 — 实时交易结果 → 复盘文件",
        requires=[],
        input_patterns=["*实时交易结果查询*"],
        output_patterns=["*-实时机组组合收益复盘.xlsx"],
    ),
    "04_settlement": Stage(
        name="04_settlement",
        description="日结算收益复盘 — 汇总结算单 + 实时复盘参数",
        requires=["03_realtime"],
        input_patterns=["*结算单-充电*", "*结算单-放电*"],
        output_patterns=["*-日结算收益复盘.xlsx"],
    ),
    "05_dashboard": Stage(
        name="05_dashboard",
        description="收益统计表更新 — 汇总全部复盘结果到主表",
        requires=["02_dayahead", "03_realtime", "04_settlement"],
        input_patterns=["*-日前机组组合收益复盘.xlsx",
                        "*-实时机组组合收益复盘.xlsx",
                        "*-日结算收益复盘.xlsx"],
        output_patterns=["山东夏津储能收益统计表.xlsx"],
    ),
    "06_analysis": Stage(
        name="06_analysis",
        description="数据分析与可视化 — 电价对比、策略评估、图表生成",
        requires=["01_bidding_space", "02_dayahead", "03_realtime"],
        input_patterns=[],
        output_patterns=["电价对比_*.html", "竞价空间_电价_天气综合分析_*.html"],
    ),
}


def get_run_order(stages: list[str] | None = None) -> list[str]:
    """Get stages in dependency-respecting execution order.

    Stages with no dependencies come first (can run in parallel).
    Stages that depend on earlier stages come later.

    Args:
        stages: Specific stage names to run, or None for all.

    Returns:
        Ordered list of stage names.
    """
    if stages is None:
        stages = list(ALL_STAGES.keys())

    # Topological sort
    resolved = []
    seen = set()

    def resolve(name: str):
        if name in seen:
            return
        if name not in ALL_STAGES:
            raise ValueError(f"Unknown stage: {name}")
        for dep in ALL_STAGES[name].requires:
            if dep in stages or stages is None:
                resolve(dep)
        if name in stages:
            seen.add(name)
            resolved.append(name)

    for s in stages:
        resolve(s)

    return resolved


def get_parallel_groups(stages: list[str] | None = None) -> list[list[str]]:
    """Group stages into parallel-executable batches.

    Batch 0: stages with no deps (01, 02, 03) — can run simultaneously
    Batch 1: stages that depend on batch 0 only (04, 06)
    Batch 2: stages that depend on batch 1 (05)

    Returns:
        List of lists, each inner list is a batch of parallel-runnable stages.
    """
    if stages is None:
        stages = list(ALL_STAGES.keys())

    run_order = get_run_order(stages)
    groups = []
    remaining = set(run_order)

    while remaining:
        batch = []
        for name in list(remaining):
            deps = ALL_STAGES[name].requires
            if all(d not in remaining for d in deps):
                batch.append(name)
        if not batch:
            raise ValueError(f"Circular dependency detected: {remaining}")
        for b in batch:
            remaining.remove(b)
        groups.append(batch)

    return groups