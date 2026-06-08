"""Generate power flow section utilization analysis HTML."""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, '_tmp_powerflow_data.json'), 'r', encoding='utf-8') as f:
    pf = json.load(f)

# Color scale for utilization
def util_color(u):
    if u >= 95: return '#d13438'  # red - congestion
    if u >= 80: return '#ff8c00'  # orange - heavy
    if u >= 60: return '#f2c811'  # yellow - moderate
    return '#107c10'  # green - normal

sections_sorted = sorted(pf['sections'], key=lambda s: s['max_util'], reverse=True)

html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>山东电网潮流断面分析 | ''' + pf['date'] + '''</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Microsoft YaHei','Segoe UI',sans-serif;background:#f3f3f3;color:#333;min-height:100vh}
.header{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9;display:flex;justify-content:space-between;align-items:center;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.header h1{font-size:20px;color:#0078d4;font-weight:600}
.header .sub{font-size:13px;color:#888;margin-left:12px}
.overview-bar{display:flex;gap:12px;padding:12px 16px;flex-wrap:wrap}
.overview-chip{background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:10px 16px;text-align:center;min-width:120px}
.overview-chip .chip-label{font-size:10px;color:#888;margin-bottom:3px}
.overview-chip .chip-value{font-size:20px;font-weight:700}
.main-grid{display:grid;grid-template-columns:1fr 320px;gap:0}
@media(max-width:1200px){.main-grid{grid-template-columns:1fr}}
.charts-area{padding:10px;display:flex;flex-direction:column;gap:10px}
.chart-panel{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.chart-panel .panel-title{padding:8px 14px;font-size:13px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}
.chart-box{width:100%;height:420px}
.chart-box.tall{height:550px}
.sidebar{background:#fff;border-left:1px solid #e0e0e0;padding:14px;overflow-y:auto;display:flex;flex-direction:column;gap:10px}
.section-list{max-height:420px;overflow-y:auto}
.section-item{padding:7px 10px;border-bottom:1px solid #f3f3f3;cursor:pointer;transition:background .15s;display:flex;justify-content:space-between;align-items:center;font-size:12px}
.section-item:hover{background:#e5f3ff}
.section-item.active{background:#deecf9;border-left:3px solid #0078d4;padding-left:7px}
.section-item .sname{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-right:8px}
.section-item .sutil{font-weight:700;font-size:13px;white-space:nowrap}
.stats-card{background:#fff;border:1px solid #e0e0e0;border-radius:6px;padding:14px}
.stats-card h3{font-size:14px;color:#0078d4;margin-bottom:10px;border-bottom:1px solid #e8e8e8;padding-bottom:7px}
.stat-row{display:flex;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px solid #f3f3f3}
.stat-row .label{color:#888}
.stat-row .val{font-weight:600;color:#333}
.legend-tip{font-size:10px;color:#999;margin-top:8px;line-height:1.5}
.util-bar{display:inline-block;height:6px;border-radius:3px;margin-right:4px;vertical-align:middle}
</style>
</head>
<body>
<div class="header">
  <div><h1>山东电网潮流断面分析<span class="sub">''' + pf['date'] + ''' | 96时段</span></h1></div>
  <div style="font-size:12px;color:#888">数据来源：shandong_px_operation_actual_power_flow</div>
</div>
<div class="overview-bar" id="overviewBar"></div>
<div class="main-grid">
  <div class="charts-area">
    <div class="chart-panel">
      <div class="panel-title">断面利用率热力图 <span style="font-weight:400;color:#888;font-size:12px">(横轴=时段, 纵轴=断面, 颜色=利用率%)</span></div>
      <div class="chart-box tall" id="chartHeat"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">选定断面详情 — 实际潮流 & 限额 <span style="font-weight:400;color:#888;font-size:12px">(MW)</span></div>
      <div class="chart-box" id="chartDetail"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">重载断面对比（利用率 > 80%） <span style="font-weight:400;color:#888;font-size:12px">(%)</span></div>
      <div class="chart-box" id="chartHeavy"></div>
    </div>
  </div>
  <div class="sidebar">
    <div class="stats-card"><h3>断面列表（按最大利用率排序）</h3></div>
    <div class="section-list" id="sectionList"></div>
    <div class="stats-card" id="detailCard"><h3>点击断面查看详情</h3></div>
    <div class="legend-tip">
      颜色含义：<br>
      <span style="color:#d13438">■</span> 重载(≥95%) &nbsp;
      <span style="color:#ff8c00">■</span> 偏重(80-95%)<br>
      <span style="color:#f2c811">■</span> 中等(60-80%) &nbsp;
      <span style="color:#107c10">■</span> 正常(<60%)<br><br>
      数据来源：shandong_px_operation_actual_power_flow<br>
      利用率为 actual_power / limit_power × 100%
    </div>
  </div>
</div>
<script>
var SECTIONS = ''' + json.dumps(sections_sorted, ensure_ascii=False) + ''';
var TIMES = ''' + json.dumps(pf['timeLabels'], ensure_ascii=False) + ''';
var DATE = "''' + pf['date'] + '''";

var currentSection = SECTIONS[0];

// Overview stats
(function(){
  var total = SECTIONS.length;
  var heavy = SECTIONS.filter(function(s){return s.max_util>=95;}).length;
  var moderate = SECTIONS.filter(function(s){return s.max_util>=80 && s.max_util<95;}).length;
  var avgMax = (SECTIONS.reduce(function(a,b){return a+b.max_util;},0)/total).toFixed(1);
  var maxU = SECTIONS[0];
  document.getElementById('overviewBar').innerHTML =
    '<div class="overview-chip"><div class="chip-label">断面总数</div><div class="chip-value" style="color:#0078d4">'+total+'</div></div>' +
    '<div class="overview-chip"><div class="chip-label">重载断面(≥95%)</div><div class="chip-value" style="color:#d13438">'+heavy+'</div></div>' +
    '<div class="overview-chip"><div class="chip-label">偏重断面(80-95%)</div><div class="chip-value" style="color:#ff8c00">'+moderate+'</div></div>' +
    '<div class="overview-chip"><div class="chip-label">平均最大利用率</div><div class="chip-value" style="color:#333">'+avgMax+'%</div></div>' +
    '<div class="overview-chip"><div class="chip-label">最高利用率断面</div><div class="chip-value" style="color:#d13438;font-size:14px">'+maxU.name.slice(0,20)+'...<br>'+maxU.max_util.toFixed(1)+'%</div></div>';
})();

// Build section list
var listEl = document.getElementById('sectionList');
SECTIONS.forEach(function(s, i){
  var div = document.createElement('div');
  div.className = 'section-item' + (i===0?' active':'');
  var u = s.max_util;
  var c = u>=95?'#d13438':(u>=80?'#ff8c00':(u>=60?'#f2c811':'#107c10'));
  div.innerHTML = '<span class="sname" title="'+s.name+'">'+(i+1)+'. '+s.name+'</span><span class="sutil" style="color:'+c+'">'+u.toFixed(1)+'%</span>';
  div.onclick = function(){ selectSection(i); };
  listEl.appendChild(div);
});

function selectSection(i){
  currentSection = SECTIONS[i];
  document.querySelectorAll('.section-item').forEach(function(el,j){ el.classList.toggle('active', j===i); });
  renderDetail();
  renderDetailCard();
}

function utilColor(u){
  if(u>=95) return '#d13438';
  if(u>=80) return '#ff8c00';
  if(u>=60) return '#f2c811';
  return '#107c10';
}

// Heatmap
var cHeat = echarts.init(document.getElementById('chartHeat'));
var heatData = [];
SECTIONS.forEach(function(s, si){
  for(var ti=0; ti<96; ti++){
    var a = s.actual[ti] || 0;
    var l = s.limit[ti] || 1;
    var u = Math.min(a/l*100, 150);
    heatData.push([ti, si, u]);
  }
});

cHeat.setOption({
  grid:{left:180,right:30,top:10,bottom:40},
  tooltip:{trigger:'item',formatter:function(p){
    var s = SECTIONS[p.value[1]];
    var rate = p.value[2].toFixed(1);
    return s.name+'<br/>时段'+TIMES[p.value[0]]+'<br/>利用率: '+rate+'%<br/>实际: '+s.actual[p.value[0]]+'MW / 限额: '+s.limit[p.value[0]]+'MW';
  }},
  xAxis:{type:'category',data:TIMES,axisLabel:{color:'#888',fontSize:9,interval:7},axisLine:{lineStyle:{color:'#d0d0d0'}},splitLine:{show:false}},
  yAxis:{type:'category',data:SECTIONS.map(function(s){return s.name;}),axisLabel:{color:'#555',fontSize:10,width:170,overflow:'truncate'},axisLine:{lineStyle:{color:'#d0d0d0'}},inverse:true},
  visualMap:{min:0,max:100,calculable:true,orient:'vertical',right:10,top:40,inRange:{color:['#107c10','#f2c811','#ff8c00','#d13438']},text:['高','低'],textStyle:{color:'#888'}},
  series:[{type:'heatmap',data:heatData,label:{show:false},emphasis:{itemStyle:{shadowBlur:10,shadowColor:'rgba(0,0,0,.3)'}}}]
});

// Detail chart
var cDetail = echarts.init(document.getElementById('chartDetail'));
var g = {left:50,right:30,top:30,bottom:40};
var ec = {axisLabel:{color:'#888',fontSize:10},axisLine:{lineStyle:{color:'#d0d0d0'}},splitLine:{lineStyle:{color:'#f0f0f0'}}};
var el = {textStyle:{color:'#666'},top:5};

function renderDetail(){
  var s = currentSection;
  cDetail.setOption({
    grid:g, tooltip:{trigger:'axis'},
    legend:Object.assign({data:['实际潮流','断面限额','利用率']}, el),
    xAxis:Object.assign({type:'category',data:TIMES,axisLabel:{interval:7}}, ec),
    yAxis:[
      Object.assign({type:'value',name:'MW'}, ec),
      Object.assign({type:'value',name:'%',max:120}, ec)
    ],
    series:[
      {name:'实际潮流',type:'line',data:s.actual,smooth:true,lineStyle:{width:2,color:'#0078d4'},symbol:'none'},
      {name:'断面限额',type:'line',data:s.limit,smooth:false,lineStyle:{width:2,color:'#d13438',type:'dashed'},symbol:'none'},
      {name:'利用率',type:'line',yAxisIndex:1,data:s.actual.map(function(a,i){return a/Math.max(s.limit[i],1)*100;}),smooth:true,lineStyle:{width:1.5,color:'#ff8c00'},symbol:'none',areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(255,140,0,0.25)'},{offset:1,color:'rgba(255,140,0,0)'}])}}
    ]
  }, true);
}

// Heavy sections comparison
var cHeavy = echarts.init(document.getElementById('chartHeavy'));
var heavySects = SECTIONS.filter(function(s){return s.max_util>=80;});
cHeavy.setOption({
  grid:{left:160,right:30,top:30,bottom:40},
  tooltip:{trigger:'axis',formatter:function(ps){
    var out = ps[0].axisValue+'<br/>';
    ps.forEach(function(p){ out += p.marker+p.seriesName+': '+p.value.toFixed(1)+'%<br/>'; });
    return out;
  }},
  legend:Object.assign({data:heavySects.map(function(s){return s.name;}),type:'scroll',width:'80%'}, el),
  xAxis:Object.assign({type:'category',data:TIMES,axisLabel:{interval:7}}, ec),
  yAxis:Object.assign({type:'value',name:'利用率 %',axisLabel:{formatter:'{value}%'}}, ec),
  series:heavySects.map(function(s){
    var uData = s.actual.map(function(a,i){return a/Math.max(s.limit[i],1)*100;});
    return {name:s.name,type:'line',data:uData,smooth:true,symbol:'none',lineStyle:{width:1.5}};
  })
});

// Detail card
function renderDetailCard(){
  var s = currentSection;
  var peakIdx = 0;
  var peakU = 0;
  s.actual.forEach(function(a,i){ var u=a/Math.max(s.limit[i],1)*100; if(u>peakU){peakU=u;peakIdx=i;} });
  document.getElementById('detailCard').innerHTML =
    '<h3>'+s.name+'</h3>' +
    '<div class="stat-row"><span class="label">最大利用率</span><span class="val" style="color:'+utilColor(s.max_util)+'">'+s.max_util.toFixed(1)+'%</span></div>' +
    '<div class="stat-row"><span class="label">平均利用率</span><span class="val">'+s.avg_util.toFixed(1)+'%</span></div>' +
    '<div class="stat-row"><span class="label">断面限额</span><span class="val">'+s.max_limit+' MW</span></div>' +
    '<div class="stat-row"><span class="label">峰值时段</span><span class="val">'+TIMES[peakIdx]+'</span></div>' +
    '<div class="stat-row"><span class="label">峰值潮流</span><span class="val">'+s.actual[peakIdx]+' MW</span></div>' +
    '<div class="stat-row"><span class="label">峰值利用率</span><span class="val" style="color:'+utilColor(peakU)+'">'+peakU.toFixed(1)+'%</span></div>';
}

renderDetail();
renderDetailCard();

window.addEventListener('resize', function(){cHeat.resize();cDetail.resize();cHeavy.resize();});
</script>
</body>
</html>'''

out_path = os.path.join(ROOT, '06 DataMining', '山东潮流断面分析_2026-03-10.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved: {out_path}')
print(f'Size: {len(html):,} bytes')