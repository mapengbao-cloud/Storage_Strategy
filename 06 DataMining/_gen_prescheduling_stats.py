"""Generate prescheduling classification statistics by date."""
import pymysql, math, openpyxl
from openpyxl.styles import Font, PatternFill
from collections import defaultdict

conn = pymysql.connect(host='rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com', port=3306,
    user='pengyiqiang', password='pengyiqiang123', database='tianrun_new',
    charset='utf8mb4', connect_timeout=10, read_timeout=300)
cur = conn.cursor()

def classify(vals, name=''):
    arr = [v for v in vals if v is not None]
    if len(arr) < 80: return '数据不足', 0
    mean_v = sum(arr)/len(arr)
    if mean_v == 0: return '零出力', 0
    std_v = math.sqrt(sum((x-mean_v)**2 for x in arr)/len(arr))
    cv = (std_v/abs(mean_v))*100 if mean_v != 0 else 0
    has_neg = min(arr) < 0; has_pos = max(arr) > 0
    if has_neg and has_pos:
        if '机' in name or '#' in name: return '一充一放型(抽蓄)', cv
        return '一充一放型', cv
    if has_neg and not has_pos: return '纯充电型', cv
    quarter = 24
    first_q = sum(arr[0:quarter])/quarter; last_q = sum(arr[96-quarter:96])/quarter
    if first_q / max(mean_v, 1) < 0.03 and last_q / max(mean_v, 1) > 0.03: return '日内启机', cv
    if last_q / max(mean_v, 1) < 0.03 and first_q / max(mean_v, 1) > 0.03: return '日内停机', cv
    if cv < 5: return '平稳/直线型', cv
    return '午间调峰机组', cv

NOON_IDX = range(44, 52)
def noon_avg(vals): return sum(vals[i] for i in NOON_IDX)/8
def eve_avg(vals):
    best = -1e9
    for s in range(68, 84-8+1):
        m = sum(vals[s:s+8])/8
        if m > best: best = m
    return best

cur.execute("SELECT DISTINCT date FROM shandong_px_provincial_prescheduling_results ORDER BY date")
all_dates = [str(r[0]) for r in cur.fetchall()]
print(f'Total dates: {len(all_dates)}')

results = []
for i, DATE in enumerate(all_dates):
    cur.execute(f"""SELECT generator_name, time_order, declaration_power
        FROM shandong_px_provincial_prescheduling_results
        WHERE date='{DATE}'
        ORDER BY generator_name, CAST(time_order AS UNSIGNED)""")
    rows = cur.fetchall()
    data = defaultdict(lambda: [0.0]*96)
    for gn, to, pw in rows:
        idx = int(to) - 1
        if 0 <= idx < 96: data[gn][idx] = float(pw or 0)

    thermal = {n: v for n, v in data.items() if '#' in n}
    storage = {n: v for n, v in data.items() if '储能' in n}

    np = {'count': 0, 'noon': 0.0, 'eve': 0.0}
    st = {'count': 0, 'noon': 0.0, 'eve': 0.0}
    ps = {'count': 0, 'noon': 0.0, 'eve': 0.0}

    for n, vals in thermal.items():
        pat, cv = classify(vals, n)
        if pat == '午间调峰机组':
            np['count'] += 1; np['noon'] += noon_avg(vals); np['eve'] += eve_avg(vals)
        elif pat == '平稳/直线型':
            st['count'] += 1; st['noon'] += noon_avg(vals); st['eve'] += eve_avg(vals)
    for n, vals in storage.items():
        ps['count'] += 1; ps['noon'] += noon_avg(vals); ps['eve'] += eve_avg(vals)

    results.append({'date': DATE, 'np': np, 'st': st, 'ps': ps})
    if (i+1) % 10 == 0: print(f'  {i+1}/{len(all_dates)}')

cur.close(); conn.close()

# Write Excel
wb = openpyxl.Workbook()
ws = wb.active; ws.title = '预调度分类统计'
hf = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
hfn = Font(bold=True, color='FFFFFF', size=10)
headers = ['日期', '午间调峰-台数', '午间调峰-午间MW', '午间调峰-晚高峰MW',
           '平稳/直线型-台数', '平稳/直线型-午间MW', '平稳/直线型-晚高峰MW',
           '抽蓄储能-台数', '抽蓄储能-午间MW', '抽蓄储能-晚高峰MW']
for c, h in enumerate(headers, 1):
    cell = ws.cell(row=1, column=c, value=h); cell.font = hfn; cell.fill = hf

for i, r in enumerate(results):
    row = i + 2
    ws.cell(row=row, column=1, value=r['date'])
    ws.cell(row=row, column=2, value=r['np']['count'])
    ws.cell(row=row, column=3, value=round(r['np']['noon'], 0))
    ws.cell(row=row, column=4, value=round(r['np']['eve'], 0))
    ws.cell(row=row, column=5, value=r['st']['count'])
    ws.cell(row=row, column=6, value=round(r['st']['noon'], 0))
    ws.cell(row=row, column=7, value=round(r['st']['eve'], 0))
    ws.cell(row=row, column=8, value=r['ps']['count'])
    ws.cell(row=row, column=9, value=round(r['ps']['noon'], 0))
    ws.cell(row=row, column=10, value=round(r['ps']['eve'], 0))

for c, w in enumerate([12,14,14,16,14,14,20,14,14,20], 1):
    ws.column_dimensions[chr(64+c)].width = w
ws.freeze_panes = 'A2'

# Monthly summary
ws2 = wb.create_sheet('月度汇总')
mo_h = ['月份', '天数', '午间调峰-台数', '午间调峰-午间MW', '午间调峰-晚高峰MW',
        '平稳/直线型-台数', '平稳/直线型-午间MW', '平稳/直线型-晚高峰MW',
        '抽蓄储能-台数', '抽蓄储能-午间MW', '抽蓄储能-晚高峰MW']
for c, h in enumerate(mo_h, 1):
    cell = ws2.cell(row=1, column=c, value=h); cell.font = hfn; cell.fill = hf

monthly = defaultdict(list)
for r in results: monthly[r['date'][:7]].append(r)

for i, m in enumerate(sorted(monthly.keys())):
    items = monthly[m]; row = i + 2
    ws2.cell(row=row, column=1, value=m); ws2.cell(row=row, column=2, value=len(items))
    ws2.cell(row=row, column=3, value=round(sum(it['np']['count'] for it in items)/len(items), 1))
    ws2.cell(row=row, column=4, value=round(sum(it['np']['noon'] for it in items)/len(items), 0))
    ws2.cell(row=row, column=5, value=round(sum(it['np']['eve'] for it in items)/len(items), 0))
    ws2.cell(row=row, column=6, value=round(sum(it['st']['count'] for it in items)/len(items), 1))
    ws2.cell(row=row, column=7, value=round(sum(it['st']['noon'] for it in items)/len(items), 0))
    ws2.cell(row=row, column=8, value=round(sum(it['st']['eve'] for it in items)/len(items), 0))
    ws2.cell(row=row, column=9, value=round(sum(it['ps']['count'] for it in items)/len(items), 1))
    ws2.cell(row=row, column=10, value=round(sum(it['ps']['noon'] for it in items)/len(items), 0))
    ws2.cell(row=row, column=11, value=round(sum(it['ps']['eve'] for it in items)/len(items), 0))

OUT = 'E:/DataWork/Storage_Strategy/output/预调度分类统计_午间晚高峰.xlsx'
wb.save(OUT)
print(f'Saved: {OUT} ({len(results)} days)')
print()
for m in sorted(monthly.keys()):
    items = monthly[m]; n = len(items)
    print(f'  {m} ({n}天): 午间调峰{sum(it["np"]["count"] for it in items)/n:.0f}台, 平稳{sum(it["st"]["count"] for it in items)/n:.0f}台, 抽蓄储能{sum(it["ps"]["count"] for it in items)/n:.0f}台')