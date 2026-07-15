"""Serve prescheduling page with live DB-backed date picker API."""
import json, math, os, sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from collections import defaultdict
import pymysql

PORT = 8765
DB_CONFIG = {
    'host': 'rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com',
    'port': 3306, 'user': 'pengyiqiang', 'password': 'pengyiqiang123',
    'database': 'tianrun_new', 'charset': 'utf8mb4'
}


def classify(vals, name=""):
    arr = [v for v in vals if v is not None]
    if len(arr) < 80:
        return "数据不足", 0
    mean_v = sum(arr) / len(arr)
    if mean_v == 0:
        return "零出力", 0
    std_v = math.sqrt(sum((x - mean_v)**2 for x in arr) / len(arr))
    cv = (std_v / abs(mean_v)) * 100 if mean_v != 0 else 0
    peak, trough = max(arr), min(arr)

    night1 = arr[0:28]; morning = arr[28:48]; midday = arr[40:56]
    afternoon = arr[48:68]; evening = arr[68:88]; night2 = arr[88:96]

    def avg(seg):
        return sum(seg) / len(seg) if seg else 0

    avg_night1, avg_morning, avg_midday = avg(night1), avg(morning), avg(midday)
    avg_afternoon, avg_evening, avg_night2 = avg(afternoon), avg(evening), avg(night2)

    has_negative, has_positive = min(arr) < 0, max(arr) > 0

    if has_negative and has_positive:
        if '机' in name or '#' in name:
            return "一充一放型(抽蓄)", cv
        return "一充一放型", cv
    if has_negative and not has_positive:
        return "纯充电型", cv

    # 日内启机/停机检测（在 CV 检查之前，优先识别启停类）
    quarter = 24  # 6 hours
    first_q_avg = sum(arr[0:quarter]) / quarter
    last_q_avg = sum(arr[96-quarter:96]) / quarter

    # 日内启机：前1/4接近0，后3/4有显著出力
    if first_q_avg < peak * 0.03 and peak > 0:
        rest_avg = sum(arr[quarter:96]) / (96 - quarter)
        if rest_avg > peak * 0.03:
            return "日内启机", cv

    # 日内停机：后1/4接近0，前3/4有显著出力
    if last_q_avg < peak * 0.03 and peak > 0:
        rest_avg = sum(arr[0:96-quarter]) / (96 - quarter)
        if rest_avg > peak * 0.03:
            return "日内停机", cv

    if cv < 5:
        return "全天直线型" if peak == trough else "基本平稳", cv

    # 其余所有非零出力火电 → 午间调峰机组
    return "午间调峰机组", cv


def query_date(date_str):
    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        "SELECT generator_name, time_order, declaration_power "
        "FROM shandong_px_provincial_prescheduling_results "
        "WHERE date=%s ORDER BY generator_name, CAST(time_order AS UNSIGNED)",
        (date_str,))
    data = defaultdict(list)
    for name, tp, pwr in cur.fetchall():
        data[name].append(float(pwr) if pwr else 0.0)
    cur.close()
    conn.close()

    thermal = {n: v for n, v in data.items() if '机' in n or '#' in n}
    storage = {n: v for n, v in data.items() if '储能' in n}

    def classify_all(items):
        result = []
        for name, vals in items.items():
            pattern, cv = classify(vals, name)
            peak = max(vals)
            mean_v = sum(vals) / len(vals)
            charge_powers = [abs(v) for v in vals if v < 0]
            discharge_powers = [v for v in vals if v > 0]
            charge_avg = sum(charge_powers) / len(charge_powers) if charge_powers else 0
            discharge_avg = sum(discharge_powers) / len(discharge_powers) if discharge_powers else 0
            charge_energy = sum(abs(v) * 0.25 for v in vals if v < 0)
            discharge_energy = sum(v * 0.25 for v in vals if v > 0)
            efficiency = (discharge_energy / charge_energy * 100) if charge_energy > 0 else 0
            result.append({
                "name": name, "vals": vals, "pattern": pattern, "cv": cv,
                "peak": peak, "mean": mean_v, "trough": min(vals),
                "charge_avg": charge_avg, "discharge_avg": discharge_avg,
                "charge_energy": charge_energy, "discharge_energy": discharge_energy,
                "efficiency": efficiency
            })
        result.sort(key=lambda x: x["peak"], reverse=True)
        return result

    thermal_list = classify_all(thermal)
    storage_list = classify_all(storage)
    storage_list.sort(key=lambda x: x["discharge_energy"], reverse=True)

    def pattern_stats(items):
        stats = defaultdict(list)
        for it in items:
            stats[it["pattern"]].append(it)
        return dict(sorted(stats.items(), key=lambda x: len(x[1]), reverse=True))

    return {
        "date": date_str,
        "thermal": thermal_list,
        "storage": storage_list,
        "t_pat": {k: len(v) for k, v in pattern_stats(thermal_list).items()},
        "s_pat": {k: len(v) for k, v in pattern_stats(storage_list).items()},
        "total_charge": sum(s["charge_energy"] for s in storage_list),
        "total_discharge": sum(s["discharge_energy"] for s in storage_list),
    }


def get_dates():
    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT date, COUNT(DISTINCT generator_name) FROM "
                "shandong_px_provincial_prescheduling_results "
                "WHERE date >= '2026-01-01' GROUP BY date ORDER BY date DESC")
    dates = [{"date": str(r[0]), "units": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return dates


HTML_PAGE = None


def get_page():
    global HTML_PAGE
    if HTML_PAGE:
        return HTML_PAGE
    with open(os.path.join(os.path.dirname(__file__), 'prescheduling_page.html'), 'rb') as f:
        HTML_PAGE = f.read()
    return HTML_PAGE


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/api/dates':
            self.send_json(get_dates())
        elif path == '/api/data':
            date_str = params.get('date', ['2026-06-05'])[0]
            self.send_json(query_date(date_str))
        elif path == '/' or path == '/index.html':
            body = get_page()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def send_json(self, data):
        body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), args[0] % args[1:]))


if __name__ == '__main__':
    print(f"Server starting at http://localhost:{PORT}")
    print("Press Ctrl+C to stop")
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()