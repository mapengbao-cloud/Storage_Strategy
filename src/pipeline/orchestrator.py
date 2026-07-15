"""Pipeline orchestrator — runs stages in dependency order for given dates.

Core flow:
    1. Parse date range → list of dates
    2. For each date, run stages in dependency order:
       - Batch 0 (parallel): 01, 02, 03
       - Batch 1: 04 (needs 03), 06 (needs 01+02+03)
       - Batch 2: 05 (needs 02+03+04)
    3. Track state, resume from failures

Usage:
    from src.pipeline.orchestrator import Pipeline
    pipe = Pipeline('0522-0531')
    pipe.run()
"""

import logging
from pathlib import Path
from datetime import date
from typing import Optional

from src.pipeline.stages import ALL_STAGES, StageStatus, get_parallel_groups
from src.pipeline.state import PipelineState
from src.utils.date_utils import expand_mmdd_range, date_to_mmdd

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the full 6-stage pipeline for one or more dates."""

    def __init__(
        self,
        date_range: str | None = None,
        stages: list[str] | None = None,
        data_root: str = "data",
        output_root: str = "output",
        template_root: str = "assets/templates",
        state_file: str | None = None,
    ):
        """
        Args:
            date_range: 'MMDD-MMDD' or 'MMDD' or None (auto-detect).
            stages: List of stage names to run, or None for all.
            data_root: Root directory for source data.
            output_root: Root directory for output files.
            template_root: Root directory for templates.
            state_file: Path to pipeline state JSON file.
        """
        self.dates: list[date] = self._resolve_dates(date_range)
        self.stages_to_run: list[str] = stages or list(ALL_STAGES.keys())
        self.data_root = data_root
        self.output_root = output_root
        self.template_root = template_root
        self.state = PipelineState(
            state_file or f"{output_root}/pipeline_state.json"
        )

    def _resolve_dates(self, date_range: str | None) -> list[date]:
        """Parse date range or auto-detect from data/raw/."""
        if date_range:
            return expand_mmdd_range(date_range)

        # Auto-detect: scan data/raw/ for date directories
        raw_dir = Path(self.data_root) / "raw"
        if raw_dir.exists():
            detected = []
            for d in sorted(raw_dir.iterdir()):
                if d.is_dir():
                    try:
                        detected.append(date.fromisoformat(d.name))
                    except ValueError:
                        pass
            if detected:
                logger.info(f"Auto-detected {len(detected)} dates from {raw_dir}")
                return detected

        raise ValueError(
            "No date_range specified and no data/raw/ directories found. "
            "Specify dates like '0522-0531'."
        )

    @property
    def date_strs(self) -> list[str]:
        return [date_to_mmdd(d) for d in self.dates]

    def run(self, dry_run: bool = False, force: bool = False) -> PipelineState:
        """Execute the pipeline.

        Args:
            dry_run: If True, preview what would run without executing.
            force: If True, re-run stages even if already marked SUCCESS.

        Returns:
            PipelineState with final status for all dates/stages.
        """
        self.state.start_run(self.date_strs)

        parallel_groups = get_parallel_groups(self.stages_to_run)

        for date_obj in self.dates:
            date_str = date_to_mmdd(date_obj)
            date_iso = date_obj.isoformat()
            logger.info(f"\n{'='*50}")
            logger.info(f"Processing: {date_iso} ({date_str})")
            logger.info(f"{'='*50}")

            for batch_idx, batch in enumerate(parallel_groups):
                logger.info(f"  Batch {batch_idx}: {', '.join(batch)}")

                for stage_name in batch:
                    stage = ALL_STAGES[stage_name]

                    # Skip if already done (unless forced)
                    if not force and self.state.is_done(stage_name, date_str):
                        logger.info(f"    {stage_name}: already done, skipping")
                        continue

                    # Check dependencies
                    deps_ok = True
                    for dep in stage.requires:
                        if dep in self.stages_to_run and not self.state.is_done(dep, date_str):
                            logger.warning(
                                f"    {stage_name}: dependency '{dep}' not met, skipping"
                            )
                            deps_ok = False
                            break

                    if not deps_ok:
                        self.state.set_status(
                            stage_name, date_str, StageStatus.SKIPPED,
                            "Dependency not met"
                        )
                        continue

                    if dry_run:
                        logger.info(f"    [DRY RUN] {stage_name}: {stage.description}")
                        continue

                    # Execute
                    try:
                        self.state.set_status(
                            stage_name, date_str, StageStatus.RUNNING
                        )
                        logger.info(f"    {stage_name}: running...")
                        self._run_stage(stage_name, date_str)
                        self.state.set_status(
                            stage_name, date_str, StageStatus.SUCCESS
                        )
                        logger.info(f"    {stage_name}: SUCCESS")
                    except Exception as e:
                        logger.error(f"    {stage_name}: FAILED — {e}")
                        self.state.set_status(
                            stage_name, date_str, StageStatus.FAILED,
                            str(e)
                        )

            self.state.save()

        return self.state

    def _run_stage(self, stage_name: str, date_str: str):
        """Dispatch to the appropriate stage implementation."""
        kwargs = {
            "date_mmdd": date_str,
            "data_root": self.data_root,
            "output_root": self.output_root,
            "template_root": self.template_root,
        }

        if stage_name == "01_bidding_space":
            from src.stages.stage01_bidding_space import run
            # Try prediction, then actual
            try:
                run(**kwargs, is_actual=False)
            except FileNotFoundError:
                pass
            try:
                run(**kwargs, is_actual=True)
            except FileNotFoundError:
                pass

        elif stage_name == "02_dayahead":
            from src.stages.stage02_dayahead import run
            run(**kwargs)

        elif stage_name == "03_realtime":
            from src.stages.stage03_realtime import run
            run(**kwargs)

        elif stage_name == "04_settlement":
            from src.stages.stage04_settlement import run
            run(**kwargs)

        elif stage_name == "05_dashboard":
            from src.stages.stage05_dashboard import run
            run(
                date_list=[date_str],
                source_dir=self.output_root,
                output_dir=f"{self.output_root}/reports",
            )

        elif stage_name == "06_analysis":
            # Stage 06 is mostly visualization — defer to extract_prices.py
            # or generate_analysis_html.py for now
            logger.info(f"    {stage_name}: visualization — use existing scripts for now")

        else:
            raise ValueError(f"Unknown stage: {stage_name}")

    def status(self) -> str:
        """Return a human-readable summary of pipeline state."""
        return self.state.summary()

    def validate(self) -> dict[str, list[str]]:
        """Check for missing source files for all dates/stages.

        Returns:
            {date_str: [list of missing patterns]}
        """
        missing = {}
        for date_obj in self.dates:
            date_iso = date_obj.isoformat()
            date_str = date_to_mmdd(date_obj)
            data_dir = Path(self.data_root) / "raw" / date_iso
            date_missing = []

            for stage_name in self.stages_to_run:
                stage = ALL_STAGES[stage_name]
                for pattern in stage.input_patterns:
                    if not list(data_dir.glob(pattern)):
                        date_missing.append(f"{stage_name}: {pattern}")

            if date_missing:
                missing[date_str] = date_missing

        return missing