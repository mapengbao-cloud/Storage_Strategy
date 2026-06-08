"""Generate system-level real-time backup capacity analysis HTML."""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, '_tmp_sysbackup_data.json'), 'r', encoding='utf-8') as f:
    raw = json.load(f)

tl = []
for h in range(24):
    for m in [15, 30, 45, 0]:
        if h == 23 and m == 0: continue
        tl.append(f'{h+1:02d}:00' if m == 0 else f'{h:02d}:{m}')

html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>山东实时系统备用容量分析 | 0528-0603</title>
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
.main-grid{display:grid;grid-template-columns:1fr 300px;gap:0}
@media(max-width:1200px){.main-grid{grid-template-columns:1fr}}
.charts-area{padding:10px;display:flex;flex-direction:column;gap:10px}
.chart-panel{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.chart-panel .panel-title{padding:8px 14px;font-size:13px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}
.chart-box{width:100%;height:380px}
.chart-box.short{height:300px}
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
.legend-tip{font-size:10px;color:#999;margin-top:8px;line-height:1.5}
</style>
</head>
<body>
<div class="header">
  <h1>山东实时系统正/负备用容量 — 全省实时调度可调容量</h1>
  <div class="date-tabs" id="dateTabs"></div>
</div>
<div class="summary-bar" id="summaryBar"></div>
<div class="main-grid">
  <div class="charts-area">
    <div class="chart-panel">
      <div class="panel-title">正备用容量（上调空间） <span style="font-weight:400;color:#888;font-size:12px">(MW)</span></div>
      <div class="chart-box" id="chartPos"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">负备用容量（下调空间） <span style="font-weight:400;color:#888;font-size:12px">(MW)</span></div>
      <div class="chart-box" id="chartNeg"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">正/负备用对比 + 调节总量  <span style="font-weight:400;color:#888;font-size:12px">(MW)</span></div>
      <div class="chart-box" id="chartBoth"></div>
    </div>
  </div>
  <div class="sidebar" id="sidebar">
    <div class="stats-card" id="statsCard"></div>
    <div class="legend-tip">
      表名：shandong_px_release_operation_real_time_system_backup<br><br>
      含义：<b>全省实时运行系统备用容量</b><br>
      是全省层面可用的总上调/下调容量，<br>
      由调度中心根据机组出力、备用投运<br>
      状态实时计算发布。<br><br>
      · positive_power = 正备用（上调可用）<br>
      · negative_power = 负备用（下调可用）<br><br>
      与日前备用(断面级)的区别：<br>
      这是实时系统级总量，日前备用是<br>
      按断面/区域申报的96点计划值。<br><br>
      键盘 ← → 切换日期
    </div>
  </div>
</div>
<script>
var DATA = ''' + json.dumps(raw, ensure_ascii=False) + ''';
var TIMES = ''' + json.dumps(tl, ensure_ascii=False) + ''';

var ALL_DATES = Object.keys(DATA).sort();
var currentDate = ALL_DATES[ALL_DATES.length - 1];

var tabsEl = document.getElementById('dateTabs');
ALL_DATES.forEach(function(d) {
  var b = document.createElement('div'); b.className = 'date-tab';
  b.textContent = d.slice(5);
  b.onclick = function() { selectDate(d); };
  tabsEl.appendChild(b);
});

function selectDate(d) {
  currentDate = d;
  document.querySelectorAll('.date-tab').forEach(function(t){t.classList.remove('active');});
  var idx = ALL_DATES.indexOf(d);
  if(idx>=0) document.querySelectorAll('.date-tab')[idx].classList.add('active');
  renderAll();
}

var cP = echarts.init(document.getElementById('chartPos'));
var cN = echarts.init(document.getElementById('chartNeg'));
var cB = echarts.init(document.getElementById('chartBoth'));

var g = {left:50,right:30,top:30,bottom:40};
var ec = {axisLabel:{color:'#888',fontSize:10},axisLine:{lineStyle:{color:'#d0d0d0'}},splitLine:{lineStyle:{color:'#f0f0f0'}}};
var el = {textStyle:{color:'#666'},top:5};

function fmt(v){return v!=null?v.toFixed(0):'—';}

function getOptPos(dd) {
  var d = DATA[dd];
  var s = [{name:'正备用',type:'line',data:d.pos,smooth:true,lineStyle:{width:2.5,color:'#0078d4'},symbol:'none',areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(0,120,212,0.2)'},{offset:1,color:'rgba(0,120,212,0)'}])}}];
  return {grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:['正备用']},el),xAxis:Object.assign({type:'category',data:TIMES,axisLabel:{interval:7}},ec),yAxis:Object.assign({type:'value',name:'MW'},ec),series:s};
}

function getOptNeg(dd) {
  var d = DATA[dd];
  var s = [{name:'负备用',type:'line',data:d.neg,smooth:true,lineStyle:{width:2.5,color:'#d83b01'},symbol:'none',areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(216,59,1,0.2)'},{offset:1,color:'rgba(216,59,1,0)'}])}}];
  return {grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:['负备用']},el),xAxis:Object.assign({type:'category',data:TIMES,axisLabel:{interval:7}},ec),yAxis:Object.assign({type:'value',name:'MW'},ec),series:s};
}

function getOptBoth(dd) {
  var d = DATA[dd];
  var total = d.pos.map(function(v,i){ return v + d.neg[i]; });
  var s = [
    {name:'正备用',type:'line',data:d.pos,smooth:true,lineStyle:{width:2,color:'#0078d4'},symbol:'none'},
    {name:'负备用',type:'line',data:d.neg,smooth:true,lineStyle:{width:2,color:'#d83b01'},symbol:'none'},
    {name:'调节总量(正+负)',type:'line',data:total,smooth:true,lineStyle:{width:2,color:'#881798',type:'dashed'},symbol:'none',areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(136,23,152,0.1)'},{offset:1,color:'rgba(136,23,152,0)'}])}}
  ];
  return {grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:['正备用','负备用','调节总量(正+负)']},el),xAxis:Object.assign({type:'category',data:TIMES,axisLabel:{interval:7}},ec),yAxis:Object.assign({type:'value',name:'MW'},ec),series:s};
}

function renderSummary(dd) {
  var d = DATA[dd];
  var pAvg = d.pos.reduce(function(a,b){return a+b;},0)/96;
  var pMax = Math.max.apply(null,d.pos);
  var pMin = Math.min.apply(null,d.pos);
  var nAvg = d.neg.reduce(function(a,b){return a+b;},0)/96;
  var nMax = Math.max.apply(null,d.neg);
  var nMin = Math.min.apply(null,d.neg);
  var totalAvg = pAvg + nAvg;
  var ratio = (pAvg / (nAvg||1)).toFixed(1);
  document.getElementById('summaryBar').innerHTML =
    '<div class="summary-chip"><div class="chip-label">正备用均值</div><div class="chip-value" style="color:#0078d4">'+fmt(pAvg)+'</div><div class="chip-sub">MW</div></div>' +
    '<div class="summary-chip"><div class="chip-label">正备用范围</div><div class="chip-value" style="color:#0078d4">'+fmt(pMin)+'~'+fmt(pMax)+'</div><div class="chip-sub">MW</div></div>' +
    '<div class="summary-chip"><div class="chip-label">负备用均值</div><div class="chip-value" style="color:#d83b01">'+fmt(nAvg)+'</div><div class="chip-sub">MW</div></div>' +
    '<div class="summary-chip"><div class="chip-label">负备用范围</div><div class="chip-value" style="color:#d83b01">'+fmt(nMin)+'~'+fmt(nMax)+'</div><div class="chip-sub">MW</div></div>' +
    '<div class="summary-chip"><div class="chip-label">调节总量均值</div><div class="chip-value" style="color:#881798">'+fmt(totalAvg)+'</div><div class="chip-sub">MW</div></div>' +
    '<div class="summary-chip"><div class="chip-label">正/负备用倍率</div><div class="chip-value">'+ratio+'x</div><div class="chip-sub">正备用÷负备用</div></div>';
}

function renderStats(dd) {
  var d = DATA[dd];
  var pAvg = d.pos.reduce(function(a,b){return a+b;},0)/96;
  var nAvg = d.neg.reduce(function(a,b){return a+b;},0)/96;
  var pRange = Math.max.apply(null,d.pos)-Math.min.apply(null,d.pos);
  var nRange = Math.max.apply(null,d.neg)-Math.min.apply(null,d.neg);
  var pMaxT = TIMES[d.pos.indexOf(Math.max.apply(null,d.pos))];
  var nMaxT = TIMES[d.neg.indexOf(Math.max.apply(null,d.neg))];
  var pMinT = TIMES[d.pos.indexOf(Math.min.apply(null,d.pos))];
  var nMinT = TIMES[d.neg.indexOf(Math.min.apply(null,d.neg))];
  document.getElementById('statsCard').innerHTML =
    '<h3>'+dd+' 详情</h3>' +
    '<div style="font-size:11px;color:#888;margin-bottom:4px;border-bottom:1px solid #e8e8e8;padding-bottom:3px">正备用</div>' +
    '<div class="stat-row"><span class="label">均值</span><span class="val" style="color:#0078d4">'+fmt(pAvg)+' MW</span></div>' +
    '<div class="stat-row"><span class="label">最大值</span><span class="val">'+fmt(Math.max.apply(null,d.pos))+' MW ('+pMaxT+')</span></div>' +
    '<div class="stat-row"><span class="label">最小值</span><span class="val">'+fmt(Math.min.apply(null,d.pos))+' MW ('+pMinT+')</span></div>' +
    '<div class="stat-row"><span class="label">峰谷差</span><span class="val">'+fmt(pRange)+' MW</span></div>' +
    '<div style="font-size:11px;color:#888;margin:6px 0 4px;border-bottom:1px solid #e8e8e8;padding-bottom:3px">负备用</div>' +
    '<div class="stat-row"><span class="label">均值</span><span class="val" style="color:#d83b01">'+fmt(nAvg)+' MW</span></div>' +
    '<div class="stat-row"><span class="label">最大值</span><span class="val">'+fmt(Math.max.apply(null,d.neg))+' MW ('+nMaxT+')</span></div>' +
    '<div class="stat-row"><span class="label">最小值</span><span class="val">'+fmt(Math.min.apply(null,d.neg))+' MW ('+nMinT+')</span></div>' +
    '<div class="stat-row"><span class="label">峰谷差</span><span class="val">'+fmt(nRange)+' MW</span></div>' +
    '<div style="font-size:11px;color:#888;margin:6px 0 4px;border-bottom:1px solid #e8e8e8;padding-bottom:3px">综合</div>' +
    '<div class="stat-row"><span class="label">正/负比</span><span class="val">'+(pAvg/(nAvg||1)).toFixed(2)+'x</span></div>' +
    '<div class="stat-row"><span class="label">正备⽤率</span><span class="val">'+(pAvg/76000*100).toFixed(1)+'% (vs ~76GW)</span></div>';
}

function renderAll() {
  var dd = currentDate;
  cP.setOption(getOptPos(dd), true);
  cN.setOption(getOptNeg(dd), true);
  cB.setOption(getOptBoth(dd), true);
  renderSummary(dd);
  renderStats(dd);
}

selectDate(currentDate);
window.addEventListener('resize', function(){cP.resize();cN.resize();cB.resize();});
document.addEventListener('keydown', function(e){
  var idx = ALL_DATES.indexOf(currentDate);
  if(e.key==='ArrowLeft'&&idx>0) selectDate(ALL_DATES[idx-1]);
  if(e.key==='ArrowRight'&&idx<ALL_DATES.length-1) selectDate(ALL_DATES[idx+1]);
});
</script>
</body>
</html>'''

out_path = os.path.join(ROOT, '06 DataMining', '系统备用容量分析_0528-0603.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved: {out_path}')
print(f'Size: {len(html):,} bytes')