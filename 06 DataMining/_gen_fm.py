"""Generate FM daily report from template.

Usage: python _gen_fm.py MMDD [month]
  e.g. python _gen_fm.py 0525     # May 25, auto-detect month=5
       python _gen_fm.py 0303 3   # March 3, explicit month

Template: assets/templates/调频测算/调频收益及报价测算_20260527.xlsx
Output: output/调频收益测算/调频收益及报价测算_MMDD.xlsx
"""
import sqlite3, os, pymysql, openpyxl, shutil, sys
from datetime import date

def safe_float(v):
    try: return float(v) if v is not None else 0.0
    except: return 0.0

def excel_serial(d):
    return (d - date(1899, 12, 30)).days

# ===== Parse args =====
if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

mmdd = sys.argv[1]
month = int(sys.argv[2]) if len(sys.argv) > 2 else int(mmdd[:2])
year = 2026
iso_date = f'{year}-{mmdd[:2]}-{mmdd[2:]}'
serial = excel_serial(date(year, int(mmdd[:2]), int(mmdd[2:])))
print(f'Date: {iso_date}, serial={serial}, month={month}')

# ===== 1. Read data =====
DB_CONFIG = {
    'host': os.getenv('DB_TIANJI_HOST', 'rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com'),
    'port': int(os.getenv('DB_TIANJI_PORT', '3306')),
    'user': os.getenv('DB_TIANJI_USER', 'pengyiqiang'),
    'password': os.getenv('DB_TIANJI_PASSWORD', 'pengyiqiang123'),
    'database': os.getenv('DB_TIANJI_DATABASE', 'tianrun_new'),
}

# 天机库 - 中标价格
conn = pymysql.connect(**DB_CONFIG, connect_timeout=10)
cur = conn.cursor()
cur.execute(f"SELECT time_order, price FROM shandong_px_fm_market_intraday_clearing_price WHERE date='{iso_date}' ORDER BY time_order")
tianji_prices = {}
for r in cur.fetchall():
    if r[1] is not None:
        tianji_prices[r[0]] = float(r[1])
cur.close()
conn.close()

# 本地库
db = sqlite3.connect('data/cache/local.db')
cur = db.cursor()

cur.execute(f"SELECT * FROM 调频日性能记录 WHERE 日期='{iso_date}' ORDER BY 小时")
fm_rows = [r for r in cur.fetchall()]

cur.execute(f'SELECT * FROM 用电结算单 WHERE date="{mmdd}" ORDER BY rowid')
elec_rows = [r for r in cur.fetchall() if r[1] and r[1] not in ('时点', '合计')]

cur.execute(f'SELECT * FROM 发电结算单 WHERE date="{mmdd}" ORDER BY rowid')
gen_rows = [r for r in cur.fetchall() if r[1] and r[1] not in ('时点', '合计')]

cur.execute(f"SELECT * FROM 润津实时出清结果 WHERE date='{iso_date}' ORDER BY time_point")
rt_rows = list(cur.fetchall())

cur.execute(f'SELECT time_point, coefficient FROM 容量分摊系数 WHERE year=2026 AND month={month} ORDER BY time_point')
cap_coeff = {r[0]: float(r[1]) for r in cur.fetchall()}
db.close()

# Filter to hours with valid bid price
fm_hours = [r for r in fm_rows if tianji_prices.get(r[1]) is not None]
if not fm_hours:
    print('No FM hours with bid price found!')
    sys.exit(1)

n = len(fm_hours)
print(f'FM hours: {n} ({[r[1] for r in fm_hours]})')

# ===== 2. Generate output =====
template = r'assets\templates\调频测算\调频收益及报价测算_20260527.xlsx'
os.makedirs(r'output\调频收益测算', exist_ok=True)
out_path = rf'output\调频收益测算\调频收益及报价测算_{mmdd}.xlsx'
shutil.copy2(template, out_path)
wb = openpyxl.load_workbook(out_path)

ws_fm = wb[wb.sheetnames[0]]        # 调频测算
ws_elec = wb[wb.sheetnames[1]]      # 用电结算单
ws_gen = wb[wb.sheetnames[2]]       # 发电结算单
ws_rt = wb[wb.sheetnames[3]]        # 实时出清结果
# [4] 调频产生发用电及损益 -- all formulas, no writing needed
ws_perf = wb[wb.sheetnames[5]]      # 性能记录表格
ws_cap = wb[wb.sheetnames[6]]       # 容量分摊系数

# ---- 性能记录表格 ----
for r in range(2, ws_perf.max_row + 1):
    for c in range(1, 9):
        ws_perf.cell(row=r, column=c).value = None

for i, r in enumerate(fm_hours):
    row = i + 2
    ws_perf.cell(row=row, column=1).value = iso_date
    ws_perf.cell(row=row, column=2).value = r[1]
    ws_perf.cell(row=row, column=3).value = '德州润津储能'
    ws_perf.cell(row=row, column=4).value = safe_float(r[3])
    ws_perf.cell(row=row, column=5).value = safe_float(r[4])
    ws_perf.cell(row=row, column=6).value = safe_float(r[5])
    ws_perf.cell(row=row, column=7).value = safe_float(r[6])
    ws_perf.cell(row=row, column=8).value = safe_float(r[7])

# ---- 调频测算 ----
for r in range(2, 12):
    for c in range(1, 17):
        ws_fm.cell(row=r, column=c).value = None

for i, r in enumerate(fm_hours):
    row = i + 2
    h = r[1]
    # 容量分摊系数: B3=tp1, B{h+2}=tp{h}
    cap_row = 2 + h
    ws_fm.cell(row=row, column=1).value = serial
    ws_fm.cell(row=row, column=2).value = f'=性能记录表格!B{row}'
    ws_fm.cell(row=row, column=3).value = f'=性能记录表格!G{row}'
    ws_fm.cell(row=row, column=4).value = f'=性能记录表格!H{row}'
    ws_fm.cell(row=row, column=5).value = tianji_prices[h]
    ws_fm.cell(row=row, column=6).value = f'=E{row}*D{row}*C{row}'
    ws_fm.cell(row=row, column=7).value = f'=调频产生发用电及损益!E{h+1}'
    ws_fm.cell(row=row, column=8).value = f'=调频产生发用电及损益!F{h+1}'
    ws_fm.cell(row=row, column=9).value = f'=调频产生发用电及损益!G{h+1}'
    ws_fm.cell(row=row, column=10).value = f'=调频产生发用电及损益!H{h+1}'
    ws_fm.cell(row=row, column=11).value = f'=J{row}+H{row}'
    ws_fm.cell(row=row, column=12).value = f'=F{row}+K{row}+M{row}'
    ws_fm.cell(row=row, column=13).value = f'=G{row}*70.5*容量分摊系数!B{cap_row}'

data_end = n + 1
# 均值
ws_fm.cell(row=data_end+1, column=1).value = '均值'
ws_fm.cell(row=data_end+1, column=2).value = '-'
ws_fm.cell(row=data_end+1, column=3).value = f'=AVERAGE(C2:C{data_end})'
ws_fm.cell(row=data_end+1, column=4).value = f'=AVERAGE(D2:D{data_end})'
ws_fm.cell(row=data_end+1, column=5).value = f'=AVERAGE(E2:E{data_end})'
ws_fm.cell(row=data_end+1, column=11).value = f'=AVERAGE(K2:K{data_end})'
ws_fm.cell(row=data_end+1, column=13).value = f'=AVERAGE(M2:M{data_end})'
# 合计
sum_row = data_end + 2
ws_fm.cell(row=sum_row, column=1).value = '合计'
for cl in ['F','G','H','I','J','K','L','M']:
    ws_fm.cell(row=sum_row, column=ord(cl)-64).value = f'=SUM({cl}2:{cl}{data_end})'
# 最低申报价格
min_row = data_end + 4
ws_fm.cell(row=min_row, column=1).value = '最低申报价格'
ws_fm.cell(row=min_row, column=2).value = f'=-(K{data_end+1}+M{data_end+1})/C{data_end+1}/D{data_end+1}'

# ---- 用电结算单 ----
for r in elec_rows:
    tp = r[1]
    if tp == '合计':
        row = 29
        for ci in [22, 23, 24, 25, 26, 27, 28, 29]:
            if ci < len(r):
                ws_elec.cell(row=row, column=ci).value = safe_float(r[ci])
        continue
    h = int(tp.split(':')[0])
    row = 4 + h
    ws_elec.cell(row=row, column=1).value = tp
    ws_elec.cell(row=row, column=3).value = safe_float(r[2])
    ws_elec.cell(row=row, column=4).value = safe_float(r[3])
    ws_elec.cell(row=row, column=5).value = safe_float(r[4])
    ws_elec.cell(row=row, column=28).value = safe_float(r[27])
    ws_elec.cell(row=row, column=29).value = safe_float(r[28])
    ws_elec.cell(row=row, column=30).value = safe_float(r[29])

# ---- 发电结算单 ----
for i, r in enumerate(gen_rows):
    row = 5 + i
    ws_gen.cell(row=row, column=1).value = r[1]
    ws_gen.cell(row=row, column=15).value = safe_float(r[15])
    ws_gen.cell(row=row, column=16).value = safe_float(r[16])
    ws_gen.cell(row=row, column=17).value = safe_float(r[17])
    ws_gen.cell(row=row, column=41).value = safe_float(r[41])
    ws_gen.cell(row=row, column=42).value = safe_float(r[42])

# ---- 实时出清结果 ----
for i, r in enumerate(rt_rows):
    ws_rt.cell(row=2+i, column=5).value = safe_float(r[8])

# ---- 容量分摊系数 ----
# B2 = month label, B3:B26 = 24 timepoint coefficients
ws_cap.cell(row=2, column=2).value = f'{month}月'
for tp in range(1, 25):
    ws_cap.cell(row=2+tp, column=2).value = cap_coeff.get(tp, 0)

wb.save(out_path)
print(f'Saved: {out_path}')
print(f'Rows: data=2~{data_end}, avg={data_end+1}, sum={sum_row}, minPrice={min_row}')
print('Done')