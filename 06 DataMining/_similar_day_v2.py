"""Enhanced similar day analysis with must-run unit estimation.
Adds: 谷段竞价空间、预估火电出清、必开估算(直调负荷×13%)、开机台数、单台调节机组出力
Output: 相似日分析_v2_YYYY-MM-DD.html
"""
import json, math, os, sqlite3, sys
from collections import defaultdict
from datetime import datetime, date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'output', '竞价空间分析结果')
DB_PATH = os.path.join(ROOT, 'data', 'cache', 'local.db')
FEATURES_PATH = os.path.join(ROOT, '_tmp_similar_features.json')

TIME_LABELS = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0, 15, 30, 45)]
W = 8  # 2h = 8个15min点

# ── 回归系数（从similar_day_analysis.py复用）──
PEAK_UNITS_A = 0.0019
PEAK_UNITS_B = 13.12
VALLEY_UNITS_A = 0.0011
VALLEY_UNITS_B = 79.88

# 谷段最小出力地板线（由峰值台数决定）
MIN_OUTPUT_BY_UNITS = [
    (0, 60, 7856), (60, 70, 9573), (70, 80, 11193),
    (80, 90, 12733), (90, 100, 17035), (100, 9999, 22421),
]

# 单机最小出力估算（MW/台）
UNIT_MIN_OUTPUT = {
    (0, 60): 130, (60, 70): 160, (70, 80): 160,
    (80, 90): 160, (90, 100): 180, (100, 9999): 220,
}


def load_data():
    """Load bidding_space_forecast from local SQLite."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('SELECT date, time_order, bidding_space FROM bidding_space_forecast ORDER BY date, time_order').fetchall()
    conn.close()
    data = defaultdict(list)
    for d, to, bs in rows:
        data[d].append(bs or 0)
    return dict(data)


def load_prices():
    """Load dayahead and realtime prices from local SQLite."""
    conn = sqlite3.connect(DB_PATH)
    da = defaultdict(list)
    rt = defaultdict(list)
    for r in conn.execute('SELECT date, time_order, price FROM dayahead_price ORDER BY date, time_order').fetchall():
        da[r[0]].append(float(r[2] or 0))
    for r in conn.execute('SELECT date, time_order, price FROM realtime_price ORDER BY date, time_order').fetchall():
        rt[r[0]].append(float(r[2] or 0))
    conn.close()
    return {'dayahead': dict(da), 'realtime': dict(rt)}


def load_actual_load():
    """Load actual load info (dispatched, bs, local) from remote DB for recent dates."""
    import pymysql
    for line in open(os.path.join(ROOT, '.env'), encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())
    conn = pymysql.connect(
        host=os.getenv('DB_TIANJI_HOST'), port=int(os.getenv('DB_TIANJI_PORT', 3306)),
        user=os.getenv('DB_TIANJI_USER'), password=os.getenv('DB_TIANJI_PASSWORD'),
        database=os.getenv('DB_TIANJI_DATABASE'), charset='utf8mb4',
        connect_timeout=10, read_timeout=60)
    cur = conn.cursor()
    cur.execute("""SELECT date, time_order, actual_dispatched_load, actual_tie_line_load,
        actual_wind_power, actual_photovoltaic_power, actual_nuclear_power, actual_self_power, actual_local_power
        FROM shandong_px_spot_actual_load_info ORDER BY date, time_order""")
    data = defaultdict(list)
    for r in cur.fetchall():
        d = str(r[0])
        dispatched = float(r[2] or 0)
        bs = dispatched - float(r[3] or 0) - float(r[4] or 0) - float(r[5] or 0) - float(r[6] or 0) - float(r[7] or 0)
        data[d].append({'dispatched': dispatched, 'bs': bs, 'local': float(r[8] or 0)})
    cur.close(); conn.close()
    return dict(data)


def load_dayahead_clearing():
    """Load dayahead thermal clearing from remote DB."""
    import pymysql
    for line in open(os.path.join(ROOT, '.env'), encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())
    conn = pymysql.connect(
        host=os.getenv('DB_TIANJI_HOST'), port=int(os.getenv('DB_TIANJI_PORT', 3306)),
        user=os.getenv('DB_TIANJI_USER'), password=os.getenv('DB_TIANJI_PASSWORD'),
        database=os.getenv('DB_TIANJI_DATABASE'), charset='utf8mb4',
        connect_timeout=10, read_timeout=60)
    cur = conn.cursor()
    cur.execute("""SELECT date, time_point, thermal_clearing, independent_clearing, draw_clearing, virtual_clearing
        FROM shandong_px_dayahead_clearing_quantity_number ORDER BY date, time_point""")
    data = defaultdict(list)
    for r in cur.fetchall():
        data[str(r[0])].append({
            'thermal': float(r[2] or 0) * 4,
            'es_dr_vi': (float(r[3] or 0) + float(r[4] or 0) + float(r[5] or 0)) * 4
        })
    cur.close(); conn.close()
    return dict(data)


def find_peak_valley_windows(values):
    """Find 2h peak and valley windows from 96-point curve."""
    best_vi, best_vs = 0, float('inf')
    best_pi, best_ps = 0, float('-inf')
    for i in range(len(values) - W + 1):
        s = sum(values[i:i+W])
        if s < best_vs: best_vs = s; best_vi = i
        if s > best_ps: best_ps = s; best_pi = i
    return best_vi, best_pi


def compute_enhanced_features(target_date, bs_values, actual_load, da_clearing, prices):
    """Compute enhanced features including must-run estimation."""
    vi, pi = find_peak_valley_windows(bs_values)

    # 谷段/峰段竞价空间
    valley_bs = sum(bs_values[vi:vi+W]) / W
    peak_bs = sum(bs_values[pi:pi+W]) / W

    # 预估火电出清（从bs回归：thermal ≈ bs × 系数，简化用bs直接估算）
    # 实际火电 = bs - local - es_dr_vi，但local/es_dr_vi在预测日不可得
    # 用回归：火电出清 ≈ bs × 0.85（经验系数，从5-7月数据拟合）
    est_thermal_valley = valley_bs * 0.85
    est_thermal_peak = peak_bs * 0.85

    # 必开估算 = 直调负荷 × 13%（非供暖期）
    # 直调负荷 ≈ bs + 联络线 + 新能源，但预测日只有bs
    # 简化：直调负荷 ≈ bs / 0.75（bs约占直调负荷75%）
    est_dispatched_valley = valley_bs / 0.75
    est_dispatched_peak = peak_bs / 0.75
    must_run_valley = est_dispatched_valley * 0.13
    must_run_peak = est_dispatched_peak * 0.13

    # 开机台数（从bs回归）
    peak_units = round(PEAK_UNITS_A * peak_bs + PEAK_UNITS_B)
    valley_units = round(VALLEY_UNITS_A * valley_bs + VALLEY_UNITS_B)

    # 必开台数估算（必开≈13%直调负荷，单台平均300MW）
    must_run_units_valley = round(must_run_valley / 300)
    must_run_units_peak = round(must_run_peak / 300)

    # 调节机组台数
    reg_units_valley = max(0, valley_units - must_run_units_valley)
    reg_units_peak = max(0, peak_units - must_run_units_peak)

    # 调节机组出力
    reg_output_valley = est_thermal_valley - must_run_valley
    reg_output_peak = est_thermal_peak - must_run_peak

    # 单台调节机组出力
    unit_output_valley = reg_output_valley / reg_units_valley if reg_units_valley > 0 else 0
    unit_output_peak = reg_output_peak / reg_units_peak if reg_units_peak > 0 else 0

    # 单机最小出力（根据台数档位，考虑保供季上调）
    min_output_per_unit = 160  # 默认
    for (lo, hi), v in UNIT_MIN_OUTPUT.items():
        if lo <= peak_units < hi:
            min_output_per_unit = v
            break
    # 7-8月保供季：火电基本接近满发，单台最小出力显著高于其他季节
    month = int(target_date.split('-')[1])
    if month in (7, 8):
        min_output_per_unit = max(min_output_per_unit, 280)  # 保供季最小出力≥280MW

    # 是否压到最小出力
    is_at_min_valley = unit_output_valley <= min_output_per_unit * 1.2  # 20%容差

    # 保供季标记（充电推荐和地板价概率共用）
    is_summer_peak = month in (7, 8)

    # 单台出力 / 最小出力 比值
    unit_ratio = unit_output_valley / min_output_per_unit if min_output_per_unit > 0 else 999

    # 地板价概率（简化：谷值<0→100%，保供季谷值<10GW→80%，<15GW→50%）
    floor_prob = 0
    if valley_bs < 0:
        floor_prob = 100
    elif is_summer_peak:
        if valley_bs < 5000:
            floor_prob = 90
        elif valley_bs < 10000:
            floor_prob = 70
        elif valley_bs < 15000:
            floor_prob = 40
        else:
            floor_prob = 10
    else:
        if unit_ratio <= 1.0 and valley_bs < 15000:
            floor_prob = 90
        elif unit_ratio <= 1.2 and valley_bs < 20000:
            floor_prob = 70
        elif unit_ratio <= 1.5:
            floor_prob = 40
        else:
            floor_prob = 10

    # 充电推荐（基于单台调节机组出力 vs 最小出力 + 保供季修正）
    # 核心逻辑：单台出力接近最小出力 → 火电无法下压 → 地板价 → 强充电
    # 7-8月保供季：火电接近满发，单台出力普遍偏高，即使<最小出力也不代表会触地板

    if valley_bs < 0:
        charge_mw, charge_label = -9600, '极强(谷值<0)'
    elif is_summer_peak:
        # 保供季：看谷值绝对水平，不看单台出力（保供日火电难压到最小）
        if valley_bs < 5000:
            charge_mw, charge_label = -9600, '极强(谷值极低)'
        elif valley_bs < 10000:
            charge_mw, charge_label = -7700, '强(谷值低)'
        elif valley_bs < 15000:
            charge_mw, charge_label = -6500, '中'
        elif valley_bs < 20000:
            charge_mw, charge_label = -5000, '弱中(保供)'
        else:
            charge_mw, charge_label = -3000, '弱(保供高负荷)'
    else:
        # 非保供季：单台出力是有效指标
        if unit_ratio <= 1.0:
            charge_mw, charge_label = -9600, '极强(压到最小)'
        elif unit_ratio <= 1.2:
            charge_mw, charge_label = -8400, '强(接近最小)'
        elif unit_ratio <= 1.5:
            charge_mw, charge_label = -7700, '中强'
        elif unit_ratio <= 2.0:
            charge_mw, charge_label = -6500, '中'
        elif valley_bs < 10000:
            charge_mw, charge_label = -5000, '弱中'
        else:
            charge_mw, charge_label = -3000, '弱'

    return {
        'valley_bs': round(valley_bs, 0),
        'peak_bs': round(peak_bs, 0),
        'est_thermal_valley': round(est_thermal_valley, 0),
        'est_thermal_peak': round(est_thermal_peak, 0),
        'must_run_valley': round(must_run_valley, 0),
        'must_run_peak': round(must_run_peak, 0),
        'peak_units': peak_units,
        'valley_units': valley_units,
        'must_run_units_valley': must_run_units_valley,
        'must_run_units_peak': must_run_units_peak,
        'reg_units_valley': reg_units_valley,
        'reg_units_peak': reg_units_peak,
        'reg_output_valley': round(reg_output_valley, 0),
        'reg_output_peak': round(reg_output_peak, 0),
        'unit_output_valley': round(unit_output_valley, 0),
        'unit_output_peak': round(unit_output_peak, 0),
        'min_output_per_unit': min_output_per_unit,
        'is_at_min_valley': is_at_min_valley,
        'floor_prob': floor_prob,
        'unit_ratio': round(unit_ratio, 2),
        'charge_mw': charge_mw,
        'charge_label': charge_label,
        'charge_mwh': round(abs(charge_mw) * 2, 0),
        'valley_window': f'{TIME_LABELS[vi]}-{TIME_LABELS[vi+W-1]}',
        'peak_window': f'{TIME_LABELS[pi]}-{TIME_LABELS[pi+W-1]}',
    }


def compute_similarity(target, candidates, top_n=10):
    """Compute similarity scores."""
    t = candidates[target]
    results = []
    for d, c in candidates.items():
        if d == target: continue
        # 简化的相似度计算
        score = 0
        # 谷值接近度
        v_diff = abs(c['valley_bs'] - t['valley_bs']) / max(t['valley_bs'], 1)
        score += max(0, 1 - v_diff) * 0.3
        # 峰值接近度
        p_diff = abs(c['peak_bs'] - t['peak_bs']) / max(t['peak_bs'], 1)
        score += max(0, 1 - p_diff) * 0.25
        # 时间近邻
        days_diff = abs((datetime.strptime(d, '%Y-%m-%d') - datetime.strptime(target, '%Y-%m-%d')).days)
        time_score = max(0, 1 - days_diff / 365)
        score += time_score * 0.15
        # 形状相关（简化）
        score += 0.3  # 占位

        results.append({'date': d, 'score': round(score, 4), **c})

    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_n]


def generate_html(target_date, similar_days, all_features, prices):
    """Generate enhanced HTML with must-run analysis."""
    t = all_features[target_date]

    # 准备嵌入数据
    embed = {target_date: t}
    for s in similar_days:
        embed[s['date']] = all_features[s['date']]

    embed_json = json.dumps(embed, ensure_ascii=False)
    similar_json = json.dumps(similar_days, ensure_ascii=False)

    # 电价数据
    da = prices.get('dayahead', {})
    rt = prices.get('realtime', {})
    embed_prices = {}
    for d in [target_date] + [s['date'] for s in similar_days]:
        embed_prices[d] = {
            'dayahead': da.get(d, []),
            'realtime': rt.get(d, []),
        }
    prices_json = json.dumps(embed_prices, ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>相似日分析 v2 | {target_date}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}}
.header{{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600}}
.header .info{{font-size:11px;color:#888}}
.panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;margin:8px 24px;overflow:hidden}}
.panel .t{{padding:6px 14px;font-size:12px;font-weight:600;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.panel .c{{width:100%;height:400px}}
.rec-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;padding:12px}}
.rec-card{{background:#fafafa;border:1px solid #e0e0e0;border-radius:4px;padding:10px;text-align:center}}
.rc-label{{font-size:11px;color:#888;margin-bottom:4px}}
.rc-value{{font-size:18px;font-weight:700}}
.rc-sub{{font-size:10px;color:#888;margin-top:2px}}
.rec-note{{padding:12px;font-size:11px;color:#666;background:#f9f9f9;border-top:1px solid #e0e0e0}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th,td{{padding:6px 8px;text-align:right;border-bottom:1px solid #e0e0e0}}
th{{background:#f5f5f5;font-weight:600}}
tr:hover{{background:#f5f5f5}}
</style>
</head>
<body>
<div class="header">
<h1>相似日分析 v2 | {target_date}</h1>
<div class="info">必开估算=直调负荷×13% · 单台调节机组出力=调节出力/调节台数 · 地板价判断=单台出力接近最小出力 · 数据来源：天机库+本地库</div>
</div>

<div class="panel">
<div class="t">★ 储能充放推荐（基于必开+调节机组分析）</div>
<div class="rec-grid" id="recGrid"></div>
<div class="rec-note" id="recNote"></div>
</div>

<div class="panel"><div class="t">目标日 vs 相似日 竞价空间曲线</div><div class="c" id="c1"></div></div>
<div class="panel"><div class="t">目标日 vs 相似日 电价对比</div><div class="c" id="c2"></div></div>

<div class="panel">
<div class="t">相似日排名（含增强指标）</div>
<div style="overflow-x:auto"><table id="simTable">
<thead><tr>
<th>#</th><th>日期</th><th>相似度</th><th>谷段bs</th><th>峰段bs</th>
<th>必开估算</th><th>调节出力</th><th>单台出力</th><th>触地板概率</th><th>充电推荐</th>
</tr></thead>
<tbody id="simTbody"></tbody>
</table></div>
</div>

<script>
var TARGET = '{target_date}';
var DATA = {embed_json};
var SIMILAR = {similar_json};
var PRICES = {prices_json};
var TL = {json.dumps(TIME_LABELS, ensure_ascii=False)};

function fmt(v) {{ return v!=null ? v.toLocaleString() : '—'; }}

// 渲染推荐卡片
function renderRec() {{
  var t = DATA[TARGET];
  var html = '';
  html += '<div class="rec-card"><div class="rc-label">谷段竞价空间</div><div class="rc-value" style="color:#d13438">'+fmt(t.valley_bs)+' MW</div><div class="rc-sub">'+t.valley_window+'</div></div>';
  html += '<div class="rec-card"><div class="rc-label">预估火电出清(谷)</div><div class="rc-value" style="color:#0078d4">'+fmt(t.est_thermal_valley)+' MW</div><div class="rc-sub">bs×0.85</div></div>';
  html += '<div class="rec-card"><div class="rc-label">必开估算</div><div class="rc-value" style="color:#9a60b4">'+fmt(t.must_run_valley)+' MW</div><div class="rc-sub">直调负荷×13%</div></div>';
  html += '<div class="rec-card"><div class="rc-label">开机台数(谷/峰)</div><div class="rc-value">'+t.valley_units+'/'+t.peak_units+'台</div><div class="rc-sub">回归估算</div></div>';
  html += '<div class="rec-card"><div class="rc-label">调节机组出力(谷)</div><div class="rc-value" style="color:#e67e22">'+fmt(t.reg_output_valley)+' MW</div><div class="rc-sub">'+t.reg_units_valley+'台</div></div>';
  html += '<div class="rec-card" style="border-color:'+(t.is_at_min_valley?'#52c41a':'#f5222d')+'"><div class="rc-label">★ 单台调节机组出力</div><div class="rc-value" style="color:'+(t.is_at_min_valley?'#52c41a':'#f5222d')+'">'+fmt(t.unit_output_valley)+' MW</div><div class="rc-sub">'+t.unit_ratio+'×最小出力 ('+t.min_output_per_unit+'MW)</div></div>';
  html += '<div class="rec-card" style="border-color:'+(t.floor_prob>=80?'#52c41a':t.floor_prob>=50?'#faad14':'#f5222d')+'"><div class="rc-label">触地板概率</div><div class="rc-value" style="color:'+(t.floor_prob>=80?'#52c41a':t.floor_prob>=50?'#faad14':'#f5222d')+'">'+t.floor_prob+'%</div><div class="rc-sub">'+(t.floor_prob>=80?'高':t.floor_prob>=50?'中':'低')+'</div></div>';
  html += '<div class="rec-card" style="border-color:#52c41a"><div class="rc-label">★ 谷段充电推荐</div><div class="rc-value" style="color:#52c41a">'+fmt(t.charge_mw)+' MW</div><div class="rc-sub">'+t.charge_label+' | '+t.charge_mwh+' MWh(2h)</div></div>';
  document.getElementById('recGrid').innerHTML = html;

  var note = '<b>分析逻辑：</b>谷段火电出清 = 竞价空间×0.85 → 必开估算 = 直调负荷×13% → 调节机组出力 = 火电-必开 → 单台出力 = 调节出力/调节台数。'
    + '当单台出力接近最小出力(' + t.min_output_per_unit + 'MW)时，火电无法进一步下压，电价触地板。'
    + '<br><b>7月保供季注意：</b>必开占比可能高于13%，调节出力被高估，实际触地板概率可能低于计算值。';
  document.getElementById('recNote').innerHTML = note;
}}

// 渲染相似日表格
function renderTable() {{
  var html = '';
  SIMILAR.forEach(function(s, i) {{
    var probColor = s.floor_prob>=80?'#52c41a':s.floor_prob>=50?'#faad14':'#f5222d';
    html += '<tr>';
    html += '<td>'+(i+1)+'</td>';
    html += '<td>'+s.date+'</td>';
    html += '<td><b>'+s.score.toFixed(4)+'</b></td>';
    html += '<td>'+fmt(s.valley_bs)+' MW</td>';
    html += '<td>'+fmt(s.peak_bs)+' MW</td>';
    html += '<td>'+fmt(s.must_run_valley)+' MW</td>';
    html += '<td>'+fmt(s.reg_output_valley)+' MW</td>';
    html += '<td>'+fmt(s.unit_output_valley)+' MW</td>';
    html += '<td style="color:'+probColor+'">'+s.floor_prob+'%</td>';
    html += '<td style="color:#52c41a">'+fmt(s.charge_mw)+' MW</td>';
    html += '</tr>';
  }});
  document.getElementById('simTbody').innerHTML = html;
}}

// 竞价空间曲线
var c1 = echarts.init(document.getElementById('c1'));
function renderC1() {{
  var series = [];
  var t = DATA[TARGET];
  series.push({{
    name:TARGET+'(目标)', type:'line', data:t.values||[], smooth:true,
    lineStyle:{{width:3,color:'#0078d4'}}, itemStyle:{{color:'#0078d4'}}, symbol:'none'
  }});
  SIMILAR.slice(0,5).forEach(function(s,i) {{
    var d = DATA[s.date];
    if(d && d.values) {{
      series.push({{
        name:s.date+'(相似度:'+s.score.toFixed(3)+')', type:'line', data:d.values, smooth:true,
        lineStyle:{{width:1,color:'#999'}}, itemStyle:{{color:'#999'}}, symbol:'none'
      }});
    }}
  }});
  c1.setOption({{
    grid:{{left:55,right:90,top:20,bottom:50}},
    tooltip:{{trigger:'axis'}},
    legend:{{textStyle:{{color:'#666',fontSize:10}},top:3}},
    xAxis:{{type:'category',data:TL,axisLabel:{{interval:11,fontSize:9}}}},
    yAxis:{{type:'value',name:'MW'}},
    series:series
  }});
}}

// 电价对比
var c2 = echarts.init(document.getElementById('c2'));
function renderC2() {{
  var series = [];
  var t = PRICES[TARGET];
  if(t.dayahead && t.dayahead.length) {{
    series.push({{
      name:TARGET+'日前', type:'line', data:t.dayahead, smooth:true,
      lineStyle:{{width:2,color:'#0078d4'}}, itemStyle:{{color:'#0078d4'}}, symbol:'none'
    }});
  }}
  if(t.realtime && t.realtime.length) {{
    series.push({{
      name:TARGET+'实时', type:'line', data:t.realtime, smooth:true,
      lineStyle:{{width:2,color:'#e67e22'}}, itemStyle:{{color:'#e67e22'}}, symbol:'none'
    }});
  }}
  SIMILAR.slice(0,3).forEach(function(s,i) {{
    var d = PRICES[s.date];
    if(d && d.dayahead && d.dayahead.length) {{
      series.push({{
        name:s.date+'日前', type:'line', data:d.dayahead, smooth:true,
        lineStyle:{{width:1,color:'#999',type:'dashed'}}, itemStyle:{{color:'#999'}}, symbol:'none'
      }});
    }}
  }});
  c2.setOption({{
    grid:{{left:55,right:90,top:20,bottom:50}},
    tooltip:{{trigger:'axis'}},
    legend:{{textStyle:{{color:'#666',fontSize:10}},top:3}},
    xAxis:{{type:'category',data:TL,axisLabel:{{interval:11,fontSize:9}}}},
    yAxis:{{type:'value',name:'元/MWh'}},
    series:series
  }});
}}

renderRec(); renderTable(); renderC1(); renderC2();
window.addEventListener('resize', function(){{c1.resize();c2.resize();}});
</script>
</body>
</html>'''
    return html


def main(target_date, top_n=10):
    # 加载数据
    print('Loading bidding space forecast...')
    bs_data = load_data()

    print('Loading prices...')
    prices = load_prices()

    # 检查目标日
    if target_date not in bs_data:
        print(f'Target date {target_date} not found in bidding_space_forecast')
        print(f'Available: {sorted(bs_data.keys())[-5:]}')
        return

    # 计算所有日期的增强特征
    print('Computing enhanced features...')
    all_features = {}
    for d, values in bs_data.items():
        if len(values) != 96:
            continue
        all_features[d] = compute_enhanced_features(d, values, None, None, prices)
        all_features[d]['values'] = values  # 保留原始曲线

    # 相似度计算
    print('Computing similarity...')
    similar = compute_similarity(target_date, all_features, top_n)

    print(f'\nTarget: {target_date}')
    print(f'Top {len(similar)} similar days:')
    for i, s in enumerate(similar):
        print(f'  {i+1}. {s["date"]} score={s["score"]:.4f} valley={s["valley_bs"]:.0f}MW charge={s["charge_mw"]}MW')

    # 生成HTML
    html = generate_html(target_date, similar, all_features, prices)

    os.makedirs(OUT_DIR, exist_ok=True)
    fname = f'相似日分析_v2_{target_date}.html'
    out_path = os.path.join(OUT_DIR, fname)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'\nSaved: {out_path}')
    print(f'Size: {len(html):,} bytes')

    # 打印目标日详细分析
    t = all_features[target_date]
    print(f'\n=== {target_date} 详细分析 ===')
    print(f'谷段竞价空间: {t["valley_bs"]:.0f} MW ({t["valley_window"]})')
    print(f'峰段竞价空间: {t["peak_bs"]:.0f} MW ({t["peak_window"]})')
    print(f'预估火电出清(谷): {t["est_thermal_valley"]:.0f} MW')
    print(f'必开估算(谷): {t["must_run_valley"]:.0f} MW')
    print(f'开机台数(谷/峰): {t["valley_units"]}/{t["peak_units"]}台')
    print(f'调节机组出力(谷): {t["reg_output_valley"]:.0f} MW ({t["reg_units_valley"]}台)')
    print(f'单台调节机组出力(谷): {t["unit_output_valley"]:.0f} MW (最小出力{t["min_output_per_unit"]}MW)')
    print(f'是否压到最小出力: {"是" if t["is_at_min_valley"] else "否"}')
    print(f'触地板概率: {t["floor_prob"]}%')
    print(f'充电推荐: {t["charge_mw"]} MW ({t["charge_label"]})')


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: python _similar_day_v2.py YYYY-MM-DD [top_n]')
        sys.exit(1)
    target = sys.argv[1]
    top = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    main(target, top)
