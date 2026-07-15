"""Generate 0525 调频收益及报价测算 using 0527 template.

Template sheets:
  [0] 调频测算 - main sheet, formulas reference 性能记录表格 & 调频产生用电及收入
  [1] 用电结算单 - 24h electricity data
  [2] 发电结算单 - 96 quarter generation data
  [3] 实时出清结果 - 96point clearing + 24h aggregation formulas
  [4] 调频产生用电及收入 - 24h FM-specific calculations (formulas)
  [5] 性能记录表格 - FM performance data
  [6] 容量分摊系数 - capacity coefficients

Only write data to source cells; keep all formulas intact.
"""
import sqlite3, os, pymysql, openpyxl, shutil

def safe_float(v):
    try: return float(v) if v is not None else 0.0
    except: return 0.0

# ===== 1. Read data =====
DB_CONFIG = {
    'host': os.getenv('DB_TIANJI_HOST', 'rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com'),
    'port': int(os.getenv('DB_TIANJI_PORT', '3306')),
    'user': os.getenv('DB_TIANJI_USER', 'pengyiqiang'),
    'password': os.getenv('DB_TIANJI_PASSWORD', 'pengyiqiang123'),
    'database': os.getenv('DB_TIANJI_DATABASE', 'tianrun_new'),
}
conn = pymysql.connect(**DB_CONFIG, connect_timeout=10)
cur = conn.cursor()
cur.execute("SELECT time_order, price FROM shandong_px_fm_market_intraday_clearing_price WHERE date='2026-05-25' ORDER BY time_order")
tianji_prices = {r[0]: float(r[1]) if r[1] else 0.0 for r in cur.fetchall()}
cur.close()
conn.close()

db = sqlite3.connect('data/cache/local.db')
cur = db.cursor()
cur.execute("SELECT * FROM 调频日性能记录 WHERE 日期='2026-05-25' ORDER BY 小时")
fm_rows = [r for r in cur.fetchall()]

cur.execute('SELECT * FROM 用电结算单 WHERE date="0525" ORDER BY rowid')
elec_rows = [r for r in cur.fetchall() if r[1] and r[1] not in ('时点', '合计')]

cur.execute('SELECT * FROM 发电结算单 WHERE date="0525" ORDER BY rowid')
gen_rows = [r for r in cur.fetchall() if r[1] and r[1] not in ('时点', '合计')]

cur.execute("SELECT * FROM 润津实时出清结果 WHERE date='2026-05-25' ORDER BY time_point")
rt_rows = list(cur.fetchall())

cur.execute('SELECT time_point, coefficient FROM 容量分摊系数 WHERE year=2026 AND month=5 ORDER BY time_point')
cap_coeff = {r[0]: float(r[1]) for r in cur.fetchall()}
db.close()

# ===== 2. Generate output =====
template = r'assets\templates\调频测算\调频收益及报价测算_20260527.xlsx'
out_path = r'output\调频收益测算\调频收益及报价测算_0525.xlsx'
shutil.copy2(template, out_path)
wb = openpyxl.load_workbook(out_path)

ws_fm = wb[wb.sheetnames[0]]      # 调频测算
ws_elec = wb[wb.sheetnames[1]]    # 用电结算单
ws_gen = wb[wb.sheetnames[2]]     # 发电结算单
ws_rt = wb[wb.sheetnames[3]]      # 实时出清结果
ws_fm_detail = wb[wb.sheetnames[4]]  # 调频产生用电及收入
ws_perf = wb[wb.sheetnames[5]]    # 性能记录表格
ws_cap = wb[wb.sheetnames[6]]     # 容量分摊系数

# ---- 性能记录表格 ----
# Clear old data, write 6 rows for 0525
for r in range(2, ws_perf.max_row + 1):
    for c in range(1, 9):
        ws_perf.cell(row=r, column=c).value = None

for i, r in enumerate(fm_rows):
    row = i + 2
    ws_perf.cell(row=row, column=1).value = '2026-05-25'
    ws_perf.cell(row=row, column=2).value = r[1]       # 小时
    ws_perf.cell(row=row, column=3).value = '德州润津储能'
    ws_perf.cell(row=row, column=4).value = safe_float(r[3])  # AGC K1
    ws_perf.cell(row=row, column=5).value = safe_float(r[4])  # AGC K2
    ws_perf.cell(row=row, column=6).value = safe_float(r[5])  # AGC K3
    ws_perf.cell(row=row, column=7).value = safe_float(r[6])  # Kp
    ws_perf.cell(row=row, column=8).value = safe_float(r[7])  # 调节容量

# ---- 调频测算 ----
# Clear old data rows, write 6 data rows (R2-R7)
for r in range(2, 12):
    for c in range(1, 17):
        ws_fm.cell(row=r, column=c).value = None

# R1: headers (keep formulas by not touching)
# R2-R7: data rows = 6 hours
for i, r in enumerate(fm_rows):
    row = i + 2
    ws_fm.cell(row=row, column=1).value = 46167  # 2026-05-25
    ws_fm.cell(row=row, column=2).value = f"=性能记录表格!B{row}"  # 时点
    ws_fm.cell(row=row, column=3).value = f"=性能记录表格!G{row}"  # Kp
    ws_fm.cell(row=row, column=4).value = f"=性能记录表格!H{row}"  # 调节深度
    ws_fm.cell(row=row, column=5).value = tianji_prices.get(r[1], 0.0)  # 中标价格
    ws_fm.cell(row=row, column=6).value = f"=E{row}*D{row}*C{row}"  # 调频收益
    ws_fm.cell(row=row, column=7).value = f"=调频产生发用电及损益!E{r[1]+1}"  # 调频用电量
    ws_fm.cell(row=row, column=8).value = f"=调频产生发用电及损益!F{r[1]+1}"  # 用电支出
    ws_fm.cell(row=row, column=9).value = f"=调频产生发用电及损益!G{r[1]+1}"  # 调频发电量
    ws_fm.cell(row=row, column=10).value = f"=调频产生发用电及损益!H{r[1]+1}"  # 发电收入
    ws_fm.cell(row=row, column=11).value = f"=J{row}+H{row}"  # 现货损益
    ws_fm.cell(row=row, column=12).value = f"=F{row}+K{row}+M{row}"  # 综合收益
    ws_fm.cell(row=row, column=13).value = f"=G{row}*容量分摊系数!$C${15+r[1]}*容量分摊系数!$B$1"  # 容量分摊

# R8: 均值
data_end = len(fm_rows) + 1  # R7 for 6 rows
ws_fm.cell(row=data_end+1, column=1).value = '均值'
ws_fm.cell(row=data_end+1, column=2).value = '-'
ws_fm.cell(row=data_end+1, column=3).value = f"=AVERAGE(C2:C{data_end})"
ws_fm.cell(row=data_end+1, column=4).value = f"=AVERAGE(D2:D{data_end})"
ws_fm.cell(row=data_end+1, column=5).value = f"=AVERAGE(E2:E{data_end})"
ws_fm.cell(row=data_end+1, column=11).value = f"=AVERAGE(K2:K{data_end})"
ws_fm.cell(row=data_end+1, column=13).value = f"=AVERAGE(M2:M{data_end})"

# R9: 合计
sum_row = data_end + 2
ws_fm.cell(row=sum_row, column=1).value = '合计'
ws_fm.cell(row=sum_row, column=6).value = f"=SUM(F2:F{data_end})"
ws_fm.cell(row=sum_row, column=7).value = f"=SUM(G2:G{data_end})"
ws_fm.cell(row=sum_row, column=8).value = f"=SUM(H2:H{data_end})"
ws_fm.cell(row=sum_row, column=9).value = f"=SUM(I2:I{data_end})"
ws_fm.cell(row=sum_row, column=10).value = f"=SUM(J2:J{data_end})"
ws_fm.cell(row=sum_row, column=11).value = f"=SUM(K2:K{data_end})"
ws_fm.cell(row=sum_row, column=12).value = f"=SUM(L2:L{data_end})"
ws_fm.cell(row=sum_row, column=13).value = f"=SUM(M2:M{data_end})"

# R11: 最低申报价格
min_row = data_end + 4
ws_fm.cell(row=min_row, column=1).value = '最低申报价格'
ws_fm.cell(row=min_row, column=2).value = f"=-(K{data_end+1}+M{data_end+1})/C{data_end+1}/D{data_end+1}"

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
    ws_elec.cell(row=row, column=3).value = safe_float(r[2])   # 用电量
    ws_elec.cell(row=row, column=4).value = safe_float(r[3])   # 电价
    ws_elec.cell(row=row, column=5).value = safe_float(r[4])   # 电费
    ws_elec.cell(row=row, column=28).value = safe_float(r[27]) # 总结算电量
    ws_elec.cell(row=row, column=29).value = safe_float(r[28]) # 总结算电价
    ws_elec.cell(row=row, column=30).value = safe_float(r[29]) # 总结算电费

# ---- 发电结算单 ----
for i, r in enumerate(gen_rows):
    row = 5 + i
    ws_gen.cell(row=row, column=1).value = r[1]
    ws_gen.cell(row=row, column=15).value = safe_float(r[15])  # 实时电量
    ws_gen.cell(row=row, column=16).value = safe_float(r[16])  # 实时电价
    ws_gen.cell(row=row, column=17).value = safe_float(r[17])  # 实时电费
    ws_gen.cell(row=row, column=41).value = safe_float(r[41])  # 总结算电量
    ws_gen.cell(row=row, column=42).value = safe_float(r[42])  # 总结算电费

# ---- 实时出清结果 ----
# E: 96点实时出清电量, I: 96点实际发电量(=发电结算单!AO)
for i, r in enumerate(rt_rows):
    row = 2 + i
    energy = safe_float(r[8])
    ws_rt.cell(row=row, column=5).value = energy  # 96点出清电量
    # I column is already formula =发电结算单!AO, no need to write

# ---- 容量分摊系数 ----
ws_cap.cell(row=1, column=2).value = 70.5
for tp in range(1, 25):
    ws_cap.cell(row=7+tp, column=3).value = cap_coeff.get(tp, 0)

wb.save(out_path)
print(f'Saved: {out_path}')
print(f'FM hours: {len(fm_rows)} ({[r[1] for r in fm_rows]})')
print('Done')