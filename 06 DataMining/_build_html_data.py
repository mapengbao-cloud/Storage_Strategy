"""Build _tmp_html_data.json for 0629-0708 from local DB + 天机 + Open-Meteo weather."""
import json, os, sqlite3, pymysql, urllib.request, time
from datetime import datetime

ROOT = r'E:\DataWork\Storage_Strategy'
DB_PATH = os.path.join(ROOT, 'data', 'cache', 'local.db')
DATES = ['2026-06-29','2026-06-30','2026-07-01','2026-07-02','2026-07-03','2026-07-04','2026-07-05','2026-07-06','2026-07-07','2026-07-08']
TIMES = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0,15,30,45)]

db = sqlite3.connect(DB_PATH)
cur = db.cursor()

# 1. bidding_space_forecast
cur.execute("SELECT date, time_order, dispatched_load, wind_power, photovoltaic_power, bidding_space FROM bidding_space_forecast WHERE date IN ('" + "','".join(DATES) + "') ORDER BY date, time_order")
fc = {}
for d, to, dl, wi, pv, bs in cur.fetchall():
    fc.setdefault(d, []).append((int(to), float(dl or 0), float(wi or 0), float(pv or 0), float(bs or 0)))

# 2. bidding_space_actual
cur.execute("SELECT date, time_order, dispatched_load, wind_power, photovoltaic_power, bidding_space FROM bidding_space_actual WHERE date IN ('" + "','".join(DATES) + "') ORDER BY date, time_order")
ac = {}
for d, to, dl, wi, pv, bs in cur.fetchall():
    ac.setdefault(d, []).append((int(to), float(dl or 0), float(wi or 0), float(pv or 0), float(bs or 0)))

# 3. dayahead_price
cur.execute("SELECT date, time_order, price FROM dayahead_price WHERE date IN ('" + "','".join(DATES) + "') ORDER BY date, time_order")
da_p = {}
for d, to, price in cur.fetchall():
    da_p.setdefault(d, [0.0]*96)[max(0, int(to)-2)] = float(price or 0)

# 4. realtime_price
cur.execute("SELECT date, time_order, price FROM realtime_price WHERE date IN ('" + "','".join(DATES) + "') ORDER BY date, time_order")
rt_p = {}
for d, to, price in cur.fetchall():
    rt_p.setdefault(d, [0.0]*96)[max(0, int(to)-2)] = float(price or 0)

db.close()

# 5. 润津 power from 天机 (日前 + 实时)
conn = pymysql.connect(host='rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com', port=3306,
    user='pengyiqiang', password='pengyiqiang123', database='tianrun_new',
    charset='utf8mb4', connect_timeout=10, read_timeout=60)
cur2 = conn.cursor()

da_power = {}; rt_power = {}
for d in DATES:
    cur2.execute("SELECT time_point, power FROM shandong_px_reliable_clearing_unit_data WHERE date=%s AND member_id='b9e64e64a713458eba94c9af05c0a757' AND unit_name NOT LIKE '%%发电%%' AND unit_name NOT LIKE '%%用电%%' ORDER BY time_point", (d,))
    rows = cur2.fetchall()
    da_power[d] = [float(r[1] or 0) for r in rows] if rows else [0]*96

    cur2.execute("SELECT time_point, power FROM shandong_px_realtime_clearing_results_query WHERE date=%s AND member_id='b9e64e64a713458eba94c9af05c0a757' ORDER BY time_point", (d,))
    rows = cur2.fetchall()
    rt_power[d] = [float(r[1] or 0) for r in rows] if rows else [0]*96

cur2.close(); conn.close()

# 6. Weather from Open-Meteo
# Use Dezhou coordinates
LAT, LON = 37.45, 116.36
def get_weather(date_str):
    url = f'https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&daily=weather_code,temperature_2m_max,temperature_2m_min,shortwave_radiation_sum,wind_speed_10m_max,wind_direction_10m_dominant,precipitation_sum,relative_humidity_2m_mean,sunshine_duration,cloud_cover_mean&timezone=Asia/Shanghai&start_date={date_str}&end_date={date_str}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        daily = data['daily']
        return {
            'code': daily['weather_code'][0],
            'temp_max': daily['temperature_2m_max'][0],
            'temp_min': daily['temperature_2m_min'][0],
            'radiation': daily['shortwave_radiation_sum'][0] / 100.0 if daily['shortwave_radiation_sum'][0] else 0,
            'wind_max': daily['wind_speed_10m_max'][0],
            'wind_dir': daily['wind_direction_10m_dominant'][0],
            'precip': daily['precipitation_sum'][0],
            'humidity': daily['relative_humidity_2m_mean'][0],
            'sunshine': daily['sunshine_duration'][0],
            'cloud': daily['cloud_cover_mean'][0],
            'desc': '',
            'wind_dir_str': '',
        }
    except Exception as e:
        print(f'  Weather fetch failed for {date_str}: {e}')
        return {'code': 0, 'temp_max': 0, 'temp_min': 0, 'radiation': 0, 'wind_max': 0, 'wind_dir': 0, 'precip': 0, 'humidity': 0, 'sunshine': 0, 'cloud': 0, 'desc': '', 'wind_dir_str': ''}

print('Fetching weather...')
weather = {}
for d in DATES:
    weather[d] = get_weather(d)
    print(f'  {d}: {weather[d]["temp_max"]}°C/{weather[d]["temp_min"]}°C')
    time.sleep(0.3)

# 7. Build output JSON
data = {}
for d in DATES:
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

out = {'data': data, 'weather': weather, 'timeLabels': TIMES}
OUT = os.path.join(ROOT, '_tmp_html_data.json')
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f'Saved: {OUT} ({os.path.getsize(OUT):,} bytes)')
print(f'Dates: {sorted(data.keys())}')