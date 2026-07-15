"""Generate 直调负荷 & 光伏 预测vs实际 comparison HTML for 0628-0707."""
import json, os, pymysql
from datetime import datetime

DATES = ['2026-06-28','2026-06-29','2026-06-30','2026-07-01','2026-07-02','2026-07-03','2026-07-04','2026-07-05','2026-07-06','2026-07-07']
TIMES = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0,15,30,45)]
COLORS10 = ['#0078d4','#d13438','#107c10','#f2a900','#9a60b4','#5470c6','#d83b01','#73c0de','#fc8452','#3ba272']

conn = pymysql.connect(host='rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com', port=3306,
    user='pengyiqiang', password='pengyiqiang123', database='tianrun_new',
    charset='utf8mb4', connect_timeout=10, read_timeout=30)
cur = conn.cursor()

fc_dl, fc_pv = {}, {}
ac_dl, ac_pv = {}, {}

for d in DATES:
    cur.execute('SELECT dispatched_load_forecast, photovoltaic_power_forecast FROM shandong_px_spot_dayahead_load_info WHERE date=%s ORDER BY time_order', (d,))
    rows = cur.fetchall()
    fc_dl[d] = [float(r[0]) for r in rows]
    fc_pv[d] = [float(r[1]) for r in rows]

    cur.execute('SELECT actual_dispatched_load, actual_photovoltaic_power FROM shandong_px_spot_actual_load_info WHERE date=%s ORDER BY time_order', (d,))
    rows = cur.fetchall()
    ac_dl[d] = [float(r[0]) for r in rows]
    ac_pv[d] = [float(r[1]) for r in rows]

cur.close(); conn.close()

LABELS = [d[5:] for d in DATES]

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>直调负荷 & 光伏出力 预测vs实际 | 0628-0707</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}}
.header{{background:#fff;padding:12px 24px;border-bottom:1px solid #d9d9d9;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600;margin-bottom:4px}}
.header .info{{font-size:11px;color:#888}}
.date-bar{{background:#fff;padding:10px 24px;border-bottom:1px solid #e0e0e0;display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.date-bar .label{{font-size:12px;color:#666;font-weight:600}}
.date-chip{{padding:5px 14px;border:1px solid #c8c8c8;border-radius:4px;cursor:pointer;font-size:12px;background:#fff;user-select:none;transition:all .15s}}
.date-chip:hover{{border-color:#0078d4}}
.date-chip.active{{background:#0078d4;color:#fff;border-color:#0078d4}}
.date-bar .actions{{display:flex;gap:6px;margin-left:8px}}
.date-bar .actions button{{padding:4px 10px;border:1px solid #c8c8c8;border-radius:4px;cursor:pointer;font-size:11px;background:#fff}}
.date-bar .actions button:hover{{background:#f0f0f0}}
.stats{{display:flex;gap:8px;padding:8px 24px;flex-wrap:wrap}}
.stat{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:10px 14px;min-width:140px;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.stat .l{{font-size:10px;color:#888}}
.stat .v{{font-size:18px;font-weight:600;color:#2c7be5}}
.stat .s{{font-size:10px;color:#aaa}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:8px 24px}}
@media(max-width:1000px){{.charts{{grid-template-columns:1fr}}}}
.panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.panel .t{{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.panel .c{{width:100%;height:420px}}
.panel.full{{grid-column:1/-1}}
.panel.full .c{{height:400px}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
</style>
</head>
<body>
<div class="header">
<h1>直调负荷 & 光伏出力 预测 vs 实际 | 0628 ~ 0707</h1>
<div class="info">数据来源：天机库 shandong_px_spot_dayahead_load_info（预测） + shandong_px_spot_actual_load_info（实际）· MW · 点击日期切换</div>
</div>
<div class="date-bar">
<span class="label">选择日期：</span>
<div id="dateChips"></div>
<div class="actions">
<button onclick="selectAll()">全选</button>
<button onclick="clearAll()">清除</button>
</div>
</div>
<div class="stats" id="statsBar"></div>
<div class="charts">
<div class="panel"><div class="t">直调负荷 预测 vs 实际（MW）<span style="font-weight:400;color:#888;font-size:11px"> — 实线=预测，虚线=实际</span></div><div class="c" id="c1"></div></div>
<div class="panel"><div class="t">光伏出力 预测 vs 实际（MW）<span style="font-weight:400;color:#888;font-size:11px"> — 实线=预测，虚线=实际</span></div><div class="c" id="c2"></div></div>
<div class="panel full"><div class="t">直调负荷偏差（实际 - 预测，MW）<span style="font-weight:400;color:#888;font-size:11px"> — 正值=实际>预测</span></div><div class="c" id="c3"></div></div>
<div class="panel full"><div class="t">光伏出力偏差（实际 - 预测，MW）</div><div class="c" id="c4"></div></div>
</div>
<div class="footer">润津储能 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<script>
var T={json.dumps(TIMES, ensure_ascii=False)};
var DATES={json.dumps(DATES, ensure_ascii=False)};
var LABELS={json.dumps(LABELS, ensure_ascii=False)};
var FC_DL={json.dumps(fc_dl)};
var AC_DL={json.dumps(ac_dl)};
var FC_PV={json.dumps(fc_pv)};
var AC_PV={json.dumps(ac_pv)};
var COLORS={json.dumps(COLORS10)};

var g={{left:55,right:60,top:20,bottom:35}};
var ec={{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var el={{textStyle:{{color:'#666',fontSize:10}},top:3}};
var xA=Object.assign({{type:'category',data:T,axisLabel:{{interval:7}}}},ec);

var selected = DATES.slice();  // default: all selected

function renderChips() {{
  var html = '';
  DATES.forEach(function(d, i) {{
    var active = selected.indexOf(d) >= 0 ? ' active' : '';
    html += '<span class="date-chip' + active + '" data-date="' + d + '" onclick="toggleDate(this)">' + LABELS[i] + '</span>';
  }});
  document.getElementById('dateChips').innerHTML = html;
}}

function toggleDate(el) {{
  var d = el.dataset.date;
  var idx = selected.indexOf(d);
  if (idx >= 0) {{
    selected.splice(idx, 1);
    el.classList.remove('active');
  }} else {{
    selected.push(d);
    el.classList.add('active');
  }}
  // Sort selected by original order
  selected.sort(function(a,b){{return DATES.indexOf(a)-DATES.indexOf(b);}});
  refreshAll();
}}

function selectAll() {{
  selected = DATES.slice();
  document.querySelectorAll('.date-chip').forEach(function(c){{c.classList.add('active');}});
  refreshAll();
}}

function clearAll() {{
  selected = [];
  document.querySelectorAll('.date-chip').forEach(function(c){{c.classList.remove('active');}});
  refreshAll();
}}

function refreshAll() {{
  renderCharts();
  renderStats();
}}

function renderStats() {{
  if (selected.length === 0) {{
    document.getElementById('statsBar').innerHTML = '<div class="stat"><div class="l">提示</div><div class="v">请选择日期</div></div>';
    return;
  }}
  var fcDl=[], acDl=[], fcPv=[], acPv=[];
  selected.forEach(function(d) {{
    fcDl = fcDl.concat(FC_DL[d]);
    acDl = acDl.concat(AC_DL[d]);
    fcPv = fcPv.concat(FC_PV[d]);
    acPv = acPv.concat(AC_PV[d]);
  }});
  var afd = fcDl.reduce(function(a,b){{return a+b;}},0)/fcDl.length;
  var aad = acDl.reduce(function(a,b){{return a+b;}},0)/acDl.length;
  var afp = fcPv.reduce(function(a,b){{return a+b;}},0)/fcPv.length;
  var aap = acPv.reduce(function(a,b){{return a+b;}},0)/acPv.length;
  var s = '';
  s += '<div class="stat"><div class="l">选中日期</div><div class="v">' + selected.length + ' 天</div><div class="s">' + selected.map(function(d){{return d.slice(5);}}).join(', ') + '</div></div>';
  s += '<div class="stat"><div class="l">直调负荷预测均值</div><div class="v">' + afd.toFixed(0) + ' MW</div></div>';
  s += '<div class="stat"><div class="l">直调负荷实际均值</div><div class="v">' + aad.toFixed(0) + ' MW</div><div class="s">偏差 ' + (aad-afd).toFixed(0) + ' MW</div></div>';
  s += '<div class="stat"><div class="l">光伏预测均值</div><div class="v">' + afp.toFixed(0) + ' MW</div></div>';
  s += '<div class="stat"><div class="l">光伏实际均值</div><div class="v">' + aap.toFixed(0) + ' MW</div><div class="s">偏差 ' + (aap-afp).toFixed(0) + ' MW</div></div>';
  document.getElementById('statsBar').innerHTML = s;
}}

function renderCharts() {{
  var dlSeries = [], pvSeries = [], dlDevSeries = [], pvDevSeries = [];
  var legendDl = [], legendPv = [], legendDev = [];
  selected.forEach(function(d, idx) {{
    var c = COLORS[idx % COLORS.length];
    var lb = d.slice(5);
    dlSeries.push({{name:lb+' 预测',type:'line',data:FC_DL[d],smooth:true,lineStyle:{{width:2,color:c}},itemStyle:{{color:c}},symbol:'none'}});
    dlSeries.push({{name:lb+' 实际',type:'line',data:AC_DL[d],smooth:true,lineStyle:{{width:2,color:c,type:'dashed'}},itemStyle:{{color:c}},symbol:'none'}});
    pvSeries.push({{name:lb+' 预测',type:'line',data:FC_PV[d],smooth:true,lineStyle:{{width:2,color:c}},itemStyle:{{color:c}},symbol:'none'}});
    pvSeries.push({{name:lb+' 实际',type:'line',data:AC_PV[d],smooth:true,lineStyle:{{width:2,color:c,type:'dashed'}},itemStyle:{{color:c}},symbol:'none'}});
    var devDL = AC_DL[d].map(function(v,i){{return v-FC_DL[d][i];}});
    var devPV = AC_PV[d].map(function(v,i){{return v-FC_PV[d][i];}});
    dlDevSeries.push({{name:lb,type:'line',data:devDL,smooth:true,lineStyle:{{width:1.5,color:c}},itemStyle:{{color:c}},symbol:'none'}});
    pvDevSeries.push({{name:lb,type:'line',data:devPV,smooth:true,lineStyle:{{width:1.5,color:c}},itemStyle:{{color:c}},symbol:'none'}});
    legendDl.push(lb+' 预测', lb+' 实际');
    legendPv.push(lb+' 预测', lb+' 实际');
    legendDev.push(lb);
  }});

  var emptyOption = {{grid:g,xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:[]}};

  c1.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:legendDl,type:'scroll',bottom:0}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:dlSeries}}, true);
  c2.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:legendPv,type:'scroll',bottom:0}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:pvSeries}}, true);
  c3.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:legendDev,type:'scroll',bottom:0}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:dlDevSeries}}, true);
  c4.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:legendDev,type:'scroll',bottom:0}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:pvDevSeries}}, true);
}}

var c1=echarts.init(document.getElementById('c1'));
var c2=echarts.init(document.getElementById('c2'));
var c3=echarts.init(document.getElementById('c3'));
var c4=echarts.init(document.getElementById('c4'));

renderChips();
refreshAll();

window.addEventListener('resize',function(){{c1.resize();c2.resize();c3.resize();c4.resize();}});
</script>
</body>
</html>'''

OUT = 'E:/DataWork/Storage_Strategy/output/直调负荷_光伏_预测vs实际_0628-0707.html'
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved: {OUT} ({os.path.getsize(OUT):,} bytes)')