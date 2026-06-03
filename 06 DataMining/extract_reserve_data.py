"""Extract reserve capacity data from tianrun_new for analysis HTML.
Edit START_DATE / END_DATE below to change the query range.
Run from project root: python "06 DataMining/extract_reserve_data.py"
"""
import pymysql, json, os
from collections import defaultdict

# ===== DATE_RANGE: 修改这里的日期范围 =====
START_DATE = '2026-05-21'
END_DATE = '2026-05-27'

DB = {
    'host': 'rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com',
    'port': 3306,
    'user': 'pengyiqiang',
    'password': 'pengyiqiang123',
    'database': 'tianrun_new',
}

conn = pymysql.connect(**DB)
c = conn.cursor()
data = defaultdict(lambda: {'da_pos': [], 'da_neg': [], 'act_pos': [], 'act_neg': []})

# 日前备用
c.execute(
    "SELECT date, type, time_order, reserve_capacity "
    "FROM shandong_px_spot_dayahead_reserve_capacity_info "
    "WHERE date >= %s AND date <= %s ORDER BY date, type, time_order",
    (START_DATE, END_DATE))
for d, typ, _, cap in c.fetchall():
    k = 'da_pos' if typ == '正备用' else 'da_neg'
    data[str(d)][k].append(float(cap))

# 实际备用
c.execute(
    "SELECT date, type, time_order, reserve_capacity "
    "FROM shandong_px_spot_actual_reserve_capacity_info "
    "WHERE date >= %s AND date <= %s ORDER BY date, type, time_order",
    (START_DATE, END_DATE))
for d, typ, _, cap in c.fetchall():
    k = 'act_pos' if typ == '正备用' else 'act_neg'
    data[str(d)][k].append(float(cap))

conn.close()

out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        '_tmp_reserve_data.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)

dates = sorted(data.keys())
print(f'Extracted {len(dates)} dates: {dates[0]} ~ {dates[-1]}')
for d in dates:
    dd = data[d]
    print(f'  {d}: da_pos={len(dd["da_pos"])}pts, act_pos={len(dd["act_pos"])}pts')
print(f'Saved to: {out_path}')