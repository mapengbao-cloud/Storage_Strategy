"""Generate bidding space visualization from tianrun_new database.

预测竞价空间 = 直调负荷 - 联络线受电 - 风电总加 - 光伏总加 - 核电总加 - 自备机组
真实竞价空间 = 同上公式，使用实际运行数据
注：地方电厂(local_power)是地方电厂发电总加，不属竞价空间，预留用于分布式光伏=全网负荷-直调-地方电厂

Usage:
    python bidding_space_viz.py                              # 预测 (默认)
    python bidding_space_viz.py --actual                     # 实际
    python bidding_space_viz.py --compare                    # 预测vs实际对比
    python bidding_space_viz.py 2026-06-01 2026-06-15        # 预测，指定日期
    python bidding_space_viz.py --actual 2026-06-01 2026-06-15
    python bidding_space_viz.py --compare 2026-06-01 2026-06-15

Output: output/竞价空间分析结果/预测竞价空间_YYYY-MM-DD_YYYY-MM-DD.html
        output/竞价空间分析结果/真实竞价空间_YYYY-MM-DD_YYYY-MM-DD.html
        output/竞价空间分析结果/竞价空间对比_YYYY-MM-DD_YYYY-MM-DD.html
"""

import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

import pymysql

# ===== DATE_RANGE: 默认日期范围 =====
DEFAULT_START = '2026-06-01'
DEFAULT_END = '2026-06-22'

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'output', '竞价空间分析结果')

# 本地 SQLite 数据库路径
LOCAL_DB_PATH = os.path.join(ROOT, 'data', 'cache', 'local.db')

DB_CONFIG = {
    'host': 'rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com',
    'port': 3306,
    'user': 'pengyiqiang',
    'password': 'pengyiqiang123',
    'database': 'tianrun_new',
}


def _time_labels():
    labels = []
    for h in range(24):
        for m in (0, 15, 30, 45):
            labels.append(f'{h:02d}:{m:02d}')
    return labels


TIME_LABELS = _time_labels()

# ── 表/列映射 ──
TABLE_CONFIG = {
    'forecast': {
        'table': 'shandong_px_spot_dayahead_load_info',
        'columns': {
            '直调负荷': 'dispatched_load_forecast',
            '联络线受电': 'tie_line_load_forecast',
            '风电总加': 'wind_power_forecast',
            '光伏总加': 'photovoltaic_power_forecast',
            '核电总加': 'nuclear_power_forecast',
            '地方电厂': 'local_power_forecast',   # 地方电厂发电总加，预留(分布式光伏用)，不参与bs
            '自备机组': 'self_power_forecast',
        },
        'label': '预测',
        'info': '数据来源: shandong_px_spot_dayahead_load_info',
        'source_desc': 'shandong_px_spot_dayahead_load_info',
        'data_type': '日前负荷预测数据',
    },
    'actual': {
        'table': 'shandong_px_spot_actual_load_info',
        'columns': {
            '直调负荷': 'actual_dispatched_load',
            '联络线受电': 'actual_tie_line_load',
            '风电总加': 'actual_wind_power',
            '光伏总加': 'actual_photovoltaic_power',
            '核电总加': 'actual_nuclear_power',
            '地方电厂': 'actual_local_power',   # 地方电厂发电总加，预留，不参与bs
            '自备机组': 'actual_self_power',
        },
        'label': '真实',
        'info': '数据来源: shandong_px_spot_actual_load_info',
        'source_desc': 'shandong_px_spot_actual_load_info',
        'data_type': '实际运行数据',
    },
}


def fetch_data(start_date: str, end_date: str, mode: str) -> dict[str, dict]:
    """Query database, return {date: {field: [96 values]}}."""
    cfg = TABLE_CONFIG[mode]
    cols = cfg['columns']
    col_names = list(cols.values())
    col_sql = ', '.join(col_names)

    conn = pymysql.connect(**DB_CONFIG)
    c = conn.cursor()
    sql = f"""
        SELECT date, time_order, {col_sql}
        FROM {cfg['table']}
        WHERE date >= %s AND date <= %s
        ORDER BY date, time_order
    """
    c.execute(sql, (start_date, end_date))
    rows = c.fetchall()
    conn.close()

    # Build reverse map: col_name -> field_label
    rev = {v: k for k, v in cols.items()}

    data = defaultdict(lambda: defaultdict(list))
    for row in rows:
        ds = str(row[0])
        vals = row[2:]  # skip date, time_order
        for i, col_name in enumerate(col_names):
            label = rev[col_name]
            v = float(vals[i]) if vals[i] is not None else 0
            data[ds][label].append(v)
        # 竞价空间 = 直调负荷 - (联络线受电 + 风电 + 光伏 + 核电 + 自备)
        # 注：地方电厂(local_power)不参与bs，预留用于分布式光伏
        bs = (
            data[ds]['直调负荷'][-1]
            - data[ds]['联络线受电'][-1]
            - data[ds]['风电总加'][-1]
            - data[ds]['光伏总加'][-1]
            - data[ds]['核电总加'][-1]
            - data[ds]['自备机组'][-1]
        )
        data[ds]['竞价空间'].append(bs)

    return dict(data)


def fetch_price_data(start_date: str, end_date: str, price_type: str) -> dict[str, list[float]]:
    """Query remote MySQL for 润津 electricity price data.

    Args:
        price_type: 'dayahead' → shandong_px_reliable_clearing_unit_data
                    'realtime' → shandong_px_realtime_clearing_results_query

    Returns:
        {date: [96 price values]}
    """
    member_id = 'b9e64e64a713458eba94c9af05c0a757'
    table = ('shandong_px_reliable_clearing_unit_data' if price_type == 'dayahead'
             else 'shandong_px_realtime_clearing_results_query')

    conn = pymysql.connect(**DB_CONFIG)
    c = conn.cursor()
    sql = f"""
        SELECT date, time_point, price
        FROM {table}
        WHERE member_id = %s AND date >= %s AND date <= %s
            AND unit_name LIKE '%%润津%%'
        ORDER BY date, time_point
    """
    c.execute(sql, (member_id, start_date, end_date))
    rows = c.fetchall()
    conn.close()

    data = defaultdict(list)
    for d, tp, price in rows:
        ds = str(d)
        if isinstance(tp, str):
            parts = tp.split(':')
            to = int(parts[0]) * 4 + int(parts[1]) // 15
        else:
            to = int(tp) - 1
        while len(data[ds]) < to:
            data[ds].append(0.0)
        data[ds].append(float(price) if price else 0.0)

    for ds in list(data.keys()):
        while len(data[ds]) < 96:
            data[ds].append(data[ds][-1] if data[ds] else 0.0)

    return dict(data)


def fetch_price_data_local(start_date: str, end_date: str, price_type: str) -> dict[str, list[float]]:
    """Query local SQLite for price data."""
    table = 'dayahead_price' if price_type == 'dayahead' else 'realtime_price'
    conn = sqlite3.connect(LOCAL_DB_PATH)
    sql = f'''
        SELECT date, time_order, price FROM {table}
        WHERE date >= ? AND date <= ?
        ORDER BY date, time_order
    '''
    rows = conn.execute(sql, (start_date, end_date)).fetchall()
    conn.close()

    data = defaultdict(list)
    for d, to, price in rows:
        while len(data[d]) < to - 1:
            data[d].append(0.0)
        data[d].append(price or 0.0)

    for ds in list(data.keys()):
        while len(data[ds]) < 96:
            data[ds].append(data[ds][-1] if data[ds] else 0.0)

    return dict(data)


def fetch_data_local(start_date: str, end_date: str, mode: str) -> dict[str, dict]:
    """Query local SQLite, return {date: {field: [96 values]}} — same format as fetch_data()."""
    table = 'bidding_space_forecast' if mode == 'forecast' else 'bidding_space_actual'
    conn = sqlite3.connect(LOCAL_DB_PATH)
    sql = f'''
        SELECT date, time_order, dispatched_load, tie_line_load,
               wind_power, photovoltaic_power, nuclear_power,
               local_power, self_power, bidding_space
        FROM {table}
        WHERE date >= ? AND date <= ?
        ORDER BY date, time_order
    '''
    rows = conn.execute(sql, (start_date, end_date)).fetchall()
    conn.close()

    data = defaultdict(lambda: defaultdict(list))
    for d, to, dl, tl, wp, pv, nu, loc, slf, bs in rows:
        data[d]['直调负荷'].append(dl or 0)
        data[d]['联络线受电'].append(tl or 0)
        data[d]['风电总加'].append(wp or 0)
        data[d]['光伏总加'].append(pv or 0)
        data[d]['核电总加'].append(nu or 0)
        data[d]['地方电厂'].append(loc or 0)   # 地方电厂发电总加，预留(分布式光伏用)，不参与bs
        data[d]['自备机组'].append(slf or 0)
        data[d]['竞价空间'].append(bs or 0)

    return dict(data)


def fetch_both_data_local(start_date: str, end_date: str) -> dict[str, dict]:
    """Query both forecast and actual from local SQLite."""
    fg = fetch_data_local(start_date, end_date, 'forecast')
    ac = fetch_data_local(start_date, end_date, 'actual')

    common_dates = sorted(set(fg.keys()) & set(ac.keys()))
    fields = ['直调负荷', '联络线受电', '风电总加', '光伏总加', '核电总加', '地方电厂', '自备机组', '竞价空间']

    merged = {}
    for d in common_dates:
        merged[d] = {}
        for f in fields:
            merged[d][f] = {
                '预测': fg[d][f],
                '实际': ac[d][f],
            }

    return merged


def _build_html(all_dates: list[str], data: dict, title: str, mode: str,
                 price_data: dict[str, list[float]] | None = None,
                 price_source: str = '') -> str:
    """Generate self-contained ECharts HTML."""
    cfg = TABLE_CONFIG[mode]
    price_label = '日前电价' if mode == 'forecast' else '实时电价'

    time_labels_json = json.dumps(TIME_LABELS, ensure_ascii=False)
    data_json = json.dumps(data, ensure_ascii=False)
    price_json = json.dumps(price_data, ensure_ascii=False) if price_data else 'null'
    dates_json = json.dumps(all_dates, ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333;min-height:100vh}}
.header{{background:#fff;padding:12px 24px;border-bottom:1px solid #d9d9d9;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600}}
.header .info{{font-size:11px;color:#888}}
.date-tabs{{display:flex;flex-wrap:wrap;gap:3px;max-width:100%;overflow-x:auto}}
.date-tab{{padding:4px 10px;border:1px solid #c8c8c8;border-radius:4px;cursor:pointer;background:#fff;color:#555;font-size:11px;transition:all .15s;white-space:nowrap}}
.date-tab:hover{{background:#e5f3ff;border-color:#0078d4;color:#0078d4}}
.date-tab.active{{background:#0078d4;border-color:#0078d4;color:#fff;font-weight:600}}
.summary-bar{{display:flex;gap:8px;padding:8px 20px;flex-wrap:wrap}}
.summary-chip{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:6px 14px;flex:1;min-width:120px;text-align:center}}
.summary-chip .chip-label{{font-size:10px;color:#888;margin-bottom:2px}}
.summary-chip .chip-value{{font-size:18px;font-weight:700;color:#0078d4}}
.summary-chip .chip-sub{{font-size:10px;color:#999}}
.main-grid{{display:grid;grid-template-columns:1fr 280px;gap:0}}
@media(max-width:1100px){{.main-grid{{grid-template-columns:1fr}}}}
.charts-area{{padding:8px;display:flex;flex-direction:column;gap:6px}}
.chart-panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.chart-panel .panel-title{{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.chart-box{{width:100%;height:340px}}
.sidebar{{background:#fff;border-left:1px solid #e0e0e0;padding:12px;overflow-y:auto;display:flex;flex-direction:column;gap:10px;max-height:calc(100vh - 180px)}}
.stats-card{{background:#fff;border:1px solid #e0e0e0;border-radius:6px;padding:12px}}
.stats-card h3{{font-size:13px;color:#0078d4;margin-bottom:8px;border-bottom:1px solid #e8e8e8;padding-bottom:6px}}
.stat-row{{display:flex;justify-content:space-between;padding:3px 0;font-size:11px;border-bottom:1px solid #f3f3f3}}
.stat-row .label{{color:#888}}
.stat-row .val{{font-weight:600;color:#333}}
.legend-tip{{font-size:10px;color:#999;margin-top:6px;line-height:1.5}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>{cfg["label"]}竞价空间分析</h1>
    <div class="info">{cfg['info']} | 公式: 直调负荷 - 联络线受电 - 风电 - 光伏 - 核电 - 自备 (地方电厂不参与bs)</div>
  </div>
  <div class="date-tabs" id="dateTabs"></div>
</div>
<div class="summary-bar" id="summaryBar"></div>
<div class="main-grid">
  <div class="charts-area">
    <div class="chart-panel">
      <div class="panel-title">竞价空间 <span style="font-weight:400;color:#888;font-size:11px">(MW)</span></div>
      <div class="chart-box" id="chartBiddingSpace"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">竞价空间构成 <span style="font-weight:400;color:#888;font-size:11px">(MW) — 点击图例切换显示</span></div>
      <div class="chart-box" id="chartComposition"></div>
    </div>
  </div>
  <div class="sidebar" id="sidebar">
    <div class="stats-card" id="statsCard"></div>
    <div class="legend-tip">
      数据来源：<br>
      · {cfg['source_desc']}<br>
      · 96点{cfg['data_type']}<br>
      · 竞价空间 = 直调负荷 - 联络线 - 风电 - 光伏 - 核电 - 自备<br>
      · {price_label}：{price_source}<br>
      · 键盘 ← → 切换日期<br>
      · 图例选择在切换日期后保持不变
    </div>
  </div>
</div>
<div class="footer">润津储能 · 竞价空间分析 · 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>

<script>
var DATA = {data_json};
var PRICE_DATA = {price_json};
var TIMES = {time_labels_json};
var ALL_DATES = {dates_json};
var currentDate = ALL_DATES[ALL_DATES.length - 1];

// Date tabs
var tabsEl = document.getElementById('dateTabs');
ALL_DATES.forEach(function(d) {{
  var b = document.createElement('div');
  b.className = 'date-tab';
  b.textContent = d.slice(5);
  b.onclick = function() {{ selectDate(d); }};
  tabsEl.appendChild(b);
}});

function selectDate(d) {{
  currentDate = d;
  document.querySelectorAll('.date-tab').forEach(function(t){{t.classList.remove('active');}});
  var idx = ALL_DATES.indexOf(d);
  if(idx>=0) document.querySelectorAll('.date-tab')[idx].classList.add('active');
  renderAll();
}}

var cBS = echarts.init(document.getElementById('chartBiddingSpace'));
var cComp = echarts.init(document.getElementById('chartComposition'));

var g = {{left:55,right:70,top:20,bottom:35}};
var ec = {{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var ec2 = {{axisLabel:{{color:'#e67e22',fontSize:10}},axisLine:{{lineStyle:{{color:'#e67e22'}}}},splitLine:{{show:false}}}};
var el = {{textStyle:{{color:'#666',fontSize:11}},top:3}};

// ── Legend selection persistence ──
var legendState = {{}};
cBS.on('legendselectchanged', function(params) {{ legendState.bs = params.selected; }});
cComp.on('legendselectchanged', function(params) {{ legendState.comp = params.selected; }});

function fmt(v){{return v!=null?v.toFixed(0):'—';}}
function fmtPrice(v){{return v!=null?v.toFixed(2):'—';}}

var HAS_PRICE = PRICE_DATA !== null;
var PRICE_LABEL = '{price_label}';

var ALL_SERIES = [
  {{key:'直调负荷', name:'直调负荷', color:'#5470c6', dashed:true, width:1.5, areaColor:'rgba(84,112,198,0.12)'}},
  {{key:'联络线受电', name:'联络线受电', color:'#d83b01', dashed:false, width:1.5, areaColor:'rgba(216,59,1,0.12)'}},
  {{key:'风电总加', name:'风电总加', color:'#107c10', dashed:false, width:2, area:true, areaColor:'rgba(16,124,16,0.12)'}},
  {{key:'光伏总加', name:'光伏总加', color:'#f2a900', dashed:false, width:2, area:true, areaColor:'rgba(242,169,0,0.12)'}},
  {{key:'核电总加', name:'核电总加', color:'#9a60b4', dashed:false, width:2, areaColor:'rgba(154,96,180,0.12)'}},
  {{key:'竞价空间', name:'竞价空间', color:'#0078d4', dashed:false, width:2.5, area:true, areaColor:'rgba(0,120,212,0.15)'}},
];

// Chart 1: 竞价空间 + 电价 (right axis)
function getOptBS(dd) {{
  var d = DATA[dd];
  var s = [{{
    name:'竞价空间', type:'line', data:d['竞价空间'], smooth:true,
    lineStyle:{{width:2.5,color:'#0078d4'}}, itemStyle:{{color:'#0078d4'}}, symbol:'none',
    areaStyle:{{color:new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:'rgba(0,120,212,0.2)'}},{{offset:1,color:'rgba(0,120,212,0)'}}])}}
  }}];
  if (HAS_PRICE && PRICE_DATA[dd]) {{
    s.push({{
      name:PRICE_LABEL, type:'line', data:PRICE_DATA[dd], smooth:true,
      lineStyle:{{width:2,color:'#e67e22'}}, itemStyle:{{color:'#e67e22'}}, symbol:'none',
      yAxisIndex:1
    }});
  }}
  var yAxis = [Object.assign({{type:'value',name:'MW'}},ec)];
  if (HAS_PRICE && PRICE_DATA[dd]) {{
    yAxis.push(Object.assign({{type:'value',name:'元/MWh'}},ec2));
  }}
  var opt = {{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:s.map(function(x){{return x.name;}})}},el),xAxis:Object.assign({{type:'category',data:TIMES,axisLabel:{{interval:7}}}},ec),yAxis:yAxis,series:s}};
  if (legendState.bs) {{ opt.legend.selected = legendState.bs; }}
  return opt;
}}

// Chart 2: all constituents (no price)
function getOptComp(dd) {{
  var d = DATA[dd];
  var s = [];
  ALL_SERIES.forEach(function(ser) {{
    var item = {{
      name:ser.name, type:'line', data:d[ser.key], smooth:true,
      lineStyle:{{width:ser.width,color:ser.color,type:ser.dashed?'dashed':'solid'}},
      itemStyle:{{color:ser.color}}, symbol:'none'
    }};
    if (ser.area) {{
      item.areaStyle = {{color:new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:ser.areaColor}},{{offset:1,color:'rgba(0,0,0,0)'}}])}};
    }}
    s.push(item);
  }});
  var opt = {{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:s.map(function(x){{return x.name;}})}},el),xAxis:Object.assign({{type:'category',data:TIMES,axisLabel:{{interval:7}}}},ec),yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:s}};
  if (legendState.comp) {{ opt.legend.selected = legendState.comp; }}
  return opt;
}}

function renderSummary(dd) {{
  var d = DATA[dd];
  var bs = d['竞价空间'];
  var bsAvg = bs.reduce(function(a,b){{return a+b;}},0)/96;
  var bsMax = Math.max.apply(null, bs);
  var bsMin = Math.min.apply(null, bs);
  var bsTime = TIMES[bs.indexOf(bsMax)];
  var bsMinTime = TIMES[bs.indexOf(bsMin)];
  var html = '';
  html += '<div class="summary-chip"><div class="chip-label">竞价空间均值</div><div class="chip-value" style="color:#0078d4">'+fmt(bsAvg)+'</div><div class="chip-sub">MW</div></div>';
  html += '<div class="summary-chip"><div class="chip-label">竞价空间峰值</div><div class="chip-value" style="color:#0078d4">'+fmt(bsMax)+'</div><div class="chip-sub">'+bsTime+'</div></div>';
  html += '<div class="summary-chip"><div class="chip-label">竞价空间谷值</div><div class="chip-value" style="color:#d83b01">'+fmt(bsMin)+'</div><div class="chip-sub">'+bsMinTime+'</div></div>';
  html += '<div class="summary-chip"><div class="chip-label">峰谷差</div><div class="chip-value" style="color:#0078d4">'+fmt(bsMax-bsMin)+'</div><div class="chip-sub">MW</div></div>';
  var pvAvg = d['光伏总加'].reduce(function(a,b){{return a+b;}},0)/96;
  var wdAvg = d['风电总加'].reduce(function(a,b){{return a+b;}},0)/96;
  var dlAvg = d['直调负荷'].reduce(function(a,b){{return a+b;}},0)/96;
  html += '<div class="summary-chip"><div class="chip-label">新能源渗透率(均值)</div><div class="chip-value">'+((pvAvg+wdAvg)/dlAvg*100).toFixed(1)+'%</div><div class="chip-sub">风电+光伏 / 直调负荷</div></div>';
  document.getElementById('summaryBar').innerHTML = html;
}}

function renderStats(dd) {{
  var d = DATA[dd];
  var h = '<h3>'+dd+' 详细数据</h3>';
  var fields = ['直调负荷','联络线受电','风电总加','光伏总加','核电总加','地方电厂','自备机组','竞价空间'];
  var colors = ['#5470c6','#d83b01','#107c10','#f2a900','#9a60b4','#0078d4','#91cc75','#fa541c'];
  fields.forEach(function(f,i) {{
    var arr = d[f];
    var avg = arr.reduce(function(a,b){{return a+b;}},0)/96;
    var mx = Math.max.apply(null, arr);
    var mn = Math.min.apply(null, arr);
    h += '<div class="stat-row"><span class="label" style="color:'+colors[i]+'">'+f+'</span><span class="val">'+fmt(avg)+' MW</span></div>';
    h += '<div class="stat-row"><span class="label">&nbsp;&nbsp;范围</span><span class="val" style="font-weight:400;font-size:10px">'+fmt(mn)+' ~ '+fmt(mx)+'</span></div>';
  }});
  document.getElementById('statsCard').innerHTML = h;
}}

function renderAll() {{
  var dd = currentDate;
  cBS.setOption(getOptBS(dd), true);
  cComp.setOption(getOptComp(dd), true);
  renderSummary(dd);
  renderStats(dd);
}}

selectDate(currentDate);
window.addEventListener('resize', function(){{cBS.resize();cComp.resize();}});
document.addEventListener('keydown', function(e){{
  var idx = ALL_DATES.indexOf(currentDate);
  if(e.key==='ArrowLeft'&&idx>0) selectDate(ALL_DATES[idx-1]);
  if(e.key==='ArrowRight'&&idx<ALL_DATES.length-1) selectDate(ALL_DATES[idx+1]);
}});
</script>
</body>
</html>'''
    return html


def fetch_both_data(start_date: str, end_date: str) -> dict[str, dict]:
    """Query both forecast and actual tables, return merged {date: {field: {预测/实际: [96]}}}."""
    # Fetch forecast
    fg = fetch_data(start_date, end_date, 'forecast')
    # Fetch actual
    ac = fetch_data(start_date, end_date, 'actual')

    # Merge by common dates
    common_dates = sorted(set(fg.keys()) & set(ac.keys()))
    fields = ['直调负荷', '联络线受电', '风电总加', '光伏总加', '核电总加', '地方电厂', '自备机组', '竞价空间']

    merged = {}
    for d in common_dates:
        merged[d] = {}
        for f in fields:
            merged[d][f] = {
                '预测': fg[d][f],
                '实际': ac[d][f],
            }

    return merged


def _build_compare_html(all_dates: list[str], data: dict, title: str,
                         price_da: dict[str, list[float]] | None = None,
                         price_rt: dict[str, list[float]] | None = None) -> str:
    """Generate comparison HTML: forecast vs actual bidding space."""
    time_labels_json = json.dumps(TIME_LABELS, ensure_ascii=False)
    data_json = json.dumps(data, ensure_ascii=False)
    price_da_json = json.dumps(price_da, ensure_ascii=False) if price_da else 'null'
    price_rt_json = json.dumps(price_rt, ensure_ascii=False) if price_rt else 'null'
    dates_json = json.dumps(all_dates, ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333;min-height:100vh}}
.header{{background:#fff;padding:12px 24px;border-bottom:1px solid #d9d9d9;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600}}
.header .info{{font-size:11px;color:#888}}
.date-tabs{{display:flex;flex-wrap:wrap;gap:3px;max-width:100%;overflow-x:auto}}
.date-tab{{padding:4px 10px;border:1px solid #c8c8c8;border-radius:4px;cursor:pointer;background:#fff;color:#555;font-size:11px;transition:all .15s;white-space:nowrap}}
.date-tab:hover{{background:#e5f3ff;border-color:#0078d4;color:#0078d4}}
.date-tab.active{{background:#0078d4;border-color:#0078d4;color:#fff;font-weight:600}}
.summary-bar{{display:flex;gap:8px;padding:8px 20px;flex-wrap:wrap}}
.summary-chip{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:6px 14px;flex:1;min-width:120px;text-align:center}}
.summary-chip .chip-label{{font-size:10px;color:#888;margin-bottom:2px}}
.summary-chip .chip-value{{font-size:18px;font-weight:700;color:#0078d4}}
.summary-chip .chip-sub{{font-size:10px;color:#999}}
.summary-chip .chip-value.pos{{color:#107c10}}
.summary-chip .chip-value.neg{{color:#d13438}}
.main-grid{{display:grid;grid-template-columns:1fr 300px;gap:0}}
@media(max-width:1100px){{.main-grid{{grid-template-columns:1fr}}}}
.charts-area{{padding:8px;display:flex;flex-direction:column;gap:6px}}
.chart-panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.chart-panel .panel-title{{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.chart-box{{width:100%;height:360px}}
.sidebar{{background:#fff;border-left:1px solid #e0e0e0;padding:12px;overflow-y:auto;display:flex;flex-direction:column;gap:10px;max-height:calc(100vh - 180px)}}
.stats-card{{background:#fff;border:1px solid #e0e0e0;border-radius:6px;padding:12px}}
.stats-card h3{{font-size:13px;color:#0078d4;margin-bottom:8px;border-bottom:1px solid #e8e8e8;padding-bottom:6px}}
.stat-row{{display:flex;justify-content:space-between;padding:3px 0;font-size:11px;border-bottom:1px solid #f3f3f3}}
.stat-row .label{{color:#888}}
.stat-row .val{{font-weight:600;color:#333}}
.stat-row .val.pos{{color:#107c10}}
.stat-row .val.neg{{color:#d13438}}
.deviation-bar{{margin-top:8px;padding:8px;background:#fafafa;border-radius:4px;border:1px solid #eee}}
.deviation-bar h4{{font-size:11px;color:#666;margin-bottom:6px}}
.dev-row{{display:flex;align-items:center;gap:8px;margin-bottom:4px;font-size:10px}}
.dev-row .dev-label{{width:70px;color:#888;flex-shrink:0}}
.dev-row .dev-bar-wrap{{flex:1;height:14px;background:#eee;border-radius:7px;overflow:hidden;position:relative}}
.dev-row .dev-bar{{height:100%;border-radius:7px;transition:width .3s}}
.dev-row .dev-bar.plus{{background:#d13438}}
.dev-row .dev-bar.minus{{background:#107c10}}
.dev-row .dev-val{{width:60px;font-weight:600;font-size:11px;text-align:right;flex-shrink:0}}
.legend-tip{{font-size:10px;color:#999;margin-top:6px;line-height:1.5}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>预测 vs 实际 竞价空间对比</h1>
    <div class="info">数据来源: shandong_px_spot_dayahead_load_info + shandong_px_spot_actual_load_info | 公式: 直调负荷 - 联络线受电 - 风电 - 光伏 - 核电 - 自备 (地方电厂不参与bs)</div>
  </div>
  <div class="date-tabs" id="dateTabs"></div>
</div>
<div class="summary-bar" id="summaryBar"></div>
<div class="main-grid">
  <div class="charts-area">
    <div class="chart-panel">
      <div class="panel-title">竞价空间对比 <span style="font-weight:400;color:#888;font-size:11px">(MW) — 预测 vs 实际</span></div>
      <div class="chart-box" id="chartBS"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">偏差构成分析 <span style="font-weight:400;color:#888;font-size:11px">(MW) — 各分项预测偏差 = 实际 - 预测</span></div>
      <div class="chart-box" id="chartDev"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">各分项对比 <span style="font-weight:400;color:#888;font-size:11px">(MW) — 点击图例切换显示</span></div>
      <div class="chart-box" id="chartComp"></div>
    </div>
  </div>
  <div class="sidebar" id="sidebar">
    <div class="stats-card" id="statsCard"></div>
    <div class="deviation-bar" id="devBar"></div>
    <div class="legend-tip">
      数据来源：<br>
      · 预测: shandong_px_spot_dayahead_load_info<br>
      · 实际: shandong_px_spot_actual_load_info<br>
      · 竞价空间 = 直调负荷 - 联络线 - 风电 - 光伏 - 核电 - 自备<br>
      · 偏差 = 实际值 - 预测值<br>
      · 键盘 ← → 切换日期<br>
      · 图例选择在切换日期后保持不变
    </div>
  </div>
</div>
<div class="footer">润津储能 · 竞价空间分析 · 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>

<script>
var DATA = {data_json};
var PRICE_DA = {price_da_json};
var PRICE_RT = {price_rt_json};
var TIMES = {time_labels_json};
var ALL_DATES = {dates_json};
var currentDate = ALL_DATES[ALL_DATES.length - 1];

// Date tabs
var tabsEl = document.getElementById('dateTabs');
ALL_DATES.forEach(function(d) {{
  var b = document.createElement('div');
  b.className = 'date-tab';
  b.textContent = d.slice(5);
  b.onclick = function() {{ selectDate(d); }};
  tabsEl.appendChild(b);
}});

function selectDate(d) {{
  currentDate = d;
  document.querySelectorAll('.date-tab').forEach(function(t){{t.classList.remove('active');}});
  var idx = ALL_DATES.indexOf(d);
  if(idx>=0) document.querySelectorAll('.date-tab')[idx].classList.add('active');
  renderAll();
}}

var cBS = echarts.init(document.getElementById('chartBS'));
var cDev = echarts.init(document.getElementById('chartDev'));
var cComp = echarts.init(document.getElementById('chartComp'));

var g = {{left:60,right:80,top:20,bottom:35}};
var ec = {{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var ec2 = {{axisLabel:{{color:'#e67e22',fontSize:10}},axisLine:{{lineStyle:{{color:'#e67e22'}}}},splitLine:{{show:false}}}};
var el = {{textStyle:{{color:'#666',fontSize:11}},top:3}};

var legendState = {{}};
cBS.on('legendselectchanged', function(p) {{ legendState.bs = p.selected; }});
cDev.on('legendselectchanged', function(p) {{ legendState.dev = p.selected; }});
cComp.on('legendselectchanged', function(p) {{ legendState.comp = p.selected; }});

function fmt(v){{return v!=null?v.toFixed(0):'—';}}
function fmtSigned(v){{return v!=null?(v>=0?'+':'')+v.toFixed(0):'—';}}

// Chart 1: 竞价空间 预测 vs 实际 + 电价
function getOptBS(dd) {{
  var d = DATA[dd];
  var s = [];
  s.push({{name:'预测竞价空间',type:'line',data:d['竞价空间']['预测'],smooth:true,lineStyle:{{width:2,color:'#0078d4',type:'dashed'}},itemStyle:{{color:'#0078d4'}},symbol:'none'}});
  s.push({{name:'实际竞价空间',type:'line',data:d['竞价空间']['实际'],smooth:true,lineStyle:{{width:2.5,color:'#d13438'}},itemStyle:{{color:'#d13438'}},symbol:'none',areaStyle:{{color:new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:'rgba(209,52,56,0.15)'}},{{offset:1,color:'rgba(209,52,56,0)'}}])}}}});
  if (PRICE_DA && PRICE_DA[dd]) {{
    s.push({{name:'日前电价',type:'line',data:PRICE_DA[dd],smooth:true,lineStyle:{{width:1.5,color:'#0078d4',type:'dotted'}},itemStyle:{{color:'#0078d4'}},symbol:'none',yAxisIndex:1}});
  }}
  if (PRICE_RT && PRICE_RT[dd]) {{
    s.push({{name:'实时电价',type:'line',data:PRICE_RT[dd],smooth:true,lineStyle:{{width:1.5,color:'#d13438',type:'dotted'}},itemStyle:{{color:'#d13438'}},symbol:'none',yAxisIndex:1}});
  }}
  var yAxis = [Object.assign({{type:'value',name:'MW'}},ec)];
  if ((PRICE_DA && PRICE_DA[dd]) || (PRICE_RT && PRICE_RT[dd])) {{
    yAxis.push(Object.assign({{type:'value',name:'元/MWh'}},ec2));
  }}
  var opt = {{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:s.map(function(x){{return x.name;}})}},el),xAxis:Object.assign({{type:'category',data:TIMES,axisLabel:{{interval:7}}}},ec),yAxis:yAxis,series:s}};
  if (legendState.bs) {{ opt.legend.selected = legendState.bs; }}
  return opt;
}}

// Chart 2: 各分项偏差 (实际 - 预测)
function getOptDev(dd) {{
  var d = DATA[dd];
  var fields = ['直调负荷','联络线受电','风电总加','光伏总加','核电总加','地方电厂','自备机组'];
  var colors = ['#5470c6','#d83b01','#107c10','#f2a900','#9a60b4','#0078d4','#91cc75'];
  var s = [];
  fields.forEach(function(f,i) {{
    var dev = [];
    for (var j=0; j<96; j++) dev.push(d[f]['实际'][j] - d[f]['预测'][j]);
    s.push({{name:f+'偏差',type:'line',data:dev,smooth:true,lineStyle:{{width:1.5,color:colors[i]}},itemStyle:{{color:colors[i]}},symbol:'none'}});
  }});
  // Also add 竞价空间偏差 as bold line
  var bsDev = [];
  for (var j=0; j<96; j++) bsDev.push(d['竞价空间']['实际'][j] - d['竞价空间']['预测'][j]);
  s.push({{name:'竞价空间偏差',type:'line',data:bsDev,smooth:true,lineStyle:{{width:2.5,color:'#d13438'}},itemStyle:{{color:'#d13438'}},symbol:'none'}});
  var opt = {{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:s.map(function(x){{return x.name;}})}},el),xAxis:Object.assign({{type:'category',data:TIMES,axisLabel:{{interval:7}}}},ec),yAxis:Object.assign({{type:'value',name:'MW 偏差'}},ec),series:s}};
  if (legendState.dev) {{ opt.legend.selected = legendState.dev; }}
  return opt;
}}

// Chart 3: 各分项 预测 vs 实际
var COMP_PAIRS = [
  {{key:'直调负荷',label:'直调负荷',colorF:'#5470c6',colorA:'#a0b4f0'}},
  {{key:'联络线受电',label:'联络线受电',colorF:'#d83b01',colorA:'#f0a060'}},
  {{key:'风电总加',label:'风电总加',colorF:'#107c10',colorA:'#60d060'}},
  {{key:'光伏总加',label:'光伏总加',colorF:'#f2a900',colorA:'#f0d060'}},
  {{key:'核电总加',label:'核电总加',colorF:'#9a60b4',colorA:'#d0a0f0'}},
  {{key:'地方电厂',label:'地方电厂',colorF:'#0078d4',colorA:'#80b4f0'}},
  {{key:'自备机组',label:'自备机组',colorF:'#91cc75',colorA:'#c0e0a0'}},
];

function getOptComp(dd) {{
  var d = DATA[dd];
  var s = [];
  COMP_PAIRS.forEach(function(p) {{
    s.push({{name:p.label+'(预测)',type:'line',data:d[p.key]['预测'],smooth:true,lineStyle:{{width:1.5,color:p.colorF,type:'dashed'}},itemStyle:{{color:p.colorF}},symbol:'none'}});
    s.push({{name:p.label+'(实际)',type:'line',data:d[p.key]['实际'],smooth:true,lineStyle:{{width:2,color:p.colorA}},itemStyle:{{color:p.colorA}},symbol:'none'}});
  }});
  var opt = {{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:s.map(function(x){{return x.name;}})}},el),xAxis:Object.assign({{type:'category',data:TIMES,axisLabel:{{interval:7}}}},ec),yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:s}};
  if (legendState.comp) {{ opt.legend.selected = legendState.comp; }}
  return opt;
}}

function renderSummary(dd) {{
  var d = DATA[dd];
  var bsF = d['竞价空间']['预测'];
  var bsA = d['竞价空间']['实际'];
  var bsFAvg = bsF.reduce(function(a,b){{return a+b;}},0)/96;
  var bsAAvg = bsA.reduce(function(a,b){{return a+b;}},0)/96;
  var devAvg = bsAAvg - bsFAvg;
  var devCls = devAvg >= 0 ? 'pos' : 'neg';
  var html = '';
  html += '<div class="summary-chip"><div class="chip-label">预测竞价空间均值</div><div class="chip-value" style="color:#0078d4">'+fmt(bsFAvg)+'</div><div class="chip-sub">MW</div></div>';
  html += '<div class="summary-chip"><div class="chip-label">实际竞价空间均值</div><div class="chip-value" style="color:#d13438">'+fmt(bsAAvg)+'</div><div class="chip-sub">MW</div></div>';
  html += '<div class="summary-chip"><div class="chip-label">偏差(实际-预测)</div><div class="chip-value '+devCls+'">'+fmtSigned(devAvg)+'</div><div class="chip-sub">MW</div></div>';
  // RMSE
  var rmseSum = 0;
  for (var j=0; j<96; j++) rmseSum += Math.pow(bsA[j]-bsF[j], 2);
  var rmse = Math.sqrt(rmseSum/96);
  html += '<div class="summary-chip"><div class="chip-label">RMSE</div><div class="chip-value">'+fmt(rmse)+'</div><div class="chip-sub">MW</div></div>';
  document.getElementById('summaryBar').innerHTML = html;
}}

function renderStats(dd) {{
  var d = DATA[dd];
  var h = '<h3>'+dd+' 分项均值对比</h3>';
  var fields = ['直调负荷','联络线受电','风电总加','光伏总加','核电总加','地方电厂','自备机组','竞价空间'];
  var colors = ['#5470c6','#d83b01','#107c10','#f2a900','#9a60b4','#0078d4','#91cc75','#fa541c'];
  fields.forEach(function(f,i) {{
    var fg = d[f]['预测'];
    var ac = d[f]['实际'];
    var fgAvg = fg.reduce(function(a,b){{return a+b;}},0)/96;
    var acAvg = ac.reduce(function(a,b){{return a+b;}},0)/96;
    var dev = acAvg - fgAvg;
    h += '<div class="stat-row"><span class="label" style="color:'+colors[i]+'">'+f+'</span></div>';
    h += '<div class="stat-row"><span class="label">&nbsp;&nbsp;预测</span><span class="val">'+fmt(fgAvg)+' MW</span></div>';
    h += '<div class="stat-row"><span class="label">&nbsp;&nbsp;实际</span><span class="val">'+fmt(acAvg)+' MW</span></div>';
    h += '<div class="stat-row"><span class="label">&nbsp;&nbsp;偏差</span><span class="val '+(dev>=0?'pos':'neg')+'">'+fmtSigned(dev)+' MW</span></div>';
  }});
  document.getElementById('statsCard').innerHTML = h;
}}

// Deviation contribution bar chart
function renderDevBar(dd) {{
  var d = DATA[dd];
  var fields = ['直调负荷','联络线受电','风电总加','光伏总加','核电总加','地方电厂','自备机组'];
  var colors = ['#5470c6','#d83b01','#107c10','#f2a900','#9a60b4'];
  // Compute RMSE per component
  var devs = [];
  fields.forEach(function(f,i) {{
    var fg = d[f]['预测'];
    var ac = d[f]['实际'];
    var devAvg = 0;
    for (var j=0; j<96; j++) devAvg += (ac[j] - fg[j]);
    devAvg /= 96;
    devs.push({{label:f, dev:devAvg, color:colors[i]}});
  }});
  // Find max abs for bar scaling
  var maxAbs = 0;
  devs.forEach(function(x) {{ maxAbs = Math.max(maxAbs, Math.abs(x.dev)); }});
  maxAbs = Math.max(maxAbs, 1);

  var h = '<h4>各分项平均偏差 (实际-预测)</h4>';
  devs.forEach(function(x) {{
    var pct = Math.min(Math.abs(x.dev)/maxAbs*100, 100);
    var dir = x.dev >= 0 ? 'plus' : 'minus';
    h += '<div class="dev-row">';
    h += '<span class="dev-label">'+x.label+'</span>';
    h += '<div class="dev-bar-wrap"><div class="dev-bar '+dir+'" style="width:'+pct+'%;background:'+x.color+'"></div></div>';
    h += '<span class="dev-val" style="color:'+(x.dev>=0?'#d13438':'#107c10')+'">'+fmtSigned(x.dev)+' MW</span>';
    h += '</div>';
  }});
  document.getElementById('devBar').innerHTML = h;
}}

function renderAll() {{
  var dd = currentDate;
  cBS.setOption(getOptBS(dd), true);
  cDev.setOption(getOptDev(dd), true);
  cComp.setOption(getOptComp(dd), true);
  renderSummary(dd);
  renderStats(dd);
  renderDevBar(dd);
}}

selectDate(currentDate);
window.addEventListener('resize', function(){{cBS.resize();cDev.resize();cComp.resize();}});
document.addEventListener('keydown', function(e){{
  var idx = ALL_DATES.indexOf(currentDate);
  if(e.key==='ArrowLeft'&&idx>0) selectDate(ALL_DATES[idx-1]);
  if(e.key==='ArrowRight'&&idx<ALL_DATES.length-1) selectDate(ALL_DATES[idx+1]);
}});
</script>
</body>
</html>'''
    return html


def main(start_date: str = DEFAULT_START, end_date: str = DEFAULT_END, mode: str = 'forecast',
         use_local: bool = False):
    cfg = TABLE_CONFIG[mode]
    # 电价数据来源表
    price_source_table = ('shandong_px_reliable_clearing_unit_data (润津日前可靠性机组组合出清数据)'
                          if mode == 'forecast'
                          else 'shandong_px_realtime_clearing_results_query (润津实时出清结果)')
    if use_local:
        print(f'Querying local SQLite: {mode} {start_date} ~ {end_date}')
        data = fetch_data_local(start_date, end_date, mode)
        price_data = fetch_price_data_local(start_date, end_date, 'dayahead' if mode == 'forecast' else 'realtime')
    else:
        print(f'Querying {cfg["table"]}: {start_date} ~ {end_date}')
        data = fetch_data(start_date, end_date, mode)
        price_type = 'dayahead' if mode == 'forecast' else 'realtime'
        print(f'Querying price: {price_type} ({price_source_table.split(" ")[0]})')
        price_data = fetch_price_data(start_date, end_date, price_type)
    all_dates = sorted(data.keys())

    if not all_dates:
        print('No data found!')
        return

    print(f'Fetched {len(all_dates)} dates: {all_dates[0]} ~ {all_dates[-1]}')

    title = f'{cfg["label"]}竞价空间分析 {all_dates[0]} ~ {all_dates[-1]}'
    price_label = '日前' if mode == 'forecast' else '实时'
    print(f'Price data: {len(price_data)} dates ({price_label}电价)')
    html = _build_html(all_dates, data, title, mode, price_data, price_source_table)

    os.makedirs(OUT_DIR, exist_ok=True)
    fname = f'{cfg["label"]}竞价空间_{all_dates[0]}_{all_dates[-1]}.html'
    out_path = os.path.join(OUT_DIR, fname)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'Saved: {out_path}')
    print(f'Size: {len(html):,} bytes, {len(html.encode("utf-8")):,} bytes (UTF-8)')


def main_compare(start_date: str = DEFAULT_START, end_date: str = DEFAULT_END,
                 use_local: bool = False):
    """Generate comparison HTML: forecast vs actual."""
    actual_end = end_date
    if end_date == '2026-06-22':
        actual_end = '2026-06-20'

    if use_local:
        print(f'Querying local SQLite: forecast + actual {start_date} ~ {actual_end}')
        merged = fetch_both_data_local(start_date, actual_end)
        price_da = fetch_price_data_local(start_date, actual_end, 'dayahead')
        price_rt = fetch_price_data_local(start_date, actual_end, 'realtime')
    else:
        print(f'Querying forecast: shandong_px_spot_dayahead_load_info {start_date} ~ {end_date}')
        print(f'Querying actual:   shandong_px_spot_actual_load_info {start_date} ~ {actual_end}')
        merged = fetch_both_data(start_date, actual_end)
        print('Querying price: dayahead + realtime')
        price_da = fetch_price_data(start_date, actual_end, 'dayahead')
        price_rt = fetch_price_data(start_date, actual_end, 'realtime')
    print(f'Price data: DA={len(price_da)} dates, RT={len(price_rt)} dates')
    all_dates = sorted(merged.keys())

    if not all_dates:
        print('No common dates found!')
        return

    print(f'Fetched {len(all_dates)} common dates: {all_dates[0]} ~ {all_dates[-1]}')

    title = f'预测 vs 实际 竞价空间对比 {all_dates[0]} ~ {all_dates[-1]}'
    html = _build_compare_html(all_dates, merged, title, price_da, price_rt)

    os.makedirs(OUT_DIR, exist_ok=True)
    fname = f'竞价空间对比_{all_dates[0]}_{all_dates[-1]}.html'
    out_path = os.path.join(OUT_DIR, fname)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'Saved: {out_path}')
    print(f'Size: {len(html):,} bytes, {len(html.encode("utf-8")):,} bytes (UTF-8)')


if __name__ == '__main__':
    args = sys.argv[1:]
    mode = 'forecast'
    start = DEFAULT_START
    end = DEFAULT_END
    use_local = False

    if '--local' in args or '-l' in args:
        use_local = True
        args = [a for a in args if a not in ('--local', '-l')]

    if '--compare' in args or '-c' in args:
        mode = 'compare'
        args = [a for a in args if a not in ('--compare', '-c')]
    elif '--actual' in args or '-a' in args:
        mode = 'actual'
        if end == '2026-06-22':
            end = '2026-06-20'
        args = [a for a in args if a not in ('--actual', '-a')]

    if len(args) >= 2:
        start, end = args[0], args[1]

    if mode == 'compare':
        main_compare(start, end, use_local)
    else:
        main(start, end, mode, use_local)