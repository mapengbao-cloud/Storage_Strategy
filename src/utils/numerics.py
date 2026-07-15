"""Numeric utilities — safe type conversion, rounding rules, precision.

Conventions:
- All data written to Excel must be int or float (never string)
- 综合效率 (efficiency) columns: full precision, no rounding
- All other monetary values: round to 2 decimal places
- None/empty/non-numeric → 0 or raise depending on context
"""

import numbers

# Target columns that use '0.00%' format (综合效率 = efficiency ratio)
PCT_COLUMNS = {17, 34, 52}  # Q, AH, AZ in the statistics table


def safe_float(value, default: float = 0.0) -> float:
    """Convert a value to float, returning default on failure.

    Args:
        value: Any value (string, int, float, None).
        default: Value to return if conversion fails.

    Returns:
        Float value or default.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        if isinstance(value, bool):
            return default
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("="):
            return default
        try:
            return float(s)
        except (ValueError, TypeError):
            return default
    return default


def safe_int(value, default: int = 0) -> int:
    """Convert a value to int, returning default on failure."""
    v = safe_float(value, None)
    if v is None:
        return default
    return int(v)


def is_numeric(value) -> bool:
    """Check if a value can be converted to a number."""
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return not isinstance(value, bool)
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("="):
            return False
        try:
            float(s)
            return True
        except (ValueError, TypeError):
            return False
    return False


def round_value(value, target_col: int | None = None) -> float:
    """Round a numeric value according to business rules.

    - 综合效率 columns (PCT_COLUMNS): full precision (no rounding)
    - All other float columns: round to 2 decimal places

    Args:
        value: Numeric value to round.
        target_col: Optional target column index (1-based) to check for PCT_COLUMNS.

    Returns:
        Rounded float value.
    """
    if not isinstance(value, (int, float)):
        return value
    if isinstance(value, bool):
        return float(value)
    if target_col is not None and target_col in PCT_COLUMNS:
        return float(value)  # preserve full precision
    return round(float(value), 2)


def to_float_int(value) -> int | float | None:
    """Convert a string to float/int optimally.

    If the value is a whole number and doesn't have a decimal point
    in the original string, return int. Otherwise return float.

    Args:
        value: String value to convert.

    Returns:
        int or float, or None if conversion fails.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    s = str(value).strip()
    try:
        v = float(s)
        if v == int(v) and "." not in s and "e" not in s.lower():
            return int(v)
        return v
    except (ValueError, TypeError):
        return None


def ensure_numeric(value) -> int | float:
    """Convert to numeric, raising on failure. Use when non-numeric is an error.

    Args:
        value: Any value.

    Returns:
        int or float.

    Raises:
        ValueError: If value cannot be converted.
    """
    if value is None:
        raise ValueError("Cannot convert None to numeric")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("="):
            raise ValueError(f"Formula cell: {s}")
        try:
            return float(s)
        except (ValueError, TypeError):
            raise ValueError(f"Cannot convert '{value}' to numeric")
    raise ValueError(f"Cannot convert {type(value).__name__} '{value}' to numeric")