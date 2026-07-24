"""生成2026年-80地板价日多指标汇总HTML。
逻辑：
  - 地板价(<=-80)时点的 bs/火电/光伏/台数 取 max/min/mean
  - 当天竞价空间、火电出清、开机台数的 2h峰值均值（最高2h窗口，反映日峰值水平）
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
D = json.load(open(ROOT / "_tmp_floor_days.json", encoding="utf-8"))
daily = sorted(D["daily"], key=lambda r: r["date"])

dates = [r["date"] for r in daily]
floor_pts = [int(r["floor_pts"]) for r in daily]
bs_max = [r["bs_max"] for r in daily]
bs_min = [r["bs_min"] for r in daily]
bs_mean = [r["bs_mean"] for r in daily]
bs_peak2h = [r.get("bs_peak2h", 0) for r in daily]
bs_peak_win = [r.get("bs_peak_window", "") for r in daily]
th_max = [r["thermal_max"] for r in daily]
th_min = [r["thermal_min"] for r in daily]
th_mean = [r["thermal_mean"] for r in daily]
th_peak2h = [r.get("thermal_peak2h", 0) for r in daily]
th_peak_win = [r.get("thermal_peak_window", "") for r in daily]
pv_max = [r["pv_max"] for r in daily]
pv_min = [r["pv_min"] for r in daily]
pv_mean = [r["pv_mean"] for r in daily]
u_max = [int(r["units_max"]) for r in daily]
u_min = [int(r["units_min"]) for r in daily]
u_mean = [round(r["units_mean"]) for r in daily]
u_peak2h = [round(r.get("units_peak2h", 0)) for r in daily]
u_peak_win = [r.get("units_peak_window", "") for r in daily]

JS = json.dumps({
    "dates": dates, "floor_pts": floor_pts,
    "bs_max": bs_max, "bs_min": bs_min, "bs_mean": bs_mean, "bs_peak2h": bs_peak2h,
    "th_max": th_max, "th_min": th_min, "th_mean": th_mean, "th_peak2h": th_peak2h,
    "pv_max": pv_max, "pv_min": pv_min, "pv_mean": pv_mean,
    "u_max": u_max, "u_min": u_min, "u_mean": u_mean, "u_peak2h": u_peak2h,
    "n_days": D["n_days"],
}, ensure_ascii=False)

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>2026年-80地板价日多指标汇总</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:"Microsoft YaHei","Segoe UI",sans-serif; background:#fff; color:#333; padding:20px; }
h1 { color:#222; font-size:22px; margin-bottom:6px; }
.subtitle { color:#666; font-size:13px; margin-bottom:18px; line-height:1.6; }
h2 { color:#222; font-size:17px; margin:24px 0 10px; border-left:4px solid #2c7be5; padding-left:10px; }
.desc { color:#666; font-size:12px; margin-bottom:8px; line-height:1.7; }
.chart { width:100%; border:1px solid #ddd; border-radius:6px; background:#fff; }
.note { background:#f6f8fa; border-left:3px solid #2c7be5; padding:10px 14px; font-size:12px; color:#555; margin:10px 0; line-height:1.7; border-radius:0 4px 4px 0; }
.card-row { display:flex; flex-wrap:wrap; gap:12px; margin-bottom:8px; }
.card { background:#fafafa; border:1px solid #e0e0e0; border-radius:6px; padding:14px 18px; min-width:170px; flex:1; }
.card .v { font-size:22px; font-weight:600; color:#2c7be5; }
.card .l { font-size:12px; color:#666; margin-top:4px; }
table { width:100%; border-collapse:collapse; font-size:10.5px; margin-top:8px; }
th, td { border:1px solid #e0e0e0; padding:4px 5px; text-align:center; white-space:nowrap; }
th { background:#f5f5f5; font-weight:600; }
tbody tr:hover { background:#e5f3ff; }
</style>
</head>
<body>

<h1>2026年-80地板价日多指标汇总</h1>
<p class="subtitle">
筛选：2026年日前电价 ≤ -80 元/MWh 的时点（非地板价时点不参与统计），共 __NDAYS__ 天，合计 2504 个地板时点。<br>
<b>统计逻辑：</b>当日地板价时点的 bs/火电/光伏/台数 取 max/min/mean；<b>2h峰值均值</b>取当天最高2h窗口（日峰值水平，反映保供峰值）。
</p>

<div class="card-row">
  <div class="card"><div class="v">__NDAYS__</div><div class="l">地板价日数</div></div>
  <div class="card"><div class="v" style="color:#d13438">__MAX_FLOOR__</div><div class="l">单日最多地板点数</div></div>
  <div class="card"><div class="v" style="color:#52c41a">__MIN_BS__</div><div class="l">地板时点bs最低(MW)</div></div>
  <div class="card"><div class="v">__MIN_TH__</div><div class="l">地板时点火电最低(MW)</div></div>
  <div class="card"><div class="v" style="color:#9a60b4">__MIN_U__</div><div class="l">地板时点最少台数</div></div>
  <div class="card"><div class="v" style="color:#faad14">__MAX_PV__</div><div class="l">地板时点光伏最高(MW)</div></div>
</div>

<h2>一、竞价空间（地板时点 max/min/mean）+ 当天2h峰值</h2>
<p class="desc">柱：地板时点bs均值；线：bs最高/最低（地板时点内）+ 当天2h峰值均值（虚线，日峰值水平）。</p>
<div id="c1" class="chart" style="height:400px"></div>
<div class="note">地板时点bs均值普遍 7-20 GW，最低常跌至负值（光伏淹没）；2h峰值均值 34-51 GW（晚峰保供水平），与地板时点形成日内峰谷反差。</div>

<h2>二、火电出清（地板时点 max/min/mean）+ 当天2h峰值</h2>
<p class="desc">柱：地板时点火电均值；线：火电最高/最低 + 当天2h峰值均值。</p>
<div id="c2" class="chart" style="height:400px"></div>
<div class="note">地板时点火电均值 11-20 GW（接近最小出力），2h峰值均值 20-37 GW（保供时段火电满发），二者差值反映当日火电调峰深度。</div>

<h2>三、光伏（地板时点 max/min/mean）</h2>
<p class="desc">柱：地板时点光伏均值；线：最高/最低。</p>
<div id="c3" class="chart" style="height:380px"></div>
<div class="note">4-7月地板时光伏最高 19-26 GW（午间光伏大发），1月光伏=0（冬季地板由负荷低谷+风电导致，非光伏）。</div>

<h2>四、开机台数（地板时点 max/min/mean）+ 当天2h峰值台数</h2>
<p class="desc">柱：地板时点台数均值；线：台数最高/最低 + 当天2h峰值台数（保供峰值时段）。</p>
<div id="c4" class="chart" style="height:380px"></div>
<div class="note">地板时点台数 67-115台，2h峰值台数 90-126台（保供峰值）。谷段台数与峰值台数差反映当日开停机变化。</div>

<h2>五、2h峰值对比（bs vs 火电 vs 台数）— 日峰值水平</h2>
<p class="desc">三轴：bs2h峰值(MW)、火电2h峰值(MW)、台数2h峰值(台)。反映地板日的日峰值保供水平。</p>
<div id="c5" class="chart" style="height:420px"></div>
<div class="note">bs2h峰值与火电2h峰值高度同步，台数2h峰值随bs峰值上升。地板日即使谷段触-80，日峰值仍需保供（火电满发+多开机）。</div>

<h2>六、明细表（全部地板价日）</h2>
<div style="overflow-x:auto">
<table id="detailTable">
<thead><tr>
<th>日期</th><th>月</th><th>地板点数</th>
<th colspan="3">竞价空间(地板时点)</th><th>bs2h峰值</th>
<th colspan="3">火电出清(地板时点)</th><th>火电2h峰值</th>
<th colspan="2">光伏(地板时点)</th>
<th colspan="3">台数(地板时点)</th><th>台数2h峰值</th>
</tr>
<tr><th colspan="3"></th><th>最高</th><th>最低</th><th>均值</th><th>(日峰值)</th><th>最高</th><th>最低</th><th>均值</th><th>(日峰值)</th><th>最高</th><th>均值</th><th>最高</th><th>最低</th><th>均值</th><th>(日峰值)</th></tr>
</thead>
<tbody id="tbody"></tbody>
</table>
</div>

<script>
var D = __JS__;

echarts.init(document.getElementById('c1')).setOption({
  tooltip: {trigger:'axis'},
  legend: {data:['bs均值(地板)','bs最高(地板)','bs最低(地板)','bs2h峰值(日峰值)'], top:5},
  grid: {left:60, right:70, bottom:60, top:50},
  xAxis: {type:'category', data:D.dates, axisLabel:{rotate:45, fontSize:9}},
  yAxis: [{type:'value', name:'MW'}],
  dataZoom: [{type:'inside'}, {type:'slider', height:18, bottom:5}],
  series: [
    {name:'bs均值(地板)', type:'bar', itemStyle:{color:'#2c7be5'}, data:D.bs_mean},
    {name:'bs最高(地板)', type:'line', symbol:'none', itemStyle:{color:'#d13438'}, lineStyle:{color:'#d13438', width:1.5}, data:D.bs_max},
    {name:'bs最低(地板)', type:'line', symbol:'none', itemStyle:{color:'#52c41a'}, lineStyle:{color:'#52c41a', width:1.5}, data:D.bs_min},
    {name:'bs2h峰值(日峰值)', type:'line', symbol:'none', itemStyle:{color:'#faad14'}, lineStyle:{color:'#faad14', width:2, type:'dashed'}, data:D.bs_peak2h}
  ]
});

echarts.init(document.getElementById('c2')).setOption({
  tooltip: {trigger:'axis'},
  legend: {data:['火电均值(地板)','火电最高(地板)','火电最低(地板)','火电2h峰值(日峰值)'], top:5},
  grid: {left:60, right:70, bottom:60, top:50},
  xAxis: {type:'category', data:D.dates, axisLabel:{rotate:45, fontSize:9}},
  yAxis: {type:'value', name:'MW'},
  dataZoom: [{type:'inside'}, {type:'slider', height:18, bottom:5}],
  series: [
    {name:'火电均值(地板)', type:'bar', itemStyle:{color:'#2c7be5'}, data:D.th_mean},
    {name:'火电最高(地板)', type:'line', symbol:'none', itemStyle:{color:'#d13438'}, lineStyle:{color:'#d13438', width:1.5}, data:D.th_max},
    {name:'火电最低(地板)', type:'line', symbol:'none', itemStyle:{color:'#52c41a'}, lineStyle:{color:'#52c41a', width:1.5}, data:D.th_min},
    {name:'火电2h峰值(日峰值)', type:'line', symbol:'none', itemStyle:{color:'#faad14'}, lineStyle:{color:'#faad14', width:2, type:'dashed'}, data:D.th_peak2h}
  ]
});

echarts.init(document.getElementById('c3')).setOption({
  tooltip: {trigger:'axis'},
  legend: {data:['光伏均值(地板)','光伏最高(地板)','光伏最低(地板)'], top:5},
  grid: {left:60, right:30, bottom:60, top:50},
  xAxis: {type:'category', data:D.dates, axisLabel:{rotate:45, fontSize:9}},
  yAxis: {type:'value', name:'MW'},
  dataZoom: [{type:'inside'}, {type:'slider', height:18, bottom:5}],
  series: [
    {name:'光伏均值(地板)', type:'bar', itemStyle:{color:'#52c41a'}, data:D.pv_mean},
    {name:'光伏最高(地板)', type:'line', symbol:'none', itemStyle:{color:'#faad14'}, lineStyle:{color:'#faad14', width:2}, data:D.pv_max},
    {name:'光伏最低(地板)', type:'line', symbol:'none', itemStyle:{color:'#888'}, lineStyle:{color:'#888', width:1}, data:D.pv_min}
  ]
});

echarts.init(document.getElementById('c4')).setOption({
  tooltip: {trigger:'axis'},
  legend: {data:['台数均值(地板)','台数最高(地板)','台数最低(地板)','台数2h峰值(日峰值)'], top:5},
  grid: {left:60, right:30, bottom:60, top:50},
  xAxis: {type:'category', data:D.dates, axisLabel:{rotate:45, fontSize:9}},
  yAxis: {type:'value', name:'台', min:60},
  dataZoom: [{type:'inside'}, {type:'slider', height:18, bottom:5}],
  series: [
    {name:'台数均值(地板)', type:'bar', itemStyle:{color:'#9a60b4'}, data:D.u_mean},
    {name:'台数最高(地板)', type:'line', symbol:'none', itemStyle:{color:'#d13438'}, lineStyle:{color:'#d13438', width:1.5}, data:D.u_max},
    {name:'台数最低(地板)', type:'line', symbol:'none', itemStyle:{color:'#52c41a'}, lineStyle:{color:'#52c41a', width:1.5}, data:D.u_min},
    {name:'台数2h峰值(日峰值)', type:'line', symbol:'none', itemStyle:{color:'#faad14'}, lineStyle:{color:'#faad14', width:2, type:'dashed'}, data:D.u_peak2h}
  ]
});

echarts.init(document.getElementById('c5')).setOption({
  tooltip: {trigger:'axis'},
  legend: {data:['bs2h峰值(MW)','火电2h峰值(MW)','台数2h峰值'], top:5},
  grid: {left:60, right:80, bottom:60, top:50},
  xAxis: {type:'category', data:D.dates, axisLabel:{rotate:45, fontSize:9}},
  yAxis: [
    {type:'value', name:'bs(MW)', position:'left'},
    {type:'value', name:'火电(MW)', position:'right', splitLine:{show:false}},
    {type:'value', name:'台', position:'right', offset:40, splitLine:{show:false}, min:60}
  ],
  dataZoom: [{type:'inside'}, {type:'slider', height:18, bottom:5}],
  series: [
    {name:'bs2h峰值(MW)', type:'line', symbol:'none', smooth:true, itemStyle:{color:'#2c7be5'}, lineStyle:{color:'#2c7be5', width:2}, data:D.bs_peak2h},
    {name:'火电2h峰值(MW)', type:'line', symbol:'none', smooth:true, yAxisIndex:1, itemStyle:{color:'#d13438'}, lineStyle:{color:'#d13438', width:2}, data:D.th_peak2h},
    {name:'台数2h峰值', type:'line', symbol:'none', smooth:true, yAxisIndex:2, itemStyle:{color:'#9a60b4'}, lineStyle:{color:'#9a60b4', width:2}, data:D.u_peak2h}
  ]
});

var tbody = document.getElementById('tbody');
var html = '';
D.dates.forEach(function(d, i) {
  html += '<tr><td>' + d + '</td><td>' + d.slice(5,7) + '</td><td>' + D.floor_pts[i] + '</td>';
  html += '<td>' + D.bs_max[i] + '</td><td>' + D.bs_min[i] + '</td><td>' + D.bs_mean[i] + '</td><td><b>' + D.bs_peak2h[i] + '</b></td>';
  html += '<td>' + D.th_max[i] + '</td><td>' + D.th_min[i] + '</td><td>' + D.th_mean[i] + '</td><td><b>' + D.th_peak2h[i] + '</b></td>';
  html += '<td>' + D.pv_max[i] + '</td><td>' + D.pv_mean[i] + '</td>';
  html += '<td>' + D.u_max[i] + '</td><td>' + D.u_min[i] + '</td><td>' + D.u_mean[i] + '</td><td><b>' + D.u_peak2h[i] + '</b></td></tr>';
});
tbody.innerHTML = html;

window.addEventListener('resize', function(){
  ['c1','c2','c3','c4','c5'].forEach(function(id){
    var inst = echarts.getInstanceByDom(document.getElementById(id));
    if(inst) inst.resize();
  });
});
</script>
</body>
</html>
"""

min_bs = min(x for x in bs_min if x is not None)
min_th = min(x for x in th_min if x is not None)
min_u = min(u_min)
max_floor = max(floor_pts)
max_pv = max(pv_max)

HTML = HTML.replace("__NDAYS__", str(D["n_days"]))
HTML = HTML.replace("__MAX_FLOOR__", str(max_floor))
HTML = HTML.replace("__MIN_BS__", str(int(min_bs)))
HTML = HTML.replace("__MIN_TH__", str(int(min_th)))
HTML = HTML.replace("__MIN_U__", str(min_u))
HTML = HTML.replace("__MAX_PV__", str(int(max_pv)))
HTML = HTML.replace("__JS__", JS)

out_dir = ROOT / "output" / "竞价空间分析结果"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "地板价日多指标汇总.html"
out_path.write_text(HTML, encoding="utf-8")
print(f"Saved: {out_path} ({out_path.stat().st_size} bytes)")
