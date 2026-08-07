"""Generate daily settlement review (日结算收益复盘).

New architecture — uses monthly templates from assets/templates/ and outputs
to output/日结算单收益测算/.  No RT review dependency (template is self-contained).

Usage:
    python generate_review.py          # batch: DATES list
    python generate_review.py 0621     # single date
"""

import openpyxl
import os
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(BASE)
ASSETS = os.path.join(BASE, 'assets')
OUTPUT = os.path.join(PROJECT, 'output', '日结算单收益测算')
TEMPLATES = os.path.join(PROJECT, 'assets', 'templates', '收益测算')
os.makedirs(OUTPUT, exist_ok=True)

# Default dates for batch mode
DATES = ['0727', '0728', '0729', '0730', '0731', '0801']

# ── template selection ──────────────────────────────────────────

def _get_template(month: int) -> str:
    """Select the correct template for a given month.

    Ref: 收益测算工作流程.md — 模板按月份和结算单版本
    """
    mapping = {
        1:  '日结算收益复盘-1月.xlsx',
        2:  '日结算收益复盘-2月.xlsx',
        3:  '日结算收益复盘-3月.xlsx',
        4:  '日结算收益复盘-4月.xlsx',
        5:  '日结算收益复盘-20260525日前.xlsx',
        6:  '日结算收益复盘-6月.xlsx',
        7:  '日结算收益复盘-7月.xlsx',
        8:  '日结算收益复盘-8月.xlsx',
    }
    name = mapping.get(month, f'日结算收益复盘-{month}月.xlsx')
    path = os.path.join(TEMPLATES, name)
    if not os.path.exists(path):
        raise FileNotFoundError(f'Template not found: {path}')
    return path


# ── helpers ─────────────────────────────────────────────────────

def _is_merged(cell):
    return type(cell).__name__ == 'MergedCell'


def convert_to_numeric(ws):
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if _is_merged(cell) or cell.value is None:
                continue
            if not isinstance(cell.value, str):
                continue
            if str(cell.value).startswith('='):
                continue
            s = str(cell.value).strip()
            try:
                v = float(s)
                cell.value = int(v) if v == int(v) and '.' not in s else v
            except ValueError:
                pass


def copy_sheet_data(src_ws, dst_ws):
    for row in src_ws.iter_rows(min_row=1, max_row=src_ws.max_row, max_col=src_ws.max_column):
        for src_cell in row:
            if src_cell.value is None:
                continue
            dst_cell = dst_ws.cell(row=src_cell.row, column=src_cell.column)
            if _is_merged(dst_cell):
                continue
            if isinstance(dst_cell.value, str) and str(dst_cell.value).startswith('='):
                continue
            dst_cell.value = src_cell.value
            if src_cell.number_format and src_cell.number_format != 'General':
                dst_cell.number_format = src_cell.number_format


# ── main logic ──────────────────────────────────────────────────

def generate_review(date_mmdd: str) -> bool:
    month = date_mmdd[:2]
    day = date_mmdd[2:4]
    date_iso = f'2026-{month}-{day}'
    month_int = int(month)

    charge_stmt = os.path.join(ASSETS, f'6052-{date_iso}德州润津储能科技有限公司结算单-充电.xlsx')
    discharge_stmt = os.path.join(ASSETS, f'6052-{date_iso}德州润津储能科技有限公司结算单-放电.xlsx')
    template_path = _get_template(month_int)
    out_path = os.path.join(OUTPUT, f'{date_mmdd}-日结算收益复盘.xlsx')

    for f in [charge_stmt, discharge_stmt]:
        if not os.path.exists(f):
            print(f'  SKIP {date_mmdd}: Missing {os.path.basename(f)}')
            return False

    # 1. Copy template → output
    shutil.copy2(template_path, out_path)

    # 2. Load
    wb_charge = openpyxl.load_workbook(charge_stmt, data_only=True)
    wb_discharge = openpyxl.load_workbook(discharge_stmt, data_only=True)
    wb_out = openpyxl.load_workbook(out_path)

    # 3. 充电日清算费用 ← charge settlement 日清算数据
    copy_sheet_data(wb_charge['日清算数据'], wb_out['充电日清算费用'])
    convert_to_numeric(wb_out['充电日清算费用'])

    # 4. 放电日清算费用 ← discharge settlement 日清算费用
    copy_sheet_data(wb_discharge['日清算费用'], wb_out['放电日清算费用'])
    convert_to_numeric(wb_out['放电日清算费用'])

    wb_out.save(out_path)
    for wb in [wb_charge, wb_discharge, wb_out]:
        wb.close()
    print(f'[OK] {os.path.basename(out_path)}')
    return True


# ── CLI ─────────────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) > 1:
        dates = [sys.argv[1]]
    else:
        dates = DATES
    if not dates:
        print('Usage: python generate_review.py MMDD')
        print('   or: edit DATES list and run without args')
        sys.exit(1)

    for d in dates:
        generate_review(d)
    print('\nDone.')