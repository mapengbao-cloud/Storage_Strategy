"""Ingest 0629/0630 日结算收益复盘 into local SQLite per 收益测算工作流程.md.

Steps:
  1. COM refresh: open each output xlsx, RefreshAll + Calculate, save
  2. openpyxl(data_only=True) read 充放测算 Row 4 (19 cols) -> 日结算单收益测算
  3. read 充电日清算费用 (25 rows) -> 用电结算单
  4. read 放电日清算费用 (97 rows) -> 发电结算单
"""
import openpyxl
import os
import sqlite3
import sys

import win32com.client
import pythoncom

PROJECT = r'E:\DataWork\Storage_Strategy'
OUT_DIR = os.path.join(PROJECT, 'output', '日结算单收益测算')
DB_PATH = os.path.join(PROJECT, 'data', 'cache', 'local.db')
DATES = ['0705', '0706']


def com_refresh(path):
    """Open Excel via COM, refresh formulas, save."""
    excel = win32com.client.Dispatch('Excel.Application', pythoncom.CoInitialize())
    excel.Visible = False
    excel.DisplayAlerts = False
    wb = excel.Workbooks.Open(path)
    wb.RefreshAll()
    excel.CalculateUntilAsyncQueriesDone()
    wb.Save()
    wb.Close()
    excel.Quit()


def safe_float(v):
    if v is None:
        return None
    try:
        f = float(v)
        return f
    except (ValueError, TypeError):
        return None


def ingest_one(mmdd):
    path = os.path.join(OUT_DIR, f'{mmdd}-日结算收益复盘.xlsx')
    if not os.path.exists(path):
        print(f'  SKIP {mmdd}: output file not found')
        return False

    print(f'  COM refresh {mmdd} ...')
    com_refresh(path)

    # Read with data_only=True to get cached formula values
    wb = openpyxl.load_workbook(path, data_only=True)

    # --- 1. 充放测算 Row 4, 19 cols (A-S = col 1-19) ---
    ws = wb['充放测算']
    row4 = [ws.cell(row=4, column=c).value for c in range(1, 20)]
    summary_vals = [safe_float(v) for v in row4]

    # --- 2. 充电日清算费用: 25 rows (24 hours + 合计) ---
    # Per 收益测算工作流程.md: Row 5-29 (28/30 cols), 25 rows
    ws_e = wb['充电日清算费用']
    elec_rows = []
    # Data rows: Row 5 to Row 29 (25 rows)
    for r in range(5, 30):
        vals = [ws_e.cell(row=r, column=c).value for c in range(1, ws_e.max_column + 1)]
        elec_rows.append(vals)

    # --- 3. 放电日清算费用: 97 rows (96 points + 合计) ---
    # Per 收益测算工作流程.md: Row 5-101 (37/42 cols), 97 rows
    ws_d = wb['放电日清算费用']
    gen_rows = []
    for r in range(5, 102):
        vals = [ws_d.cell(row=r, column=c).value for c in range(1, ws_d.max_column + 1)]
        gen_rows.append(vals)

    wb.close()

    # --- Write to SQLite ---
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()

    # Fetch actual column names from each table (avoid hardcoded name mismatch)
    def _cols(table):
        cur.execute(f'PRAGMA table_info("{table}")')
        return [r[1] for r in cur.fetchall()]

    sum_cols = _cols('日结算单收益测算')
    elec_cols = _cols('用电结算单')
    gen_cols = _cols('发电结算单')

    # 日结算单收益测算: 1 row per day (date col[0] + 19 data cols)
    placeholders = ','.join(['?'] * len(sum_cols))
    col_list = ','.join([f'"{c}"' for c in sum_cols])
    cur.execute(f'DELETE FROM "日结算单收益测算" WHERE date=?', (mmdd,))
    # summary_vals has 19 values (cols A-S of Row 4); sum_cols has 20 (date + 19)
    cur.execute(f'INSERT OR REPLACE INTO "日结算单收益测算" ({col_list}) VALUES ({placeholders})',
                (mmdd, *summary_vals))

    # 用电结算单: 25 rows
    cur.execute(f'DELETE FROM "用电结算单" WHERE date=?', (mmdd,))
    n_elec_cols = len(elec_cols)
    placeholders_e = ','.join(['?'] * n_elec_cols)
    col_list_e = ','.join([f'"{c}"' for c in elec_cols])
    need_e = n_elec_cols - 1  # exclude date col (supplied as mmdd)
    for row_vals in elec_rows:
        vals = list(row_vals[:need_e]) + [None] * max(0, need_e - len(row_vals))
        # vals[0]=时段, vals[1:]=data
        data_vals = [vals[0]] + [safe_float(v) for v in vals[1:]]
        cur.execute(f'INSERT OR REPLACE INTO "用电结算单" ({col_list_e}) VALUES ({placeholders_e})',
                    (mmdd, *data_vals))

    # 发电结算单: 97 rows
    cur.execute(f'DELETE FROM "发电结算单" WHERE date=?', (mmdd,))
    n_gen_cols = len(gen_cols)
    placeholders_g = ','.join(['?'] * n_gen_cols)
    col_list_g = ','.join([f'"{c}"' for c in gen_cols])
    need_g = n_gen_cols - 1
    for row_vals in gen_rows:
        vals = list(row_vals[:need_g]) + [None] * max(0, need_g - len(row_vals))
        period = vals[0]
        data_vals = [vals[0]] + [safe_float(v) for v in vals[1:]]
        cur.execute(f'INSERT OR REPLACE INTO "发电结算单" ({col_list_g}) VALUES ({placeholders_g})',
                    (mmdd, *data_vals))

    db.commit()
    db.close()
    print(f'  [OK] {mmdd}: summary 1 row, elec {len(elec_rows)} rows, gen {len(gen_rows)} rows')
    return True


def main():
    print('=== Ingesting 日结算收益复盘 into local DB ===')
    for d in DATES:
        print(f'\n--- {d} ---')
        ingest_one(d)
    print('\nDone.')


if __name__ == '__main__':
    main()