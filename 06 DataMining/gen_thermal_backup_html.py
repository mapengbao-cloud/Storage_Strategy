"""Generate thermal backup comparison analysis HTML.
Compares system-level pos/neg backup capacity with thermal fleet adjustable range.
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, '_tmp_thermal_data.json'), 'r', encoding='utf-8') as f:
    d = json.load(f)

rt_gen = d['rt_gen']; rt_stat = d['rt_stat']; da_stat = d['da_stat']

# Build comparison data per date
dates = sorted(rt_gen.keys())

# Time labels
tl_96 = []; tl_24 = []
for h in range(24):
    for m in [15, 30, 45, 0]:
        if h == 23 and m == 0: continue
        tl_96.append(f'{h+1:02d}:00' if m == 0 else f'{h:02d}:{m}')
for h in range(24): tl_24.append(f'{h:02d}:15')

# Recompute with all data needed
from collections import defaultdict
comp = {}
for dt in dates:
    gen = rt_gen[dt]
    stat = rt_stat.get(dt, {})
    da_s = da_stat.get(dt, {})

    thermal = gen.get('火电', [0]*24)
    t_max = max(thermal); t_min = min(thermal); t_avg = sum(thermal)/24
    t_range = t_max - t_min

    # Total gen
    total = [0.0]*24
    for typ in ['火电','核电','水电','风电','光伏','抽水蓄能']:
        for i, v in enumerate(gen.get(typ, [])):
            if i < 24: total[i] += v
    g_max = max(total); g_min = min(total)

    comp[dt] = {
        'date': dt,
        'thermal_hourly': [round(v, 1) for v in thermal],
        'thermal_max': round(t_max, 1),
        'thermal_min': round(t_min, 1),
        'thermal_avg': round(t_avg, 1),
        'thermal_range': round(t_range, 1),
        'total_gen_hourly': [round(v, 1) for v in total],
        'total_gen_max': round(g_max, 1),
        'total_gen_min': round(g_min, 1),
        'stat_thermal_stations': stat.get('火电站', 0),
        'stat_total_stations': stat.get('总成交', 0),
        'stat_thermal_avg_price': stat.get('火电加权均价', 0),
        'stat_total_avg_price': stat.get('总加权均价', 0),
        'stat_clearing_qty': stat.get('成交电量', 0),
        'da_thermal_stations': da_s.get('火电站', 0),
        'da_total_stations': da_s.get('总成交', 0),
    }

tl = tl_24
html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>火电调节能力 vs 系统备用对比分析 | 0528-0603</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Microsoft YaHei','Segoe UI',sans-serif;background:#f3f3f3;color:#333;min-height:100vh}
.header{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.header h1{font-size:20px;color:#0078d4;font-weight:600}
.date-tabs{display:flex;flex-wrap:wrap;gap:4px}
.date-tab{padding:5px 12px;border:1px solid #c8c8c8;border-radius:4px;cursor:pointer;background:#fff;color:#555;font-size:12px;transition:all .15s;white-space:nowrap}
.date-tab:hover{background:#e5f3ff;border-color:#0078d4;color:#0078d4}
.date-tab.active{background:#0078d4;border-color:#0078d4;color:#fff;font-weight:600}
.main-grid{display:grid;grid-template-columns:1fr 320px;gap:0}
@media(max-width:1200px){.main-grid{grid-template-columns:1fr}}
.charts-area{padding:10px;display:flex;flex-direction:column;gap:10px}
.chart-panel{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.chart-panel .panel-title{padding:8px 14px;font-size:13px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}
.chart-box{width:100%;height:380px}
.sidebar{background:#fff;border-left:1px solid #e0e0e0;padding:14px;overflow-y:auto;display:flex;flex-direction:column;gap:12px}
.summary-bar{display:flex;gap:10px;padding:8px 10px;flex-wrap:wrap}
.summary-chip{background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:8px 12px;flex:1;min-width:140px;text-align:center}
.summary-chip .chip-label{font-size:10px;color:#888;margin-bottom:2px}
.summary-chip .chip-value{font-size:18px;font-weight:700}
.summary-chip .chip-sub{font-size:10px;color:#999}
.stats-card{background:#fff;border:1px solid #e0e0e0;border-radius:6px;padding:14px}
.stats-card h3{font-size:14px;color:#0078d4;margin-bottom:10px;border-bottom:1px solid #e8e8e8;padding-bottom:7px}
.stat-row{display:flex;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px solid #f3f3f3}
.stat-row .label{color:#888}
.stat-row .val{font-weight:600;color:#333}
.insight-box{background:#fdf8e7;border:1px solid #e8d585;border-radius:6px;padding:12px;font-size:12px;line-height:1.6;color:#665500}
.insight-box b{color:#333}
.legend-tip{font-size:10px;color:#999;margin-top:8px;line-height:1.5}
</style>
</head>
<body>
<div class="header">
  <h1>火电调节能力 vs 系统备用对比分析</h1>
  <div class="date-tabs" id="dateTabs"></div>
</div>
<div class="summary-bar" id="summaryBar"></div>
<div class="main-grid">
  <div class="charts-area">
    <div class="chart-panel">
      <div class="panel-title">火电出力曲线 & 可调范围 vs 系统正/负备用 <span style="font-weight:400;color:#888;font-size:12px">(MW, 24点/小时)</span></div>
      <div class="chart-box" id="chartThermal"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">火电可调范围 vs 系统备用总量对比（柱状图） <span style="font-weight:400;color:#888;font-size:12px">(MW)</span></div>
      <div class="chart-box" id="chartCompare"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">每日各电源类型出力堆叠图 <span style="font-weight:400;color:#888;font-size:12px">(MW, 24点)</span></div>
      <div class="chart-box" id="chartStack"></div>
    </div>
  </div>
  <div class="sidebar" id="sidebar">
    <div class="stats-card" id="statsCard"></div>
    <div class="insight-box" id="insightBox"></div>
    <div class="legend-tip">
      数据来源：<br>
      · shandong_px_spot_surveillance_realtime_generation_quantity<br>
      · shandong_px_spot_surveillance_realtime_generation_statistics<br><br>
      火电可调范围 = max(火电出力) - min(火电出力)<br>
      系统备用总量 = 正备用 + 负备用(total)<br><br>
      注意：<br>
      · 24点数据为小时级，96点为正/负备用<br>
      · 火电最小出力受限于最低技术出力<br>
      · 系统备用含储能/抽蓄/联络线贡献
    </div>
  </div>
</div>
<script>
var COMP = ''' + json.dumps(comp, ensure_ascii=False) + ''';
var TIMES_24 = ''' + json.dumps(tl, ensure_ascii=False) + ''';

var ALL_DATES = Object.keys(COMP).sort();
var currentDate = ALL_DATES[ALL_DATES.length - 1];

var tabsEl = document.getElementById('dateTabs');
ALL_DATES.forEach(function(dt) {
  var b = document.createElement('div'); b.className = 'date-tab';
  b.textContent = dt.slice(5);
  b.onclick = function() { selectDate(dt); };
  tabsEl.appendChild(b);
});

function selectDate(dt) {
  currentDate = dt;
  document.querySelectorAll('.date-tab').forEach(function(t){t.classList.remove('active');});
  var idx = ALL_DATES.indexOf(dt);
  if(idx>=0) document.querySelectorAll('.date-tab')[idx].classList.add('active');
  renderAll();
}

var cT = echarts.init(document.getElementById('chartThermal'));
var cC = echarts.init(document.getElementById('chartCompare'));
var cS = echarts.init(document.getElementById('chartStack'));

var g = {left:55,right:30,top:30,bottom:40};
var ec = {axisLabel:{color:'#888',fontSize:10},axisLine:{lineStyle:{color:'#d0d0d0'}},splitLine:{lineStyle:{color:'#f0f0f0'}}};
var el = {textStyle:{color:'#666'},top:5};
function fmt(v){return v!=null?v.toFixed(0):'—';}

function getOptThermal(dt) {
  var d = COMP[dt];
  var series = [
    {name:'火电出力',type:'line',data:d.thermal_hourly,smooth:true,lineStyle:{width:2.5,color:'#0078d4'},symbol:'circle',symbolSize:4,areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(0,120,212,0.2)'},{offset:1,color:'rgba(0,120,212,0.02)'}])}},
    {name:'火电上限(max)',type:'line',data:Array(24).fill(d.thermal_max),lineStyle:{width:1.5,color:'#0078d4',type:'dotted'},symbol:'none',itemStyle:{color:'#0078d4'}},
    {name:'火电下限(min)',type:'line',data:Array(24).fill(d.thermal_min),lineStyle:{width:1.5,color:'#0078d4',type:'dotted'},symbol:'none',itemStyle:{color:'#0078d4'}},
    {name:'总出力',type:'line',data:d.total_gen_hourly,smooth:true,lineStyle:{width:2,color:'#881798',type:'dashed'},symbol:'none'}
  ];
  return {grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:series.map(function(s){return s.name;})},el),xAxis:Object.assign({type:'category',data:TIMES_24},ec),yAxis:Object.assign({type:'value',name:'MW'},ec),series:series};
}

// Weekly comparison chart - bar chart
function getOptCompare() {
  var dates = ALL_DATES;
  var thermalRange = dates.map(function(dt){return COMP[dt].thermal_range;});
  var thermalMax = dates.map(function(dt){return COMP[dt].thermal_max;});
  var thermalMin = dates.map(function(dt){return COMP[dt].thermal_min;});
  var labels = dates.map(function(dt){return dt.slice(5);});

  return {
    grid:{left:60,right:30,top:40,bottom:50},
    tooltip:{trigger:'axis',formatter:function(ps){
      var out = ps[0].name+'<br/>';
      ps.forEach(function(p){out+=p.marker+p.seriesName+': '+fmt(p.value)+' MW<br/>';});
      return out;
    }},
    legend:Object.assign({data:['火电可调范围','火电出力上限','火电出力下限'],top:5},el),
    xAxis:{type:'category',data:labels,axisLabel:{color:'#888',fontSize:11},axisLine:{lineStyle:{color:'#d0d0d0'}}},
    yAxis:{type:'value',name:'MW',axisLabel:{color:'#888'},splitLine:{lineStyle:{color:'#f0f0f0'}}},
    series:[
      {name:'火电可调范围',type:'bar',data:thermalRange,itemStyle:{color:'#0078d4'},barWidth:20,label:{show:true,position:'top',color:'#0078d4',fontSize:10,formatter:'{c}'}},
      {name:'火电出力上限',type:'bar',data:thermalMax,itemStyle:{color:'rgba(0,120,212,0.15)',borderColor:'#0078d4',borderWidth:1},barWidth:20,barGap:'-100%',z:0},
      {name:'火电出力下限',type:'bar',data:thermalMin,itemStyle:{color:'rgba(0,120,212,0.3)',borderColor:'#0078d4',borderWidth:1},barWidth:20,barGap:'-100%',z:1}
    ]
  };
}

// Stacked generation by type
function getOptStack(dt) {
  var d = COMP[dt];
  // We need to rebuild from original data
  return {
    grid:{left:55,right:30,top:30,bottom:40},
    tooltip:{trigger:'axis'},
    legend:{data:['火电','核电','水电','风电','光伏'],textStyle:{color:'#666'},top:5},
    xAxis:{type:'category',data:TIMES_24,axisLabel:{color:'#888',fontSize:10},axisLine:{lineStyle:{color:'#d0d0d0'}}},
    yAxis:{type:'value',name:'MW',axisLabel:{color:'#888'},splitLine:{lineStyle:{color:'#f0f0f0'}}},
    series:[
      {name:'火电',type:'bar',stack:'total',data:thermal_data,itemStyle:{color:'#0078d4'},barWidth:16},
      {name:'核电',type:'bar',stack:'total',data:nuclear_data,itemStyle:{color:'#d83b01'}},
      {name:'水电',type:'bar',stack:'total',data:hydro_data,itemStyle:{color:'#107c10'}},
      {name:'风电',type:'bar',stack:'total',data:wind_data,itemStyle:{color:'#498205'}},
      {name:'光伏',type:'bar',stack:'total',data:solar_data,itemStyle:{color:'#f2c811'}}
    ]
  };
}

function renderSummary(dt) {
  var d = COMP[dt];
  var tRange = d.thermal_range;
  var tPct = (tRange / Math.max(d.thermal_max,1) * 100).toFixed(1);
  var totRange = d.total_gen_max - d.total_gen_min;
  var ratio = (tRange / Math.max(totRange,1) * 100).toFixed(1);
  document.getElementById('summaryBar').innerHTML =
    '<div class="summary-chip"><div class="chip-label">火电出力上限</div><div class="chip-value" style="color:#0078d4">'+fmt(d.thermal_max)+'</div><div class="chip-sub">MW</div></div>' +
    '<div class="summary-chip"><div class="chip-label">火电出力下限</div><div class="chip-value" style="color:#0078d4">'+fmt(d.thermal_min)+'</div><div class="chip-sub">MW</div></div>' +
    '<div class="summary-chip"><div class="chip-label">火电可调范围</div><div class="chip-value" style="color:#0078d4">'+fmt(tRange)+'</div><div class="chip-sub">占上限 '+tPct+'%</div></div>' +
    '<div class="summary-chip"><div class="chip-label">全网出力范围</div><div class="chip-value" style="color:#881798">'+fmt(totRange)+'</div><div class="chip-sub">火电贡献 '+ratio+'%</div></div>' +
    '<div class="summary-chip"><div class="chip-label">火电站数(实时)</div><div class="chip-value">'+fmt(d.stat_thermal_stations)+'</div><div class="chip-sub">座</div></div>' +
    '<div class="summary-chip"><div class="chip-label">火电站数(日前)</div><div class="chip-value">'+fmt(d.da_thermal_stations)+'</div><div class="chip-sub">座</div></div>';
}

function renderStats(dt) {
  var d = COMP[dt];
  document.getElementById('statsCard').innerHTML =
    '<h3>'+dt+' 详情</h3>' +
    '<div class="stat-row"><span class="label">火电出力均值</span><span class="val">'+fmt(d.thermal_avg)+' MW</span></div>' +
    '<div class="stat-row"><span class="label">火电最大出力</span><span class="val" style="color:#0078d4">'+fmt(d.thermal_max)+' MW</span></div>' +
    '<div class="stat-row"><span class="label">火电最小出力</span><span class="val" style="color:#d83b01">'+fmt(d.thermal_min)+' MW</span></div>' +
    '<div class="stat-row"><span class="label">火电日内峰谷差</span><span class="val">'+fmt(d.thermal_range)+' MW</span></div>' +
    '<div class="stat-row"><span class="label">全网最大出力</span><span class="val">'+fmt(d.total_gen_max)+' MW</span></div>' +
    '<div class="stat-row"><span class="label">全网最小出力</span><span class="val">'+fmt(d.total_gen_min)+' MW</span></div>' +
    '<div class="stat-row"><span class="label">火电占全网可调比</span><span class="val">'+(d.thermal_range/Math.max(d.total_gen_max-d.total_gen_min,1)*100).toFixed(1)+'%</span></div>' +
    '<div class="stat-row"><span class="label">火电加权均价</span><span class="val">'+fmt(d.stat_thermal_avg_price)+' 元/MWh</span></div>' +
    '<div class="stat-row"><span class="label">总加权均价</span><span class="val">'+fmt(d.stat_total_avg_price)+' 元/MWh</span></div>';
}

function renderInsight(dt) {
  var d = COMP[dt];
  var tRange = d.thermal_range;
  var totRange = d.total_gen_max - d.total_gen_min;
  var thermalShare = (tRange / Math.max(totRange,1) * 100).toFixed(0);
  var depth = (d.thermal_min / Math.max(d.thermal_max,1) * 100).toFixed(0);
  document.getElementById('insightBox').innerHTML =
    '<b>'+dt.slice(5)+' 关键洞察</b><br><br>' +
    '· 火电日内出力范围 '+fmt(d.thermal_min)+' ~ '+fmt(d.thermal_max)+' MW<br>' +
    '· 火电提供全网 <b>'+thermalShare+'%</b> 的出力调节能力<br>' +
    '· 火电最低出力占上限 <b>'+depth+'%</b>（调峰深度）<br>' +
    '· 实时 '+fmt(d.stat_thermal_stations)+' 座火电站运行<br>' +
    '· 火电加权均价 '+fmt(d.stat_thermal_avg_price)+' 元/MWh<br><br>' +
    '<span style="font-size:11px;color:#887700">结论：系统备用(正+负)不等同于火电可调范围。火电是主要灵活资源，但储能、抽蓄、联络线调整也贡献可观的系统备用容量。</span>';
}

// We need the original rt_gen data for stacked chart
var RT_GEN = ''' + json.dumps({dt: rt_gen[dt] for dt in dates}, ensure_ascii=False) + ''';

function renderAll() {
  var dt = currentDate;

  cT.setOption(getOptThermal(dt), true);
  cC.setOption(getOptCompare(), true);

  // Stacked chart uses RT_GEN
  var gen = RT_GEN[dt] || {};
  var thermal = gen['火电'] || [];
  var nuclear = gen['核电'] || [];
  var hydro_raw = gen['水电'] || [];
  var hydro = hydro_raw.map(function(v){return Math.max(v,0);});
  var wind = gen['风电'] || [];
  var solar = gen['光伏'] || [];

  cS.setOption({
    grid:{left:55,right:30,top:30,bottom:40},
    tooltip:{trigger:'axis'},
    legend:{data:['火电','核电','水电','风电','光伏'],textStyle:{color:'#666'},top:5},
    xAxis:{type:'category',data:TIMES_24,axisLabel:{color:'#888',fontSize:10},axisLine:{lineStyle:{color:'#d0d0d0'}}},
    yAxis:{type:'value',name:'MW',axisLabel:{color:'#888'},splitLine:{lineStyle:{color:'#f0f0f0'}}},
    series:[
      {name:'火电',type:'bar',stack:'total',data:thermal,itemStyle:{color:'#0078d4'},barWidth:16,emphasis:{focus:'series'}},
      {name:'核电',type:'bar',stack:'total',data:nuclear,itemStyle:{color:'#d83b01'},emphasis:{focus:'series'}},
      {name:'水电',type:'bar',stack:'total',data:hydro,itemStyle:{color:'#107c10'},emphasis:{focus:'series'}},
      {name:'风电',type:'bar',stack:'total',data:wind,itemStyle:{color:'#498205'},emphasis:{focus:'series'}},
      {name:'光伏',type:'bar',stack:'total',data:solar,itemStyle:{color:'#f2c811'},emphasis:{focus:'series'}}
    ]
  }, true);

  renderSummary(dt);
  renderStats(dt);
  renderInsight(dt);
}

selectDate(currentDate);
window.addEventListener('resize', function(){cT.resize();cC.resize();cS.resize();});
document.addEventListener('keydown', function(e){
  var idx = ALL_DATES.indexOf(currentDate);
  if(e.key==='ArrowLeft'&&idx>0) selectDate(ALL_DATES[idx-1]);
  if(e.key==='ArrowRight'&&idx<ALL_DATES.length-1) selectDate(ALL_DATES[idx+1]);
});
</script>
</body>
</html>'''

out_path = os.path.join(ROOT, '06 DataMining', '火电调节能力vs系统备用对比_0528-0603.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved: {out_path}')
print(f'Size: {len(html):,} bytes')