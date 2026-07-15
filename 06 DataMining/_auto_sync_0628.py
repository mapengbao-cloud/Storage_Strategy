"""Auto-sync 0628 dayahead load info + generate similar day analysis HTML.

Scheduled to run at 10:15 when 天机库 updates dayahead forecast data.
"""
import os, sys, pymysql, sqlite3

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

DB_CONFIG = {
    'host': os.getenv('DB_TIANJI_HOST', 'rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com'),
    'port': int(os.getenv('DB_TIANJI_PORT', '3306')),
    'user': os.getenv('DB_TIANJI_USER', 'pengyiqiang'),
    'password': os.getenv('DB_TIANJI_PASSWORD', 'pengyiqiang123'),
    'database': os.getenv('DB_TIANJI_DATABASE', 'tianrun_new'),
}
DB_PATH = os.path.join(ROOT, 'data', 'cache', 'local.db')
TARGET_DATE = '2026-06-28'

# 1. Check 天机库 for 0628 data
print(f'[{__import__("datetime").datetime.now().strftime("%H:%M:%S")}] Checking 天机库 for {TARGET_DATE}...')
conn = pymysql.connect(**DB_CONFIG, connect_timeout=10)
cur = conn.cursor()
cur.execute(f"SELECT COUNT(*) FROM shandong_px_spot_dayahead_load_info WHERE date='{TARGET_DATE}'")
count = cur.fetchone()[0]

if count == 0:
    print(f'[{__import__("datetime").datetime.now().strftime("%H:%M:%S")}] {TARGET_DATE} data not yet available, exiting.')
    cur.close()
    conn.close()
    sys.exit(0)

# 2. Sync bidding_space_forecast
print(f'[{__import__("datetime").datetime.now().strftime("%H:%M:%S")}] Syncing {TARGET_DATE} {count} rows...')
cur.execute(f"""SELECT date, time_order, dispatched_load_forecast, tie_line_load_forecast,
    wind_power_forecast, photovoltaic_power_forecast
    FROM shandong_px_spot_dayahead_load_info WHERE date='{TARGET_DATE}' ORDER BY time_order""")
rows = cur.fetchall()
cur.close()
conn.close()

db = sqlite3.connect(DB_PATH)
cur = db.cursor()
cur.execute(f"DELETE FROM bidding_space_forecast WHERE date='{TARGET_DATE}'")
for r in rows:
    d, to, dl, tl, wp, pv = r
    bs = float(dl or 0) - float(tl or 0) - float(wp or 0) - float(pv or 0)
    cur.execute('INSERT INTO bidding_space_forecast VALUES (?,?,?,?,?,?,?,?)',
                 (str(d), int(to), float(dl or 0), float(tl or 0), float(wp or 0), float(pv or 0), 0.0, bs))
db.commit()
db.close()
print(f'Synced {len(rows)} rows to bidding_space_forecast')

# 3. Sync dayahead_price & realtime_price from 天机库
print(f'[{__import__("datetime").datetime.now().strftime("%H:%M:%S")}] Syncing price data...')
import subprocess
subprocess.run([sys.executable, os.path.join(ROOT, '06 DataMining', 'local_db.py'), 'sync',
                '--start', TARGET_DATE, '--end', TARGET_DATE, '--tables', 'price'],
               cwd=ROOT, check=True)

# 4. Run similar_day_analysis
print(f'[{__import__("datetime").datetime.now().strftime("%H:%M:%S")}] Computing features...')
import subprocess
subprocess.run([sys.executable, os.path.join(ROOT, '06 DataMining', 'similar_day_analysis.py'), 'compute'],
               cwd=ROOT, check=True)

print(f'[{__import__("datetime").datetime.now().strftime("%H:%M:%S")}] Generating HTML for {TARGET_DATE}...')
subprocess.run([sys.executable, os.path.join(ROOT, '06 DataMining', 'similar_day_analysis.py'), TARGET_DATE],
               cwd=ROOT, check=True)

print(f'[{__import__("datetime").datetime.now().strftime("%H:%M:%S")}] Done!')