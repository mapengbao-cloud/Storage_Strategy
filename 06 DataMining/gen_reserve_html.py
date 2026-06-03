"""Generate reserve capacity analysis HTML for recent week.

===== 日期修改指引 =====
日期范围不在本脚本中控制，而是在**数据提取 SQL 查询**中指定。
搜索 `# DATE_RANGE:` 可找到需要修改的 2 处（标题 + 输出文件名）。
数据提取 SQL 的日期条件：WHERE date >= 'YYYY-MM-DD' AND date <= 'YYYY-MM-DD'
修改后重新执行数据提取流程即可。
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# _tmp_reserve_data.json 由外部数据提取流程生成，包含按日期分组的 96 点备用容量数组
with open(os.path.join(ROOT, '_tmp_reserve_data.json'), 'r', encoding='utf-8') as f:
    raw_data = json.load(f)

time_labels = []
for h in range(24):
    for m in [15, 30, 45, 0]:
        if h == 23 and m == 0: continue
        time_labels.append(f'{h+1:02d}:00' if m == 0 else f'{h:02d}:{m}')

html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>山东日前备用容量分析 | 0521-0527</title>  <!-- DATE_RANGE: 修改标题日期 -->
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
.sidebar{background:#fff;border-left:1px solid #e0e0e0;padding:14px;overflow-y:auto;display:flex;flex-direction:column;gap:12px}
.stats-card{background:#fff;border:1px solid #e0e0e0;border-radius:6px;padding:14px}
.stats-card h3{font-size:14px;color:#0078d4;margin-bottom:10px;border-bottom:1px solid #e8e8e8;padding-bottom:7px}
.stat-row{display:flex;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px solid #f3f3f3}
.stat-row .label{color:#888}
.stat-row .val{font-weight:600;color:#333}
.stat-row .val.up{color:#107c10}
.stat-row .val.down{color:#d13438}
.legend-tip{font-size:10px;color:#999;margin-top:8px;line-height:1.5}
.summary-bar{display:flex;gap:10px;padding:8px 10px;flex-wrap:wrap}
.summary-chip{background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:8px 12px;flex:1;min-width:140px;text-align:center}
.summary-chip .chip-label{font-size:10px;color:#888;margin-bottom:2px}
.summary-chip .chip-value{font-size:18px;font-weight:700;color:#0078d4}
.summary-chip .chip-sub{font-size:10px;color:#999}
</style>
</head>
<body>
<div class="header">
  <h1>山东日前备用容量分析 — 正备用 & 负备用</h1>
  <div class="date-tabs" id="dateTabs"></div>
</div>
<div class="summary-bar" id="summaryBar"></div>
<div class="main-grid">
  <div class="charts-area">
    <div class="chart-panel">
      <div class="panel-title">正备用容量 — 日前计划 vs 实际执行 <span style="font-weight:400;color:#888;font-size:12px">(MW)</span></div>
      <div class="chart-box" id="chartPos"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">负备用容量 — 日前计划 vs 实际执行 <span style="font-weight:400;color:#888;font-size:12px">(MW)</span></div>
      <div class="chart-box" id="chartNeg"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">正负备用对比（实际执行） <span style="font-weight:400;color:#888;font-size:12px">(MW)</span></div>
      <div class="chart-box" id="chartBoth"></div>
    </div>
  </div>
  <div class="sidebar" id="sidebar">
    <div class="stats-card" id="statsCard"></div>
    <div class="legend-tip">
      数据来源：<br>
      · 日前备用：shandong_px_spot_dayahead_reserve_capacity_info<br>
      · 实际备用：shandong_px_spot_actual_reserve_capacity_info<br>
      · 正备用 = 上调备用容量<br>
      · 负备用 = 下调备用容量<br>
      · 键盘 ← → 切换日期
    </div>
  </div>
</div>
<script>
var DATA = ''' + json.dumps(raw_data, ensure_ascii=False) + ''';
var TIMES = ''' + json.dumps(time_labels, ensure_ascii=False) + ''';

var ALL_DATES = Object.keys(DATA).sort();
var currentDate = ALL_DATES[ALL_DATES.length - 1];

var tabsEl = document.getElementById('dateTabs');
ALL_DATES.forEach(function(d) {
  var b = document.createElement('div');
  b.className = 'date-tab';
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
  var s = [];
  s.push({name:'正备用(日前计划)',type:'line',data:d.da_pos,smooth:true,lineStyle:{width:2,color:'#0078d4',type:'dashed'},symbol:'none'});
  if(d.act_pos.length) s.push({name:'正备用(实际)',type:'line',data:d.act_pos,smooth:true,lineStyle:{width:2.5,color:'#0078d4'},symbol:'none',areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(0,120,212,0.15)'},{offset:1,color:'rgba(0,120,212,0)'}])}});
  return {grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:s.map(function(x){return x.name;})},el),xAxis:Object.assign({type:'category',data:TIMES,axisLabel:{interval:7}},ec),yAxis:Object.assign({type:'value',name:'MW'},ec),series:s};
}

function getOptNeg(dd) {
  var d = DATA[dd];
  var s = [];
  s.push({name:'负备用(日前计划)',type:'line',data:d.da_neg,smooth:true,lineStyle:{width:2,color:'#d83b01',type:'dashed'},symbol:'none'});
  if(d.act_neg.length) s.push({name:'负备用(实际)',type:'line',data:d.act_neg,smooth:true,lineStyle:{width:2.5,color:'#d83b01'},symbol:'none',areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(216,59,1,0.15)'},{offset:1,color:'rgba(216,59,1,0)'}])}});
  return {grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:s.map(function(x){return x.name;})},el),xAxis:Object.assign({type:'category',data:TIMES,axisLabel:{interval:7}},ec),yAxis:Object.assign({type:'value',name:'MW'},ec),series:s};
}

function getOptBoth(dd) {
  var d = DATA[dd];
  var s = [];
  if(d.act_pos.length) s.push({name:'正备用(实际)',type:'line',data:d.act_pos,smooth:true,lineStyle:{width:2,color:'#0078d4'},symbol:'none'});
  if(d.act_neg.length) s.push({name:'负备用(实际)',type:'line',data:d.act_neg,smooth:true,lineStyle:{width:2,color:'#d83b01'},symbol:'none'});
  return {grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:s.map(function(x){return x.name;})},el),xAxis:Object.assign({type:'category',data:TIMES,axisLabel:{interval:7}},ec),yAxis:Object.assign({type:'value',name:'MW'},ec),series:s};
}

function renderSummary(dd) {
  var d = DATA[dd];
  var html = '';
  if(d.act_pos.length) {
    var posAvg = d.act_pos.reduce(function(a,b){return a+b;},0)/96;
    var posMax = Math.max.apply(null,d.act_pos);
    var posMin = Math.min.apply(null,d.act_pos);
    html += '<div class="summary-chip"><div class="chip-label">正备用(实际)均值</div><div class="chip-value" style="color:#0078d4">'+fmt(posAvg)+'</div><div class="chip-sub">MW</div></div>';
    html += '<div class="summary-chip"><div class="chip-label">正备用(实际)范围</div><div class="chip-value" style="color:#0078d4">'+fmt(posMin)+'~'+fmt(posMax)+'</div><div class="chip-sub">MW</div></div>';
  }
  if(d.act_neg.length) {
    var negAvg = d.act_neg.reduce(function(a,b){return a+b;},0)/96;
    var negMax = Math.max.apply(null,d.act_neg);
    var negMin = Math.min.apply(null,d.act_neg);
    html += '<div class="summary-chip"><div class="chip-label">负备用(实际)均值</div><div class="chip-value" style="color:#d83b01">'+fmt(negAvg)+'</div><div class="chip-sub">MW</div></div>';
    html += '<div class="summary-chip"><div class="chip-label">负备用(实际)范围</div><div class="chip-value" style="color:#d83b01">'+fmt(negMin)+'~'+fmt(negMax)+'</div><div class="chip-sub">MW</div></div>';
  }
  // 备用率: 正备用/竞价空间 max
  if(d.act_pos.length) {
    var rate = (d.act_pos.reduce(function(a,b){return a+b;},0)/96 / 45000 * 100).toFixed(1);
    html += '<div class="summary-chip"><div class="chip-label">正备用率(估算)</div><div class="chip-value">'+rate+'%</div><div class="chip-sub">vs ~45000MW 最大负荷</div></div>';
  }
  document.getElementById('summaryBar').innerHTML = html;
}

function renderStats(dd) {
  var d = DATA[dd];
  var h = '<h3>'+dd+' 备用详情</h3>';
  // 日前计划
  h += '<div class="stat-row"><span class="label">正备用(日前计划)</span><span class="val">'+fmt(d.da_pos[0])+' MW (恒定)</span></div>';
  h += '<div class="stat-row"><span class="label">负备用(日前计划)</span><span class="val">'+fmt(d.da_neg[0])+' MW (恒定)</span></div>';
  if(d.act_pos.length) {
    var pa = d.act_pos.reduce(function(a,b){return a+b;},0)/96;
    var na = d.act_neg.reduce(function(a,b){return a+b;},0)/96;
    h += '<div style="margin-top:8px;font-size:11px;color:#888;border-bottom:1px solid #e8e8e8;padding-bottom:3px">实际执行</div>';
    h += '<div class="stat-row"><span class="label">正备用(实际均值)</span><span class="val up">'+fmt(pa)+' MW</span></div>';
    h += '<div class="stat-row"><span class="label">负备用(实际均值)</span><span class="val up">'+fmt(na)+' MW</span></div>';
    // 正备用占比
    h += '<div class="stat-row"><span class="label">正/负备用倍率</span><span class="val">'+(pa/(na||1)).toFixed(1)+'x</span></div>';
    // 峰谷差
    var prange = Math.max.apply(null,d.act_pos)-Math.min.apply(null,d.act_pos);
    var nrange = Math.max.apply(null,d.act_neg)-Math.min.apply(null,d.act_neg);
    h += '<div class="stat-row"><span class="label">正备用峰谷差</span><span class="val">'+fmt(prange)+' MW</span></div>';
    h += '<div class="stat-row"><span class="label">负备用峰谷差</span><span class="val">'+fmt(nrange)+' MW</span></div>';
  } else {
    h += '<div style="margin-top:8px;font-size:11px;color:#d83b01">实际数据尚未入库</div>';
  }
  document.getElementById('statsCard').innerHTML = h;
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

out_path = os.path.join(ROOT, '06 DataMining', '日前备用容量分析_0521-0527.html')  # DATE_RANGE: 修改文件名日期
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved: {out_path}')
print(f'Size: {len(html):,} bytes')