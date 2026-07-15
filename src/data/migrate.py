"""Data migration script — organize old scattered files into data/raw/YYYY-MM-DD/.

Scans the old stage directories for source files and organizes them by date:
- 01 biddingSpace_analysis/assets/ → data/raw/YYYY-MM-DD/
- 02 Dayahead_Trading_Review/assets/ → data/raw/YYYY-MM-DD/
- 03 Real-time_Trading_Review/assets/ → data/raw/YYYY-MM-DD/
- 04 Daily_Settlement_Review/assets/ → data/raw/YYYY-MM-DD/

Steps:
1. Scan all old asset directories for source files
2. Extract date from each filename
3. Create symlinks (or copies) in data/raw/YYYY-MM-DD/
4. Report what was migrated

Usage:
    python -m src.data.migrate          # dry-run (preview)
    python -m src.data.migrate --run    # actually migrate
    python -m src.data.migrate --copy   # copy instead of symlink
"""

import os
import re
import shutil
import argparse
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent.parent

# Which old directories to scan for source files
SCAN_DIRS = [
    "01 biddingSpace_analysis/assets",
    "02 Dayahead_Trading_Review/assets",
    "03 Real-time_Trading_Review/assets",
    "04 Daily_Settlement_Review/assets",
    "05 Review_Dashboard_and _weeklyreport/assets",
]

# Output templates are NOT source files — skip them
SKIP_PATTERNS = [
    "输出模版",
    "模板",
    "山东夏津储能收益统计表",
    "~$",  # Excel temp files
]

# Files that are output files from other stages (not source data)
SKIP_OUTPUT_PATTERNS = [
    "-竞价空间分析",
    "-日前机组组合收益复盘",
    "-实时机组组合收益复盘",
    "-日结算收益复盘",
]


def extract_date(filename: str) -> str | None:
    """Extract ISO date from filename patterns.

    Patterns:
    - '0522-xxx.xlsx' → '2026-05-22'
    - '2026-05-22xxx.xls' → '2026-05-22'
    - '6052-2026-05-22xxx.xlsx' → '2026-05-22'

    Validates that month is 1-12 and day is 1-31.
    """
    # Pattern 1: ISO format YYYY-MM-DD already in filename
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", filename)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # Pattern 2: MMDD at start of filename (only for .xls/.xlsx files)
    if filename.endswith(('.xls', '.xlsx')):
        m = re.match(r"^(\d{2})(\d{2})", filename)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"2026-{m.group(1)}-{m.group(2)}"

    return None


def is_skip(filename: str) -> bool:
    """Check if file should be skipped (template, output, temp, PDF, non-data)."""
    # Skip PDFs, temp files
    if filename.startswith('~$'):
        return True
    if filename.endswith('.pdf'):
        return True
    if not filename.endswith(('.xls', '.xlsx')):
        return True

    for pat in SKIP_PATTERNS:
        if pat in filename:
            return True

    # Skip output-type files (will be regenerated)
    for pat in SKIP_OUTPUT_PATTERNS:
        if pat in filename:
            return True

    # Skip files that look like monthly settlement PDFs or non-trading data
    skip_keywords = ['月度', '发电企业', '计量记录', '可再生能源']
    for kw in skip_keywords:
        if kw in filename:
            return True

    return False


def scan_files() -> dict[str, list[tuple[Path, str]]]:
    """Scan old directories and group source files by date.

    Returns:
        {date_iso: [(source_path, category)]}
        where category is one of: prediction, actual, dayahead, realtime,
        charge_settlement, discharge_settlement
    """
    grouped: dict[str, list[tuple[Path, str]]] = defaultdict(list)

    for scan_dir in SCAN_DIRS:
        full_dir = ROOT / scan_dir
        if not full_dir.exists():
            continue

        for fpath in full_dir.iterdir():
            if not fpath.is_file():
                continue
            fname = fpath.name

            if is_skip(fname):
                continue

            date_iso = extract_date(fname)
            if date_iso is None:
                continue

            # Categorize
            category = _categorize(fname)
            grouped[date_iso].append((fpath, category))

    return dict(grouped)


def _categorize(filename: str) -> str:
    """Categorize a source file by its content type."""
    fn = filename.lower()
    if "负荷信息预测" in filename or "负荷信息预测" in fn:
        return "prediction"
    if "电网运行实际" in filename:
        return "actual"
    if "日前交易结果" in filename:
        return "dayahead"
    if "实时交易结果" in filename:
        return "realtime"
    if ("结算单" in filename or "结算单" in fn) and ("充电" in filename or "充电" in fn):
        return "charge_settlement"
    if ("结算单" in filename or "结算单" in fn) and ("放电" in filename or "放电" in fn):
        return "discharge_settlement"
    # Fallback: try to detect by size for settlement files
    if "结算单" in filename or "结算单" in fn:
        fsize = os.path.getsize(filename) if os.path.exists(filename) else 0
        return "charge_settlement" if fsize < 15000 else "discharge_settlement"
    return "unknown"


def migrate(dry_run: bool = True, use_copy: bool = False):
    """Migrate old source files to data/raw/YYYY-MM-DD/.

    Args:
        dry_run: If True, preview only.
        use_copy: If True, copy files; if False, create symlinks.
    """
    grouped = scan_files()
    total = sum(len(v) for v in grouped.values())
    print(f"Found {total} source files across {len(grouped)} dates")
    print()

    if dry_run:
        print("[DRY RUN — no files will be moved]\n")

    for date_iso in sorted(grouped.keys()):
        files = grouped[date_iso]
        dest_dir = ROOT / "data" / "raw" / date_iso

        print(f"{date_iso}: {len(files)} files")
        for src_path, category in files:
            dest_path = dest_dir / src_path.name
            print(f"  [{category:<20}] {src_path.name}")

            if not dry_run:
                dest_dir.mkdir(parents=True, exist_ok=True)
                if dest_path.exists():
                    print(f"    SKIP: already exists")
                    continue
                try:
                    if use_copy:
                        shutil.copy2(src_path, dest_path)
                    else:
                        # Try symlink first, fall back to copy on Windows
                        try:
                            os.symlink(src_path, dest_path)
                        except OSError:
                            shutil.copy2(src_path, dest_path)
                except Exception as e:
                    print(f"    ERROR: {e}")

    if dry_run:
        print(f"\nRun with --run to execute migration")
        print(f"Run with --copy --run to copy instead of symlink")
    else:
        print(f"\nMigration complete: {total} files organized")


def show_stats():
    """Show statistics about what would be migrated."""
    grouped = scan_files()

    categories = defaultdict(int)
    total = 0
    for date_iso, files in grouped.items():
        for _, cat in files:
            categories[cat] += 1
            total += 1

    print("Migration Statistics")
    print("=" * 40)
    print(f"Total dates:   {len(grouped)}")
    print(f"Total files:   {total}")
    print()
    print("By category:")
    for cat in sorted(categories.keys()):
        print(f"  {cat:<22}: {categories[cat]}")
    print()
    print("Date range:")
    dates = sorted(grouped.keys())
    if dates:
        print(f"  {dates[0]} → {dates[-1]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate old source files to data/raw/YYYY-MM-DD/"
    )
    parser.add_argument("--run", action="store_true",
                        help="Actually execute migration (default: dry-run)")
    parser.add_argument("--copy", action="store_true",
                        help="Copy files instead of creating symlinks")
    parser.add_argument("--stats", action="store_true",
                        help="Show migration statistics only")
    args = parser.parse_args()

    if args.stats:
        show_stats()
    else:
        migrate(dry_run=not args.run, use_copy=args.copy)