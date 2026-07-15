"""Configuration loader. Reads YAML files with ${ENV_VAR} substitution.

Usage:
    from src.config import get_settings, get_parameters
    db_host = get_settings()["database"]["tianrun"]["host"]
    cap_cost = get_parameters()["cost"]["capacity_cost_yuan_per_kw_month"]
"""

import os
import yaml
from pathlib import Path
from functools import lru_cache

CONFIG_ROOT = Path(__file__).parent.parent / "config"


def _load_yaml(name: str) -> dict:
    """Load a YAML file, substituting ${ENV_VAR} patterns in string values."""
    path = CONFIG_ROOT / name
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    raw = os.path.expandvars(raw)
    return yaml.safe_load(raw)


@lru_cache(maxsize=1)
def get_settings() -> dict:
    """Load and cache settings.yaml. Call repeatedly without re-reading."""
    return _load_yaml("settings.yaml")


@lru_cache(maxsize=1)
def get_parameters() -> dict:
    """Load and cache parameters.yaml. Call repeatedly without re-reading."""
    return _load_yaml("parameters.yaml")


def get_month_column(month: int) -> int:
    """Get the Excel column index for a given month (1-12)
    from the 容量分摊系数 sheet."""
    settings = get_settings()
    return settings["monthly_columns"].get(month, 10)


def get_settlement_cell(side: str, field: str) -> tuple:
    """Get (row, col) for a settlement reference cell.

    Args:
        side: 'charge' or 'discharge'
        field: 'price', 'volume', or 'revenue'

    Returns:
        (row, column) tuple for the Excel cell reference.
    """
    settings = get_settings()
    cells = settings["settlement_cells"][side]
    return cells[f"{field}_row"], cells[f"{field}_col"]