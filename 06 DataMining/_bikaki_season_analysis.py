"""必开机组季节变化分析
目标：判断「必开机组」(全天出力恒定的火电机组, CV<5%)的：
  - 台数、总出力是否随季节变化
  - 是否为固定值 / 占直调负荷比例 / 占火电开机比例
数据窗口：2025-07, 2025-08（保供夏季）, 2026-02（冬季）, 2026-05下~06（过渡季）, 2026-07（夏季）
输出: _tmp_bikaki_analysis.json + HTML
"""
import pymysql, os, json, math
from collections import defaultdict

for line in open(r'E:\DataWork\Storage_Strategy\.env', encoding='utf-8'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

conn = pymysql.connect(host=os.getenv('DB_TIANJI_HOST'), port=int(os.getenv('DB_TIANJI_PORT', 3306)),
    user=os.getenv('DB_TIANJI_USER'), password=os.getenv('DB_TIANJI_PASSWORD'),
    database=os.getenv('DB_TIANJI_DATABASE'), charset='utf8mb4', connect_timeout=10, read_timeout=120)
cur = conn.cursor()

# ── 1. 取所有预调度数据（火电 + 储能区分） ──
print('Loading prescheduling data...')
cur.execute("""SELECT date, generator_name, time_order, declaration_power
    FROM shandong_px_provincial_prescheduling_results
    ORDER BY date, generator_name, time_order""")
rows = cur.fetchall()
print(f'  {len(rows):,} rows')

# 组织: {date: {gen_name: [96 points]}}
data = defaultdict(lambda: defaultdict(dict))
for r in rows:
    d = str(r[0])
    name = r[1]
    try:
        to = int(r[2])  # time_order '1'..'96'
    except (ValueError, TypeError):
        continue
    p = float(r[3] or 0)
    data[d][name][to] = p

# 过滤出有效日期（火电机组数>=50的日期才算完整数据）
valid_dates = []
for d in sorted(data.keys()):
    thermal_cnt = sum(1 for n in data[d] if ('机' in n or '#' in n) and '储能' not in n)
    if thermal_cnt >= 50:
        valid_dates.append(d)
print(f'  valid dates (thermal>=50): {len(valid_dates)}')

# ── 2. 取直调负荷（实际）作对比 ──
print('Loading actual dispatched load...')
cur.execute("""SELECT date, time_order, actual_dispatched_load
    FROM shandong_px_spot_actual_load_info
    ORDER BY date, time_order""")
dispatched = defaultdict(dict)
for r in cur.fetchall():
    dispatched[str(r[0])][int(r[1])] = float(r[2] or 0)

# ── 3. 取火电日前出清台数 + 出力（用于对比必开占比） ──
print('Loading dayahead thermal clearing...')
cur.execute("""SELECT date, time_point, thermal_clearing, thermal_number
    FROM shandong_px_dayahead_clearing_quantity_number
    ORDER BY date, time_point""")
da_thermal = defaultdict(dict)
for r in cur.fetchall():
    d = str(r[0])
    # time_point '00:15' -> 1
    tp = r[1]
    try:
        h, m = map(int, tp.split(':'))
        to = (h * 60 + m) // 15
        if to == 0: to = 96  # 24:00 case
        da_thermal[d][to] = {'power': float(r[2] or 0) * 4, 'num': float(r[3] or 0)}
    except Exception:
        pass

cur.close(); conn.close()

# ── 4. 逐日分类机组 ──
def classify_96(arr):
    """返回 (pattern, cv, mean, peak, trough). arr = 96点list."""
    vals = [v for v in arr if v is not None]
    if len(vals) < 80:
        return 'insufficient', 0, 0, 0, 0
    mean_v = sum(vals) / len(vals)
    if mean_v == 0:
        return 'zero', 0, 0, 0, 0
    std_v = math.sqrt(sum((x - mean_v)**2 for x in vals) / len(vals))
    cv = (std_v / abs(mean_v)) * 100
    peak = max(vals); trough = min(vals)
    if trough < 0 and peak > 0:
        return 'pumped_storage', cv, mean_v, peak, trough
    if trough < 0:
        return 'pure_charge', cv, mean_v, peak, trough
    if cv < 5:
        return 'must_run', cv, mean_v, peak, trough
    return 'regulating', cv, mean_v, peak, trough

results = []
unit_patterns = defaultdict(lambda: defaultdict(int))  # {gen_name: {pattern: count}}
for d in valid_dates:
    thermal_units = {}
    for name, pts in data[d].items():
        if '储能' in name: continue
        if not ('机' in name or '#' in name): continue
        # build 96-point array
        arr = [pts.get(i) for i in range(1, 97)]
        thermal_units[name] = arr

    must_run_units = []
    must_run_total_power = 0
    regulating_units = []
    regulating_total_power = 0
    total_thermal_power = 0
    for name, arr in thermal_units.items():
        pattern, cv, mean_v, peak, trough = classify_96(arr)
        if pattern in ('insufficient', 'zero', 'pumped_storage', 'pure_charge'):
            continue
        unit_patterns[name][pattern] += 1
        total_thermal_power += mean_v
        if pattern == 'must_run':
            must_run_units.append(name)
            must_run_total_power += mean_v
        else:
            regulating_units.append(name)
            regulating_total_power += mean_v

    # 直调负荷均值
    disp_pts = dispatched.get(d, {})
    disp_mean = sum(disp_pts.values()) / len(disp_pts) if disp_pts else None

    # 火电日前出清（均值 + 台数均值）
    da_pts = da_thermal.get(d, {})
    da_power_mean = sum(p['power'] for p in da_pts.values()) / len(da_pts) if da_pts else None
    da_num_mean = sum(p['num'] for p in da_pts.values()) / len(da_pts) if da_pts else None

    results.append({
        'date': d,
        'month': d[:7],
        'must_run_count': len(must_run_units),
        'must_run_power': round(must_run_total_power, 1),
        'regulating_count': len(regulating_units),
        'regulating_power': round(regulating_total_power, 1),
        'total_thermal_units': len(must_run_units) + len(regulating_units),
        'total_thermal_power': round(total_thermal_power, 1),
        'must_run_ratio_power': round(must_run_total_power / total_thermal_power * 100, 1) if total_thermal_power else 0,
        'dispatched_load_mean': round(disp_mean, 1) if disp_mean else None,
        'must_run_pct_of_load': round(must_run_total_power / disp_mean * 100, 1) if disp_mean else None,
        'da_thermal_num': round(da_num_mean, 1) if da_num_mean else None,
        'must_run_pct_of_thermal_num': round(len(must_run_units) / da_num_mean * 100, 1) if da_num_mean else None,
        'must_run_units': must_run_units,
    })

print(f'\nAnalyzed: {len(results)} days')
print(f'Total unique thermal units: {len(unit_patterns)}')

# ── 5. 月度汇总 ──
monthly = defaultdict(list)
for r in results:
    monthly[r['month']].append(r)

print('\n=== 月度汇总（必开机组） ===')
print(f'{"月份":<10}{"天数":<5}{"必开台数":<10}{"必开出力MW":<14}{"占火电功率%":<14}{"占直调负荷%":<14}{"占开机台数%":<14}')
for m in sorted(monthly.keys()):
    rs = monthly[m]
    n = len(rs)
    cnt = sum(r['must_run_count'] for r in rs) / n
    pwr = sum(r['must_run_power'] for r in rs) / n
    pct_t = sum(r['must_run_ratio_power'] for r in rs) / n
    pct_l = sum(r['must_run_pct_of_load'] for r in rs if r['must_run_pct_of_load']) / max(1, sum(1 for r in rs if r['must_run_pct_of_load']))
    pct_n = sum(r['must_run_pct_of_thermal_num'] for r in rs if r['must_run_pct_of_thermal_num']) / max(1, sum(1 for r in rs if r['must_run_pct_of_thermal_num']))
    print(f'{m:<10}{n:<5}{cnt:<10.1f}{pwr:<14.0f}{pct_t:<14.1f}{pct_l:<14.1f}{pct_n:<14.1f}')

# ── 6. 必开机组名单稳定性（跨月共有） ──
print('\n=== 必开机组名单稳定性 ===')
# 每月的必开机组集合（该月内出现次数 >= 该月天数*0.7 的机组）
month_must_run_sets = {}
for m in sorted(monthly.keys()):
    rs = monthly[m]
    n = len(rs)
    counter = defaultdict(int)
    for r in rs:
        for u in r['must_run_units']:
            counter[u] += 1
    stable = {u for u, c in counter.items() if c >= n * 0.7}
    month_must_run_sets[m] = stable
    print(f'{m}: {len(stable)} stable must-run units')

# 交集
all_months = sorted(month_must_run_sets.keys())
if all_months:
    common = month_must_run_sets[all_months[0]]
    for m in all_months[1:]:
        common &= month_must_run_sets[m]
    print(f'\n所有月份共同的必开机组: {len(common)}')
    for u in sorted(common):
        print(f'  {u}')

# ── 7. 机组模式跨月分布（看哪些机组是「永久必开」vs「季节切换」） ──
print('\n=== 典型机组模式（出现≥5天的机组） ===')
always_must_run = []
sometimes = []
for name, pat_cnt in unit_patterns.items():
    total = sum(pat_cnt.values())
    if total < 5: continue
    mr = pat_cnt.get('must_run', 0)
    rg = pat_cnt.get('regulating', 0)
    if mr / total >= 0.9:
        always_must_run.append((name, total, mr))
    elif mr > 0 and rg > 0:
        sometimes.append((name, total, mr, rg))

print(f'始终必开 (>=90% 天数为必开): {len(always_must_run)}')
print(f'模式切换 (有时必开有时调节): {len(sometimes)}')

# ── 8. 保存结果 ──
out = {
    'daily': results,
    'monthly_summary': [
        {
            'month': m,
            'days': len(monthly[m]),
            'must_run_count_avg': sum(r['must_run_count'] for r in monthly[m]) / len(monthly[m]),
            'must_run_power_avg': sum(r['must_run_power'] for r in monthly[m]) / len(monthly[m]),
            'must_run_pct_thermal_avg': sum(r['must_run_ratio_power'] for r in monthly[m]) / len(monthly[m]),
            'must_run_pct_load_avg': sum(r['must_run_pct_of_load'] for r in monthly[m] if r['must_run_pct_of_load']) / max(1, sum(1 for r in monthly[m] if r['must_run_pct_of_load'])),
            'must_run_pct_num_avg': sum(r['must_run_pct_of_thermal_num'] for r in monthly[m] if r['must_run_pct_of_thermal_num']) / max(1, sum(1 for r in monthly[m] if r['must_run_pct_of_thermal_num'])),
        }
        for m in sorted(monthly.keys())
    ],
    'stable_must_run_by_month': {m: sorted(list(s)) for m, s in month_must_run_sets.items()},
    'always_must_run_units': sorted([x[0] for x in always_must_run]),
    'switching_units': sorted([x[0] for x in sometimes]),
}
with open('_tmp_bikaki_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f'\nSaved: _tmp_bikaki_analysis.json')
