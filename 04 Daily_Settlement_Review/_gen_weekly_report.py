"""Generate weekly settlement report (0720-0726) per 收益测算工作流程.md 第六节.

Steps:
  1. Copy last week's xlsx as template → output/日结算单收益测算/周报/日结算单收益测算_周报_0720-0726.xlsx
  2. openpyxl write Row 2-8 (A-T, 20 cols): A=date MMDD, B-T = DB cols 2-20
  3. Row 9 formulas preserved (Excel recalculates on open)
  4. Compute Row9 values in Python (= same formulas) → generate txt report

调频数据来源 (3 处拼合):
  - 调频补偿金额 → 日结算单收益测算 表 R列 (调频补偿与分摊合计) 周合计
  - 中标时段数 + 中标均价 → 天机 shandong_px_fm_market_intraday_clearing_price (润津 member_id, price非空)
  - 综合性能 Kp → 03 Real-time_Trading_Review/assets/调频性能记录表格/YYYY-MM-DD日性能记录表格.xlsx col7

Text report format (per 周报要求.txt + 收益测算工作流程.md 六):
  MMDD-MMDD
  上周收益：P9/10000万（其中过网费、容量分摊等|S9|/10000万）
  实时市场：Q9/10000万（充电量：|C9|MWh；放电量：L9MWh；价差：O9元/MWh）
  日前套利：0万
  调频补偿：R9/10000万元（中标时段：N个，中标均价：X，性能：K）

  数据来源：日结算单收益测算_周报_0720-0726.xlsx
"""
import openpyxl
import os
import shutil
import sqlite3
import sys
import glob

PROJECT = r'E:\DataWork\Storage_Strategy'
OUT_DIR = os.path.join(PROJECT, 'output', '日结算单收益测算', '周报')
DB_PATH = os.path.join(PROJECT, 'data', 'cache', 'local.db')
TEMPLATE = os.path.join(OUT_DIR, '日结算单收益测算_周报_0720-0726.xlsx')  # 上周周报作模板
FM_PERF_DIR = os.path.join(PROJECT, '03 Real-time_Trading_Review', 'assets', '调频性能记录表格')
MEMBER_ID = 'b9e64e64a713458eba94c9af05c0a757'

DATES = ['0727', '0728', '0729', '0730', '0731', '0801', '0802']
RANGE_LABEL = '0727-0802'


def _load_env():
    """Load .env so src.data.db can resolve 天机 DB credentials."""
    env_path = os.path.join(PROJECT, '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip()


def safe_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None



def load_db_rows():
    """Load 7 days data from 日结算单收益测算 table. Returns {mmdd: row_tuple}."""
    db = sqlite3.connect(DB_PATH)
    cols = [r[1] for r in db.execute('PRAGMA table_info(日结算单收益测算)').fetchall()]
    col_sql = ','.join([f'"{c}"' for c in cols])
    rows = {}
    for d in DATES:
        r = db.execute(f'SELECT {col_sql} FROM 日结算单收益测算 WHERE date=?', (d,)).fetchone()
        rows[d] = r
    db.close()
    return rows, cols


def write_weekly_xlsx(rows):
    """Copy template, write Row 2-8 data (A-T = date + 19 data cols)."""
    out_xlsx = os.path.join(OUT_DIR, f'日结算单收益测算_周报_{RANGE_LABEL}.xlsx')
    shutil.copy2(TEMPLATE, out_xlsx)

    wb = openpyxl.load_workbook(out_xlsx)
    ws = wb.active

    for i, d in enumerate(DATES):
        r = rows[d]
        excel_row = 2 + i  # Row 2-8
        if r is None:
            print(f'  WARN {d} not in DB, leaving blank')
            continue
        ws.cell(row=excel_row, column=1).value = d  # A = date MMDD
        for j in range(19):  # B-T = DB cols 2-20
            ws.cell(row=excel_row, column=2 + j).value = safe_float(r[j + 1])

    wb.save(out_xlsx)
    wb.close()
    print(f'[OK] {os.path.basename(out_xlsx)}')
    return out_xlsx


def compute_row9(rows):
    """Compute Row9 values from DB data (same as Excel Row9 formulas).

    Row9 formulas (from template):
      B9=D9/C9, C9=SUM(C), D9=SUM(D), ... J9=AVERAGE(J),
      K9=M9/L9, L9=SUM(L), M9=SUM(M), N9=SUM(N), O9=K9-B9,
      P9=SUM(P), Q9=SUM(Q), R9=SUM(R), S9=SUM(S), T9=SUM(T)
    """
    # Gather per-day column sums (DB cols 2-20 = indices 1-19)
    sums = [0.0] * 19  # 19 data cols
    n_j = 0  # 容量分摊系数 count for average
    j_vals = []
    for d in DATES:
        r = rows[d]
        if r is None:
            continue
        for j in range(19):
            v = safe_float(r[j + 1])
            if v is not None:
                sums[j] += v
        # J (col 9 in 0-based data = index 8) = 容量分摊系数, use average
        jv = safe_float(r[9])  # DB col 10 = 容量分摊系数, 0-based index 9
        if jv is not None:
            j_vals.append(jv)

    # Map sums to Excel column letters (B=col2 ... T=col20)
    # data col j (0-based) → Excel col (j+2)
    # C=col3 (idx 1), D=col4 (idx 2), L=col12 (idx 10), M=col13 (idx 11)
    C9 = sums[1]    # 充电电量
    D9 = sums[2]    # 交易充电费用
    L9 = sums[10]   # 放电电量
    M9 = sums[11]   # 放电电费
    P9 = sums[14]   # 结算单发用合计
    Q9 = sums[15]   # 实时市场充放合计
    R9 = sums[16]   # 调频补偿与分摊合计
    S9 = sums[17]   # 结算单外合计
    T9 = sums[18]   # 总收益

    B9 = D9 / C9 if C9 else 0          # 加权充电均价
    K9 = M9 / L9 if L9 else 0          # 加权放电均价
    O9 = K9 - B9                       # 充放价差

    return {
        'B9': B9, 'C9': C9, 'D9': D9, 'K9': K9, 'L9': L9, 'M9': M9,
        'O9': O9, 'P9': P9, 'Q9': Q9, 'R9': R9, 'S9': S9, 'T9': T9,
    }


def load_fm_data():
    """Fetch 调频补偿合计(R列周合计) + 中标时段/均价(日内出清) + Kp(性能记录表).

    Returns dict: {compensation_wan, n_periods, avg_price, kp_avg}
    """
    # 1. 调频补偿金额: 周合计 R9 (调频补偿与分摊合计 = DB col 18, 0-based 17)
    # 与 r9['R9'] 一致, 在 generate_txt 时用 r9 即可; 这里单独取用于汇总
    r9 = compute_row9(load_db_rows()[0])
    compensation = r9['R9']

    _load_env()
    n_periods = 0
    avg_price = 0.0
    kp_vals = []

    # 2. 中标时段数 + 均价: 天机日内调频出清表
    try:
        sys.path.insert(0, PROJECT)  # 让 src 可被 import
        from src.data.db import query
        all_prices = []
        for d in DATES:
            iso = f'2026-{d[:2]}-{d[2:]}'
            rows = query(
                "SELECT price FROM shandong_px_fm_market_intraday_clearing_price "
                "WHERE date=%s AND member_id=%s AND price IS NOT NULL",
                (iso, MEMBER_ID),
            )
            all_prices.extend(float(r['price']) for r in rows if r['price'] is not None)
        n_periods = len(all_prices)
        if all_prices:
            avg_price = sum(all_prices) / len(all_prices)
    except Exception as e:
        print(f'  WARN 天机调频出清查询失败: {e}')

    # 3. 综合性能 Kp: 性能记录表格 (col7 = 综合性能指标Kp)
    kp_list = []
    for d in DATES:
        iso = f'2026-{d[:2]}-{d[2:]}'
        files = glob.glob(os.path.join(FM_PERF_DIR, f'{iso}日性能记录表格*.xlsx'))
        for f in files:
            try:
                wb = openpyxl.load_workbook(f, data_only=True)
                ws = wb.active
                for r in range(2, ws.max_row + 1):
                    kp = ws.cell(row=r, column=7).value
                    if kp is not None:
                        kp_list.append(float(kp))
                wb.close()
            except Exception as e:
                print(f'  WARN 读取性能表 {f} 失败: {e}')
    kp_avg = (sum(kp_list) / len(kp_list)) if kp_list else 0.0

    return {
        'compensation': compensation,        # 元
        'n_periods': n_periods,               # 个
        'avg_price': avg_price,               # 元/MW
        'kp_avg': kp_avg,                     # Kp
        'kp_count': len(kp_list),
    }


def generate_txt(r9, fm):
    """Generate text weekly report per 周报要求.txt format."""
    out_txt = os.path.join(OUT_DIR, f'日结算单收益测算_周报_{RANGE_LABEL}.txt')

    def wan(v):  # 元 → 万元, 2 decimals
        return f'{v / 10000:.2f}'

    def abs_wan(v):
        return f'{abs(v) / 10000:.2f}'

    def mwh_int(v):  # MWh, round to int (match 0706-0712 style)
        return f'{round(abs(v))}'

    def price_int(v):  # 元/MWh, round to int
        return f'{round(v)}'

    # 调频行: 有补偿则填实际值, 无补偿填0
    if fm['compensation'] != 0 and fm['n_periods'] > 0:
        # 金额万元保留3位(对标0706-0712的1.342)
        comp_wan = f'{fm["compensation"] / 10000:.3f}'
        # 均价保留4位
        avg_p = f'{fm["avg_price"]:.4f}'
        # Kp 保留4位
        kp_str = f'{fm["kp_avg"]:.4f}' if fm['kp_avg'] > 0 else ''
        fm_line = f'调频补偿：{comp_wan}万元（中标时段：{fm["n_periods"]}个，中标均价：{avg_p}，性能：{kp_str}）'
    else:
        fm_line = '调频补偿：0万元（中标时段：个，中标均价：，性能：）'

    lines = [
        RANGE_LABEL,
        f'上周收益：{wan(r9["P9"])}万（其中过网费、容量分摊等{abs_wan(r9["S9"])}万）',
        f'实时市场：{wan(r9["Q9"])}万（充电量：{mwh_int(r9["C9"])}MWh；放电量：{mwh_int(r9["L9"])}MWh；价差：{price_int(r9["O9"])}元/MWh）',
        '日前套利：0万',
        fm_line,
        '',
        f'数据来源：日结算单收益测算_周报_{RANGE_LABEL}.xlsx',
    ]

    with open(out_txt, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'[OK] {os.path.basename(out_txt)}')
    return out_txt


def generate_analysis_html():
    """Build _tmp_html_data.json + generate 竞价空间_电价_天气综合分析 HTML."""
    import json
    import pymysql
    import urllib.request
    import time

    iso_dates = [f'2026-{d[:2]}-{d[2:]}' for d in DATES]
    TIMES = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0, 15, 30, 45)]

    # 1. Read from local DB
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()

    cur.execute(f"SELECT date, time_order, dispatched_load, wind_power, photovoltaic_power, bidding_space FROM bidding_space_forecast WHERE date IN ('" + "','".join(iso_dates) + "') ORDER BY date, time_order")
    fc = {}
    for d, to, dl, wi, pv, bs in cur.fetchall():
        fc.setdefault(d, []).append((int(to), float(dl or 0), float(wi or 0), float(pv or 0), float(bs or 0)))

    cur.execute(f"SELECT date, time_order, dispatched_load, wind_power, photovoltaic_power, bidding_space FROM bidding_space_actual WHERE date IN ('" + "','".join(iso_dates) + "') ORDER BY date, time_order")
    ac = {}
    for d, to, dl, wi, pv, bs in cur.fetchall():
        ac.setdefault(d, []).append((int(to), float(dl or 0), float(wi or 0), float(pv or 0), float(bs or 0)))

    cur.execute(f"SELECT date, time_order, price FROM dayahead_price WHERE date IN ('" + "','".join(iso_dates) + "') ORDER BY date, time_order")
    da_p = {}
    for d, to, price in cur.fetchall():
        da_p.setdefault(d, [0.0]*96)[max(0, int(to)-2)] = float(price or 0)

    cur.execute(f"SELECT date, time_order, price FROM realtime_price WHERE date IN ('" + "','".join(iso_dates) + "') ORDER BY date, time_order")
    rt_p = {}
    for d, to, price in cur.fetchall():
        rt_p.setdefault(d, [0.0]*96)[max(0, int(to)-2)] = float(price or 0)

    db.close()

    # 2. Power from 天机
    conn = pymysql.connect(host='rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com', port=3306,
        user='pengyiqiang', password='pengyiqiang123', database='tianrun_new',
        charset='utf8mb4', connect_timeout=10, read_timeout=60)
    cur2 = conn.cursor()
    da_power = {}; rt_power = {}
    for d in iso_dates:
        cur2.execute("SELECT time_point, power FROM shandong_px_reliable_clearing_unit_data WHERE date=%s AND member_id='b9e64e64a713458eba94c9af05c0a757' AND unit_name NOT LIKE '%%发电%%' AND unit_name NOT LIKE '%%用电%%' ORDER BY time_point", (d,))
        rows = cur2.fetchall()
        da_power[d] = [float(r[1] or 0) for r in rows] if rows else [0]*96
        cur2.execute("SELECT time_point, power FROM shandong_px_realtime_clearing_results_query WHERE date=%s AND member_id='b9e64e64a713458eba94c9af05c0a757' ORDER BY time_point", (d,))
        rows = cur2.fetchall()
        rt_power[d] = [float(r[1] or 0) for r in rows] if rows else [0]*96
    cur2.close(); conn.close()

    # 3. Weather
    LAT, LON = 37.45, 116.36
    def get_weather(ds):
        url = f'https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&daily=weather_code,temperature_2m_max,temperature_2m_min,shortwave_radiation_sum,wind_speed_10m_max,wind_direction_10m_dominant,precipitation_sum,relative_humidity_2m_mean,sunshine_duration,cloud_cover_mean&timezone=Asia/Shanghai&start_date={ds}&end_date={ds}'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            daily = data['daily']
            return {'code': daily['weather_code'][0], 'temp_max': daily['temperature_2m_max'][0], 'temp_min': daily['temperature_2m_min'][0], 'radiation': daily['shortwave_radiation_sum'][0] / 100.0 if daily['shortwave_radiation_sum'][0] else 0, 'wind_max': daily['wind_speed_10m_max'][0], 'wind_dir': daily['wind_direction_10m_dominant'][0], 'precip': daily['precipitation_sum'][0], 'humidity': daily['relative_humidity_2m_mean'][0], 'sunshine': daily['sunshine_duration'][0], 'cloud': daily['cloud_cover_mean'][0], 'desc': '', 'wind_dir_str': ''}
        except Exception as e:
            print(f'  Weather failed for {ds}: {e}')
            return {'code': 0, 'temp_max': 0, 'temp_min': 0, 'radiation': 0, 'wind_max': 0, 'wind_dir': 0, 'precip': 0, 'humidity': 0, 'sunshine': 0, 'cloud': 0, 'desc': '', 'wind_dir_str': ''}

    print('  Fetching weather...')
    weather = {}
    for d in iso_dates:
        weather[d] = get_weather(d)
        time.sleep(0.3)

    # 4. Build data
    data = {}
    for d in iso_dates:
        fc_d = fc.get(d, [(i+1,0,0,0,0) for i in range(96)])
        ac_d = ac.get(d, [(i+1,0,0,0,0) for i in range(96)])
        data[d] = {
            'pred_load': [x[1] for x in sorted(fc_d, key=lambda x: x[0])],
            'pred_wind': [x[2] for x in sorted(fc_d, key=lambda x: x[0])],
            'pred_solar': [x[3] for x in sorted(fc_d, key=lambda x: x[0])],
            'pred_bs': [x[4] for x in sorted(fc_d, key=lambda x: x[0])],
            'act_load': [x[1] for x in sorted(ac_d, key=lambda x: x[0])],
            'act_wind': [x[2] for x in sorted(ac_d, key=lambda x: x[0])],
            'act_solar': [x[3] for x in sorted(ac_d, key=lambda x: x[0])],
            'act_bs': [x[4] for x in sorted(ac_d, key=lambda x: x[0])],
            'da_price': da_p.get(d, [0]*96),
            'rt_price': rt_p.get(d, [0]*96),
            'da_power': da_power.get(d, [0]*96),
            'rt_power': rt_power.get(d, [0]*96),
        }

    # 5. Save tmp JSON
    tmp_json = os.path.join(PROJECT, '_tmp_html_data.json')
    with open(tmp_json, 'w', encoding='utf-8') as f:
        json.dump({'data': data, 'weather': weather, 'timeLabels': TIMES}, f, ensure_ascii=False, indent=2)

    # 6. Generate HTML
    import subprocess
    out_html = os.path.join(OUT_DIR, f'竞价空间_电价_天气综合分析_{RANGE_LABEL}.html')
    title = f'2026年{RANGE_LABEL[:2]}月{RANGE_LABEL[2:4]}日-{RANGE_LABEL[5:7]}日'
    gen_script = os.path.join(PROJECT, '06 DataMining', 'generate_analysis_html.py')
    subprocess.run([sys.executable, gen_script, out_html, title], cwd=os.path.dirname(gen_script))
    print(f'  [OK] 竞价空间_电价_天气综合分析_{RANGE_LABEL}.html')


def main():
    print(f'=== Generating weekly report {RANGE_LABEL} ===')
    rows, cols = load_db_rows()

    missing = [d for d in DATES if rows[d] is None]
    if missing:
        print(f'  ERROR: missing DB data for {missing}, abort.')
        return

    write_weekly_xlsx(rows)
    r9 = compute_row9(rows)
    fm = load_fm_data()
    generate_txt(r9, fm)
    generate_analysis_html()

    print(f'\n--- Row9 computed values ---')
    print(f'  上周收益 P9/10000 = {r9["P9"]/10000:.2f}万')
    print(f'  过网费 |S9|/10000 = {abs(r9["S9"])/10000:.2f}万')
    print(f'  实时市场 Q9/10000 = {r9["Q9"]/10000:.2f}万')
    print(f'  充电量 |C9| = {abs(r9["C9"]):.0f}MWh')
    print(f'  放电量 L9 = {r9["L9"]:.0f}MWh')
    print(f'  价差 O9 = {r9["O9"]:.0f}元/MWh')
    print(f'\n--- 调频数据 ---')
    print(f'  调频补偿 R9 = {fm["compensation"]:.2f}元 = {fm["compensation"]/10000:.3f}万元')
    print(f'  中标时段 = {fm["n_periods"]}个, 均价 = {fm["avg_price"]:.4f}')
    print(f'  综合性能 Kp = {fm["kp_avg"]:.4f} (共{fm["kp_count"]}条记录)')
    print('\nDone.')


if __name__ == '__main__':
    main()
