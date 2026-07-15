"""Cross-validation: compare Python-computed values with Excel formula results.

CRITICAL: This is the safety net ensuring formula extraction is correct.
After extracting Excel formulas to Python in revenue.py, this module
verifies the results match within acceptable tolerance.

Usage:
    from src.business.validation import validate_revenue_vs_excel
    result = validate_revenue_vs_excel(computed_revenue, excel_path)
    if result.all_match:
        print("All 17 values match!")
    else:
        for field, (computed, excel, match) in result.mismatches():
            print(f"{field}: computed={computed}, excel={excel}")
"""

import openpyxl
from pathlib import Path
from dataclasses import dataclass, field

from src.data.models import DailyRevenue
from src.utils.numerics import safe_float


@dataclass
class ValidationResult:
    """Result of comparing computed revenue with Excel values.

    Attributes:
        date_str: Date being validated.
        excel_path: Path to the Excel file used as reference.
        comparisons: Dict mapping field_name -> (computed, excel, is_match).
        tolerance: Maximum allowed absolute difference.
    """
    date_str: str = ""
    excel_path: str = ""
    comparisons: dict[str, tuple[float, float, bool]] = field(default_factory=dict)
    tolerance: float = 0.01

    @property
    def all_match(self) -> bool:
        """True if all 17 values match within tolerance."""
        return all(is_match for _, _, is_match in self.comparisons.values())

    @property
    def match_count(self) -> int:
        return sum(1 for _, _, m in self.comparisons.values() if m)

    @property
    def total_count(self) -> int:
        return len(self.comparisons)

    def mismatches(self) -> list[tuple[str, float, float]]:
        """Return [(field_name, computed, excel)] for non-matching fields."""
        return [
            (k, c, e)
            for k, (c, e, m) in self.comparisons.items()
            if not m
        ]

    def report(self) -> str:
        """Generate a human-readable comparison report."""
        lines = [
            f"Validation: {self.date_str} vs {self.excel_path}",
            f"Tolerance: ±{self.tolerance}",
            f"Result: {self.match_count}/{self.total_count} fields match",
            f"{'ALL MATCH ✓' if self.all_match else 'MISMATCHES FOUND ✗'}",
            "",
        ]
        if not self.all_match:
            lines.append("Mismatches:")
            lines.append(f"{'Field':<6} {'Computed':>14} {'Excel':>14} {'Diff':>10}")
            lines.append("-" * 48)
            for field, computed, excel in self.mismatches():
                diff = abs(computed - excel)
                lines.append(
                    f"{field:<6} {computed:>14.4f} {excel:>14.4f} {diff:>10.4f}"
                )
        return "\n".join(lines)


def validate_revenue_vs_excel(
    computed: DailyRevenue,
    excel_path: str | Path,
    tolerance: float = 0.01,
) -> ValidationResult:
    """Compare computed DailyRevenue against Excel 充放测算 row 4.

    Opens the Excel file with data_only=True to read cached formula
    results from 充放测算 row 4, columns A-Q (cols 1-17).

    Args:
        computed: DailyRevenue from compute_revenue().
        excel_path: Path to the Excel file (日结算 or 机组组合收益复盘).
        tolerance: Maximum allowed absolute difference (default 0.01).

    Returns:
        ValidationResult with per-field comparisons.
    """
    excel_path = Path(excel_path)
    result = ValidationResult(
        date_str=computed.date_str,
        excel_path=str(excel_path),
        tolerance=tolerance,
    )

    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb["充放测算"]

    # Read row 4, columns A-Q (1-17)
    excel_values = []
    for col in range(1, 18):
        val = safe_float(ws.cell(row=4, column=col).value)
        excel_values.append(val)

    wb.close()

    computed_list = computed.to_list()
    field_names = computed.field_names()

    for i, (field, c_val, e_val) in enumerate(
        zip(field_names, computed_list, excel_values)
    ):
        diff = abs(c_val - e_val)
        is_match = diff <= tolerance
        result.comparisons[field] = (c_val, e_val, is_match)

    return result


def read_excel_row4_values(excel_path: str | Path) -> dict[str, float]:
    """Read the 17 values from 充放测算 row 4, columns A-Q.

    Useful as a reference for Golden File tests.

    Args:
        excel_path: Path to a 日结算/机组组合收益复盘 Excel file.

    Returns:
        Dict mapping field letter (A, B, ..., Q) to float value.
    """
    excel_path = Path(excel_path)
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb["充放测算"]

    field_names = list("ABCDEFGHIJKLMNOPQ")
    values = {}
    for col, field in enumerate(field_names, start=1):
        values[field] = safe_float(ws.cell(row=4, column=col).value)

    wb.close()
    return values


def generate_golden_file(
    date_str: str,
    computed: DailyRevenue,
    excel_path: str | Path,
    output_path: str | Path,
):
    """Generate a Golden File JSON for a given date.

    Saves both the computed values and Excel reference values
    for future regression testing.

    Args:
        date_str: Date identifier.
        computed: Python-computed DailyRevenue.
        excel_path: Path to reference Excel file.
        output_path: Where to save the golden JSON.
    """
    import json

    excel_values = read_excel_row4_values(excel_path)

    golden = {
        "date": date_str,
        "excel_path": str(excel_path),
        "computed": {
            field: getattr(computed, field)
            for field in computed.field_names()
        },
        "excel": excel_values,
        "diffs": {
            field: abs(getattr(computed, field) - excel_values.get(field, 0))
            for field in computed.field_names()
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(golden, f, indent=2, ensure_ascii=False)

    max_diff = max(golden["diffs"].values())
    print(
        f"Golden file saved: {output_path} "
        f"(max diff: {max_diff:.6f})"
    )