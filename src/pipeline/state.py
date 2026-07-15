"""Pipeline run state tracking — per-date, per-stage status.

Persists to JSON for resumability across sessions.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from src.pipeline.stages import StageStatus, ALL_STAGES


class PipelineState:
    """Tracks which stages have completed for each date.

    Persists to a JSON file in the output directory for resumability.
    """

    def __init__(self, state_file: str | None = None):
        self.state_file = state_file or "output/pipeline_state.json"
        self._data: dict[str, dict[str, str]] = defaultdict(dict)
        self._started_at: str = ""
        self._load()

    def _load(self):
        """Load state from persisted JSON file."""
        path = Path(self.state_file)
        if path.exists():
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
            self._data = defaultdict(dict, saved.get("stages", {}))
            self._started_at = saved.get("started_at", "")

    def save(self):
        """Persist current state to JSON file."""
        path = Path(self.state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "started_at": self._started_at,
                    "updated_at": datetime.now().isoformat(),
                    "stages": {k: dict(v) for k, v in self._data.items()},
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

    def start_run(self, dates: list[str]):
        """Initialize state for a new pipeline run."""
        self._started_at = datetime.now().isoformat()
        for date_str in dates:
            for stage_name in ALL_STAGES:
                self._data[f"{date_str}:{stage_name}"] = {"status": StageStatus.PENDING.value}

    def set_status(self, stage_name: str, date_str: str, status: StageStatus,
                   message: str = ""):
        """Record completion/failure of a stage for a date."""
        key = f"{date_str}:{stage_name}"
        self._data[key] = {
            "status": status.value,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }

    def get_status(self, stage_name: str, date_str: str) -> StageStatus:
        """Get the current status of a stage for a date."""
        key = f"{date_str}:{stage_name}"
        entry = self._data.get(key, {})
        raw = entry.get("status", "pending")
        try:
            return StageStatus(raw)
        except ValueError:
            return StageStatus.PENDING

    def is_done(self, stage_name: str, date_str: str) -> bool:
        """Check if a stage has completed successfully for a date."""
        return self.get_status(stage_name, date_str) == StageStatus.SUCCESS

    def is_failed(self, stage_name: str, date_str: str) -> bool:
        return self.get_status(stage_name, date_str) == StageStatus.FAILED

    def summary(self) -> str:
        """Generate a human-readable summary of pipeline state."""
        if not self._data:
            return "No pipeline state recorded."

        dates = set()
        stages = set()
        for key in self._data:
            date_str, stage_name = key.split(":", 1)
            dates.add(date_str)
            stages.add(stage_name)

        lines = [f"Pipeline: {len(dates)} dates, {len(stages)} stages"]
        for d in sorted(dates):
            statuses = []
            for s in sorted(stages):
                st = self.get_status(s, d)
                if st == StageStatus.SUCCESS:
                    statuses.append("✓")
                elif st == StageStatus.FAILED:
                    statuses.append("✗")
                elif st == StageStatus.RUNNING:
                    statuses.append("…")
                else:
                    statuses.append("·")
            lines.append(f"  {d}: {' '.join(statuses)}  [{', '.join(sorted(stages))}]")
        return "\n".join(lines)

    def reset_date(self, date_str: str):
        """Reset all stages for a specific date to PENDING."""
        for stage_name in ALL_STAGES:
            key = f"{date_str}:{stage_name}"
            if key in self._data:
                del self._data[key]