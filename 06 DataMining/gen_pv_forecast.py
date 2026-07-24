"""山东全省光伏出力下周预测 — 基于历史光伏 vs 全省辐照度的小时级线性回归。

方法：
  1. 从天机库取最近 ~45 天全省光伏日前预测出力（shandong_px_spot_dayahead_load_info，
     photovoltaic_power_forecast，96 点/天）。选用日前预测值而非实际出力，
     因为实际出力可能被限电，预测值更接近真实光伏资源能力。
  2. 从 Open-Meteo 取同期 + 未来 7 天山东省 8 个代表城市（济南/青岛/烟台/潍坊/
     临沂/德州/济宁/菏泽）的短波辐照度 shortwave_radiation（W/m²，逐时），8 城平均
     作为全省辐照度。
  3. 把光伏 96 点折叠为 24 逐时均值（MW），与辐照度逐时对齐，按小时 h∈[0,23]
     分别拟合 PV_h = a_h + b_h · RAD_h（最小二乘）。
  4. 用预报辐照度逐时代入各小时模型，预测未来 7 天（0725-0731）光伏逐时出力，
     裁剪 ≥0 且不超过该小时历史最大值（物理上限），再线性插值到 96 点生成每日曲线。
  5. 输出 HTML：预测光伏每日曲线 + 预测辐照度每日曲线 + 模型验证散点 + 逐日汇总表。

用法：
  cd "06 DataMining"
  python gen_pv_forecast.py
"""
import os
import sys
import json
import math
import urllib.request
import urllib.parse
from collections import defaultdict

# ── 加载 .env（项目无 python-dotenv，手动解析） ──────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = {}
with open(os.path.join(_ROOT, ".env"), encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
for k, v in env.items():
    os.environ.setdefault(k, v)
sys.path.insert(0, _ROOT)
from src.data.db import query  # noqa: E402

# ── 配置 ─────────────────────────────────────────────────────────────
# 山东 8 个代表城市（lat, lon, 名）—— 省内地理均匀分布，含润津所在地德州
CITIES = [
    (36.65, 117.00, "济南"),
    (36.07, 120.38, "青岛"),
    (37.53, 121.45, "烟台"),
    (36.70, 119.10, "潍坊"),
    (35.10, 118.35, "临沂"),
    (37.45, 116.30, "德州"),
    (35.40, 116.60, "济宁"),
    (35.25, 115.45, "菏泽"),
]
LATS = ",".join(f"{la}" for la, lo, _ in CITIES)
LONS = ",".join(f"{lo}" for la, lo, _ in CITIES)

HIST_DAYS = 45          # 历史训练窗口
FORECAST_DAYS = 7      # 预测未来天数
TIMEZONE = "Asia/Shanghai"
TODAY = "2026-07-25"    # 当天（脚本运行日，用于划分历史/预报）

OUTPUT_DIR = os.path.join(_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_HTML = os.path.join(
    OUTPUT_DIR,
    f"光伏出力预测_2026-07-25至2026-07-31.html",
)

# ── ECharts 配色（每条 series 线/点同色，遵守全局配色规则） ──────────
SERIES_COLORS = [
    "#ee6666", "#fac858", "#91cc75", "#73c0de", "#3ba272",
    "#fc8452", "#9a60b4", "#5470c6", "#ea7ccc", "#c9db5b",
]
IRRAD_COLORS = [
    "#f5994e", "#f5c842", "#7eb6c4", "#5ab463", "#4a7fb8",
    "#b07cc4", "#d4906a", "#8db96f",
]


# ── 数据获取 ─────────────────────────────────────────────────────────
def fetch_pv_history(start, end):
    """从天机库取全省光伏日前预测出力 96 点，返回 {date: [96 float MW]}。

    注意：用日前预测光伏出力（photovoltaic_power_forecast）而非实际出力
    （actual_photovoltaic_power），因为实际出力可能被限电压低，预测值更接近
    真实光伏资源能力，适合训练辐照度→光伏的回归模型。
    """
    rows = query(f"""
        SELECT date, time_order, photovoltaic_power_forecast as pv
        FROM shandong_px_spot_dayahead_load_info
        WHERE date BETWEEN %s AND %s
        ORDER BY date, time_order
    """, (start, end))
    by_date = defaultdict(dict)
    for r in rows:
        by_date[str(r["date"])][int(r["time_order"])] = float(r["pv"] or 0)
    # 转成 96 点列表（不足补 0）
    out = {}
    for d, pts in by_date.items():
        arr = [pts.get(i, 0.0) for i in range(1, 97)]
        if len([x for x in arr if x != 0]) >= 24:  # 过滤空天
            out[d] = arr
    return out


def fetch_openmeteo(start, end, base_url, extra_params=None):
    """调 Open-Meteo（archive 或 forecast），返回 list[location_dict]。"""
    params = {
        "latitude": LATS,
        "longitude": LONS,
        "hourly": "shortwave_radiation,cloud_cover,temperature_2m",
        "timezone": TIMEZONE,
    }
    if start and end:
        params["start_date"] = start
        params["end_date"] = end
    if "forecast_days" in (extra_params or {}):
        params["forecast_days"] = extra_params["forecast_days"]
    url = base_url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "StorageStrategy/1.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode())
    return data if isinstance(data, list) else [data]


def province_hourly_irradiance(locs):
    """把多城市响应合并成全省平均逐时辐照度。返回 {date: [24 float W/m²]}。"""
    by_date = defaultdict(lambda: [0.0] * 24)
    cnt = defaultdict(int)
    for loc in locs:
        times = loc["hourly"]["time"]
        rads = loc["hourly"]["shortwave_radiation"]
        for t, r in zip(times, rads):
            if r is None:
                continue
            d = t[:10]
            h = int(t[11:13])
            by_date[d][h] += r
            cnt[d] += 1
    for d in by_date:
        for h in range(24):
            by_date[d][h] /= 8
    return dict(by_date)


def province_hourly_cloud(locs):
    """全省平均云量（%），返回 {date: 24-list or avg}。"""
    by_date = defaultdict(lambda: [0.0] * 24)
    cnt = defaultdict(int)
    for loc in locs:
        times = loc["hourly"]["time"]
        cc = loc["hourly"]["cloud_cover"]
        for t, c in zip(times, cc):
            if c is None:
                continue
            d = t[:10]
            h = int(t[11:13])
            by_date[d][h] += c
            cnt[d] += 1
    for d in by_date:
        for h in range(24):
            by_date[d][h] /= 8
    return dict(by_date)


# ── 96点 ↔ 24小时 ────────────────────────────────────────────────────
def pv96_to_hourly_mean(pv96):
    """96 点（15min）→ 24 逐时均值（MW）。time_order 1-96，hour h 含点 h*4+1..h*4+4。"""
    out = []
    for h in range(24):
        chunk = [pv96[h * 4 + i] for i in range(4)]  # index 0-95
        out.append(sum(chunk) / 4.0)
    return out


def hourly_to_96(hourly):
    """24 逐时 → 96 点，分段线性插值（点 i 对应 (i)*15min，i=0..95）。
    hour h 的值作用于 h:00，故 point i 落在 frac=(i)/4 小时。"""
    out = []
    for i in range(96):
        frac = i / 4.0
        h0 = int(frac) if int(frac) < 23 else 23
        frac_h = frac - int(frac) if int(frac) < 23 else 0
        h1 = min(h0 + 1, 23)
        v = hourly[h0] * (1 - frac_h) + hourly[h1] * frac_h
        out.append(v)
    # 末段（>=23.75）锁定为 hour[23]
    for i in range(95, 96):
        out[i] = hourly[23]
    return out


# ── 逐时线性回归 ────────────────────────────────────────────────────
def fit_hourly_models(pv_by_date, rad_by_date):
    """对每个小时 h 拟合 PV_h = a_h + b_h·RAD_h，返回 models[24] = (a, b, r, n)。"""
    models = []
    # 同时记录该小时历史 PV 最大值，作为物理上限
    max_pv = [0.0] * 24
    for h in range(24):
        xs, ys = [], []
        for d in pv_by_date:
            if d not in rad_by_date:
                continue
            r = rad_by_date[d][h]
            p = pv96_to_hourly_mean(pv_by_date[d])[h]
            xs.append(r)
            ys.append(p)
            if p > max_pv[h]:
                max_pv[h] = p
        n = len(xs)
        if n < 3:
            models.append((0.0, 0.0, 0.0, n))
            continue
        mx = sum(xs) / n
        my = sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        syy = sum((y - my) ** 2 for y in ys)
        b = sxy / sxx if sxx > 0 else 0.0
        a = my - b * mx
        r = sxy / math.sqrt(sxx * syy) if (sxx > 0 and syy > 0) else 0.0
        models.append((a, b, r, n))
    return models, max_pv


def predict_pv_hourly(models, max_pv, rad_hourly):
    """用逐时模型预测光伏，裁剪 [0, max_pv_h]。"""
    out = []
    for h in range(24):
        a, b, _, _ = models[h]
        v = a + b * rad_hourly[h]
        v = max(0.0, v)
        if max_pv[h] > 0:
            v = min(v, max_pv[h] * 1.05)  # 允许略超历史最高 5%
        out.append(v)
    return out


def daily_energy_mwh(pv96):
    """96 点 MW（15min 间隔）→ 日发电量 MWh = Σ(MW · 0.25h)。"""
    return sum(pv96) * 0.25


# ── 时间标签 ──────────────────────────────────────────────────────────
def time_labels_96():
    """生成 96 个 'HH:MM' 标签（00:00 起，每 15min）。"""
    out = []
    for i in range(96):
        total = i * 15
        out.append(f"{total // 60:02d}:{total % 60:02d}")
    return out


# ── 主流程 ───────────────────────────────────────────────────────────
def main():
    from datetime import date, timedelta

    today = date.fromisoformat(TODAY)
    yesterday = today - timedelta(days=1)
    hist_start = (today - timedelta(days=HIST_DAYS)).isoformat()
    hist_end = today.isoformat()
    fc_start = today.isoformat()
    fc_end = (today + timedelta(days=FORECAST_DAYS - 1)).isoformat()

    print(f"[1/5] 取历史光伏 {hist_start} ~ {hist_end} ...")
    pv_hist = fetch_pv_history(hist_start, hist_end)
    print(f"      历史光伏天数: {len(pv_hist)}")

    print(f"[2/5] 取历史辐照度（Open-Meteo archive {hist_start} ~ {yesterday}）...")
    locs_hist = fetch_openmeteo(
        hist_start, yesterday.isoformat(),
        "https://archive-api.open-meteo.com/v1/archive",
    )
    rad_hist = province_hourly_irradiance(locs_hist)
    cloud_hist = province_hourly_cloud(locs_hist)
    print(f"      历史辐照度天数: {len(rad_hist)}")

    # 补齐当天（today）辐照度：archive 不可用，用 forecast 回看
    print(f"      补齐当天辐照度（forecast 回看 {today}）...")
    locs_today = fetch_openmeteo(
        None, None,
        "https://api.open-meteo.com/v1/forecast",
        extra_params={"forecast_days": 1},
    )
    rad_today = province_hourly_irradiance(locs_today)
    cloud_today = province_hourly_cloud(locs_today)
    if today.isoformat() in rad_today:
        rad_hist[today.isoformat()] = rad_today[today.isoformat()]
        cloud_hist[today.isoformat()] = cloud_today.get(today.isoformat(), [0] * 24)
        print(f"      当天辐照度已补齐")
    else:
        print(f"      当天无辐照度数据，跳过")

    print(f"[3/5] 拟合逐时回归模型 PV_h = a + b·RAD_h ...")
    models, max_pv = fit_hourly_models(pv_hist, rad_hist)
    for h in [6, 9, 12, 15, 18]:
        a, b, r, n = models[h]
        print(f"      h={h:02d}: a={a:.1f} b={b:.3f} r={r:.3f} n={n} max_pv={max_pv[h]:.0f}")

    print(f"[4/5] 取未来 {FORECAST_DAYS} 天预报辐照度（Open-Meteo forecast） ...")
    locs_fc = fetch_openmeteo(
        None, None,
        "https://api.open-meteo.com/v1/forecast",
        extra_params={"forecast_days": FORECAST_DAYS + 2},
    )
    rad_fc = province_hourly_irradiance(locs_fc)
    cloud_fc = province_hourly_cloud(locs_fc)
    # 只取 fc_start ~ fc_end
    fc_dates = sorted(d for d in rad_fc if fc_start <= d <= fc_end)
    print(f"      预报天数: {len(fc_dates)} -> {fc_dates}")

    print(f"[5/5] 预测光伏 + 生成 HTML ...")
    forecast_days = []
    for d in fc_dates:
        rad_h = rad_fc[d]
        pv_h = predict_pv_hourly(models, max_pv, rad_h)
        pv96 = hourly_to_96(pv_h)
        rad96 = hourly_to_96(rad_h)
        cc = sum(cloud_fc[d]) / 24
        forecast_days.append({
            "date": d,
            "pv96": pv96,
            "rad96": rad96,
            "cloud_avg": cc,
            "rad_max": max(rad_h),
            "rad_sum": sum(rad_h),
            "pv_peak": max(pv96),
            "energy_mwh": daily_energy_mwh(pv96),
        })

    # 模型验证数据（逐日 RAD_sum vs PV_sum）
    val_points = []
    for d in pv_hist:
        if d not in rad_hist:
            continue
        rad_sum = sum(rad_hist[d])
        pv_h = pv96_to_hourly_mean(pv_hist[d])
        pv_sum = sum(pv_h)
        val_points.append({"rad": rad_sum, "pv": pv_sum})

    # 近 7 天日前预测光伏（参考曲线）
    recent_dates = sorted(pv_hist.keys())[-7:]
    recent_pv = [{"date": d, "pv96": pv_hist[d]} for d in recent_dates]
    recent_rad = [
        {"date": d, "rad96": hourly_to_96(rad_hist[d]) if d in rad_hist else [0] * 96}
        for d in recent_dates
    ]

    html = build_html(forecast_days, models, val_points, recent_pv, recent_rad,
                      hist_start, hist_end, fc_start, fc_end)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nSaved: {OUTPUT_HTML}")


# ── HTML 生成 ────────────────────────────────────────────────────────
def build_html(forecast_days, models, val_points, recent_pv, recent_rad,
               hist_start, hist_end, fc_start, fc_end):
    """生成自包含 HTML。"""
    import json as _json

    # 预测光伏 series
    pv_series = []
    for i, fd in enumerate(forecast_days):
        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        pv_series.append({
            "name": fd["date"],
            "type": "line",
            "data": [round(v, 1) for v in fd["pv96"]],
            "smooth": True,
            "symbol": "none",
            "lineStyle": {"color": color, "width": 2},
            "itemStyle": {"color": color},
        })

    # 预测辐照度 series
    rad_series = []
    for i, fd in enumerate(forecast_days):
        color = IRRAD_COLORS[i % len(IRRAD_COLORS)]
        rad_series.append({
            "name": fd["date"],
            "type": "line",
            "data": [round(v, 1) for v in fd["rad96"]],
            "smooth": True,
            "symbol": "none",
            "lineStyle": {"color": color, "width": 2},
            "itemStyle": {"color": color},
        })

    # 模型验证散点 + 回归线（按日 RAD_sum vs PV_sum）
    scatter = [{"value": [p["rad"], p["pv"]]} for p in val_points]
    if val_points:
        xs = [p["rad"] for p in val_points]
        ys = [p["pv"] for p in val_points]
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        syy = sum((y - my) ** 2 for y in ys)
        b = sxy / sxx if sxx > 0 else 0
        a = my - b * mx
        r = sxy / math.sqrt(sxx * syy) if (sxx > 0 and syy > 0) else 0
        x_line = [min(xs), max(xs)]
        y_line = [a + b * x for x in x_line]
        r2 = r * r
    else:
        a = b = r = r2 = 0
        x_line = y_line = [0, 0]

    # 逐小时模型 r 值（柱状图）
    hour_r = [round(models[h][2], 3) for h in range(24)]

    # 近 7 天日前预测光伏参考 series（淡色）
    recent_pv_series = []
    for i, rd in enumerate(recent_pv):
        color = "#bbb"
        recent_pv_series.append({
            "name": rd["date"],
            "type": "line",
            "data": [round(v, 1) for v in rd["pv96"]],
            "smooth": True,
            "symbol": "none",
            "lineStyle": {"color": color, "width": 1, "type": "dashed"},
            "itemStyle": {"color": color},
        })

    # 汇总表行
    total_energy = sum(fd["energy_mwh"] for fd in forecast_days)
    avg_cloud = sum(fd["cloud_avg"] for fd in forecast_days) / len(forecast_days)
    avg_peak = sum(fd["pv_peak"] for fd in forecast_days) / len(forecast_days)

    tlbl = time_labels_96()
    data_blob = _json.dumps({
        "tlbl": tlbl,
        "pv_series": pv_series,
        "rad_series": rad_series,
        "scatter": scatter,
        "x_line": x_line,
        "y_line": y_line,
        "r2": round(r2, 3),
        "r": round(r, 3),
        "a": round(a, 1),
        "b": round(b, 2),
        "hour_r": hour_r,
        "recent_pv_series": recent_pv_series,
    }, ensure_ascii=False)

    table_rows = ""
    for fd in forecast_days:
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
            __import__("datetime").date.fromisoformat(fd["date"]).weekday()
        ]
        table_rows += (
            f"<tr>"
            f"<td>{fd['date']}</td><td>{weekday}</td>"
            f"<td>{fd['rad_max']:.0f}</td>"
            f"<td>{fd['rad_sum']:.0f}</td>"
            f"<td>{fd['cloud_avg']:.0f}</td>"
            f"<td>{fd['pv_peak']:,.0f}</td>"
            f"<td>{fd['energy_mwh']:,.0f}</td>"
            f"</tr>\n"
        )
    table_rows += (
        f"<tr class='sum'>"
        f"<td colspan='4'>合计 / 平均</td>"
        f"<td>{avg_cloud:.0f}</td>"
        f"<td>{avg_peak:,.0f}</td>"
        f"<td>{total_energy:,.0f}</td>"
        f"</tr>"
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>山东全省光伏出力预测 — 2026-07-25 至 2026-07-31</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  body {{ background:#ffffff; color:#333; font-family:"Microsoft YaHei","Segoe UI",sans-serif; margin:0; padding:20px; }}
  h1 {{ color:#222; font-size:20px; margin:0 0 4px; }}
  .sub {{ color:#666; font-size:13px; margin-bottom:16px; }}
  .cards {{ display:flex; gap:12px; margin-bottom:18px; flex-wrap:wrap; }}
  .card {{ background:#fafafa; border:1px solid #ddd; border-radius:6px; padding:10px 16px; min-width:150px; }}
  .card .lab {{ color:#888; font-size:12px; }}
  .card .val {{ color:#2c7be5; font-size:20px; font-weight:600; margin-top:2px; }}
  .chart {{ background:#fff; border:1px solid #ddd; border-radius:6px; padding:8px; margin-bottom:16px; }}
  .chart h2 {{ font-size:14px; color:#222; margin:6px 10px; }}
  .chart-box {{ width:100%; height:380px; }}
  table {{ border-collapse:collapse; width:100%; background:#fff; font-size:13px; }}
  th, td {{ border:1px solid #e0e0e0; padding:6px 10px; text-align:right; }}
  th {{ background:#f5f5f5; color:#333; text-align:center; }}
  td:first-child, th:first-child {{ text-align:left; }}
  td:nth-child(2), th:nth-child(2) {{ text-align:center; }}
  tr.sum td {{ background:#f5f9ff; font-weight:600; }}
  .note {{ color:#888; font-size:12px; margin-top:8px; line-height:1.6; }}
</style>
</head>
<body>
<h1>山东省全省光伏出力预测 · 下周（2026-07-25 ~ 2026-07-31）</h1>
<div class="sub">
  训练区间：{hist_start} ~ {hist_end}（{HIST_DAYS} 天历史）｜
  数据源：天机库 <code>shandong_px_spot_dayahead_load_info</code>（全省光伏日前预测 96 点）+
  Open-Meteo 8 城短波辐照度（济南/青岛/烟台/潍坊/临沂/德州/济宁/菏泽 均值）｜
  模型：逐时线性回归 PV<sub>h</sub> = a<sub>h</sub> + b<sub>h</sub>·RAD<sub>h</sub>｜
  生成时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}
</div>

<div class="cards">
  <div class="card"><div class="lab">预测周期</div><div class="val">{FORECAST_DAYS} 天</div></div>
  <div class="card"><div class="lab">日总量相关 r</div><div class="val">{r:.3f}</div></div>
  <div class="card"><div class="lab">决定系数 R²</div><div class="val">{r2:.3f}</div></div>
  <div class="card"><div class="lab">周合计发电量</div><div class="val">{total_energy:,.0f} MWh</div></div>
  <div class="card"><div class="lab">平均云量</div><div class="val">{avg_cloud:.0f}%</div></div>
</div>

<div class="chart">
  <h2>① 下周全省光伏出力预测曲线（96 点，MW）</h2>
  <div id="c_pv" class="chart-box"></div>
  <div class="note">每日 00:00–24:00 出力曲线。灰色虚线为近 7 天日前预测光伏（参考量级）。</div>
</div>

<div class="chart">
  <h2>② 下周全省辐照度预测曲线（96 点，W/m²）</h2>
  <div id="c_rad" class="chart-box"></div>
  <div class="note">Open-Meteo 预报短波辐照度，8 城均值，作为光伏出力的驱动量。</div>
</div>

<div class="chart">
  <h2>③ 模型验证：历史逐日辐照度总量 vs 光伏总量</h2>
  <div id="c_val" class="chart-box"></div>
  <div class="note">每个点为一天：x=当日全省辐照度逐时累加（W/m²·h），y=当日光伏逐时均值累加（MW）。
  回归线 PV = {a:.0f} + {b:.2f}·RAD，相关 r={r:.3f}，R²={r2:.3f}。</div>
</div>

<div class="chart">
  <h2>④ 逐小时模型相关系数 r（光伏 vs 辐照度）</h2>
  <div id="c_hour_r" class="chart-box" style="height:260px;"></div>
  <div class="note">白天（06–19 时）拟合质量高，夜间光伏≈0 自动归零。</div>
</div>

<div class="chart">
  <h2>⑤ 下周逐日汇总</h2>
  <table>
    <thead><tr>
      <th>日期</th><th>星期</th><th>辐照峰值(W/m²)</th><th>辐照总量(W/m²·h)</th>
      <th>云量(%)</th><th>光伏峰值(MW)</th><th>日发电量(MWh)</th>
    </tr></thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>
</div>

<div class="note">
  <b>方法说明：</b>将全省光伏 96 点折为 24 逐时均值，与 8 城平均辐照度逐时对齐，
  对每个小时 h∈[0,23] 分别最小二乘拟合 PV<sub>h</sub> = a<sub>h</sub> + b<sub>h</sub>·RAD<sub>h</sub>。
  预报日逐时代入该小时模型，输出裁剪到 [0, 1.05×历史峰值] 后线性插值回 96 点。
  日发电量 = Σ(96 点 MW · 0.25h)。<br>
  <b>局限：</b>线性模型无法捕捉云团突变的非线性骤降；预报辐照度本身有不确定性，
  实际出力受限电/检修影响可能偏低；历史窗口仅 {HIST_DAYS} 天，样本有限。
</div>

<script>
var D = {data_blob};
var tlbl = D.tlbl;

var c_pv = echarts.init(document.getElementById('c_pv'));
c_pv.setOption({{
  color: [],
  tooltip: {{ trigger:'axis', axisPointer:{{type:'line'}} }},
  legend: {{ top:0, textStyle:{{fontSize:11}} }},
  grid: {{ left:60, right:20, top:40, bottom:40 }},
  xAxis: {{ type:'category', data:tlbl, axisLabel:{{ interval:11, color:'#666' }},
            axisLine:{{lineStyle:{{color:'#ddd'}}}} }},
  yAxis: {{ type:'value', name:'MW', nameTextStyle:{{color:'#666'}}, axisLine:{{show:false}},
            splitLine:{{lineStyle:{{color:'#eee'}}}}, axisLabel:{{color:'#666'}} }},
  series: D.pv_series.concat(D.recent_pv_series)
}});

var c_rad = echarts.init(document.getElementById('c_rad'));
c_rad.setOption({{
  tooltip: {{ trigger:'axis' }},
  legend: {{ top:0, textStyle:{{fontSize:11}} }},
  grid: {{ left:60, right:20, top:40, bottom:40 }},
  xAxis: {{ type:'category', data:tlbl, axisLabel:{{ interval:11, color:'#666' }},
            axisLine:{{lineStyle:{{color:'#ddd'}}}} }},
  yAxis: {{ type:'value', name:'W/m²', nameTextStyle:{{color:'#666'}}, axisLine:{{show:false}},
            splitLine:{{lineStyle:{{color:'#eee'}}}}, axisLabel:{{color:'#666'}} }},
  series: D.rad_series
}});

var c_val = echarts.init(document.getElementById('c_val'));
c_val.setOption({{
  tooltip: {{ trigger:'item', formatter:function(p){{ return '辐照度:'+p.value[0].toFixed(0)+'<br>光伏:'+p.value[1].toFixed(0); }} }},
  grid: {{ left:70, right:20, top:30, bottom:50 }},
  xAxis: {{ type:'value', name:'辐照度总量 (W/m²·h)', nameLocation:'middle', nameGap:30,
            nameTextStyle:{{color:'#666'}}, axisLine:{{lineStyle:{{color:'#ddd'}}}},
            splitLine:{{lineStyle:{{color:'#eee'}}}}, axisLabel:{{color:'#666'}} }},
  yAxis: {{ type:'value', name:'光伏总量 (MW)', nameTextStyle:{{color:'#666'}}, axisLine:{{show:false}},
            splitLine:{{lineStyle:{{color:'#eee'}}}}, axisLabel:{{color:'#666'}} }},
  series: [
    {{ name:'历史日', type:'scatter', symbolSize:8,
       itemStyle:{{color:'rgba(44,123,229,0.6)'}},
       data:D.scatter }},
    {{ name:'回归线', type:'line', symbol:'none',
       lineStyle:{{color:'#ee6666', width:2}},
       itemStyle:{{color:'#ee6666'}},
       data:[D.x_line, D.y_line].length? [
           {{value:[D.x_line[0], D.y_line[0]]}},
           {{value:[D.x_line[1], D.y_line[1]]}}
       ] : [] }}
  ]
}});

var c_hr = echarts.init(document.getElementById('c_hour_r'));
c_hr.setOption({{
  tooltip: {{ trigger:'axis', formatter:function(p){{ return p[0].name+' 时 r='+p[0].value; }} }},
  grid: {{ left:50, right:20, top:20, bottom:40 }},
  xAxis: {{ type:'category', data:Array.from({{length:24}},function(_,i){{return ('0'+i).slice(-2)}}),
            axisLabel:{{color:'#666'}}, axisLine:{{lineStyle:{{color:'#ddd'}}}} }},
  yAxis: {{ type:'value', min:-0.2, max:1, axisLine:{{show:false}},
            splitLine:{{lineStyle:{{color:'#eee'}}}}, axisLabel:{{color:'#666'}} }},
  series: [{{ type:'bar', data:D.hour_r,
             itemStyle:{{color:'#5ab463'}},
             markLine:{{ data:[{{yAxis:0.9, lineStyle:{{color:'#ccc'}}}}], symbol:'none' }} }}]
}});

window.addEventListener('resize', function() {{
  c_pv.resize(); c_rad.resize(); c_val.resize(); c_hr.resize();
}});
</script>
</body>
</html>"""
    return html


if __name__ == "__main__":
    main()
