"""Generate comprehensive bidding space + price + weather analysis HTML.

===== 日期修改指引 =====
本脚本从 _tmp_html_data.json 读取数据，日期范围由数据文件内容决定。
需要修改的地方（2 处）均以 `# DATE_RANGE:` 标注，搜索此标记即可定位：
  1. HTML <title> 中的日期范围文本（搜索 `DATE_RANGE:`）
  2. 输出文件名中的日期范围（搜索 `DATE_RANGE:`）
每次更新数据后，将 _tmp_html_data.json 放在项目根目录运行本脚本即可。
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

# _tmp_html_data.json 由外部数据提取流程生成，包含 'data'/'weather'/'timeLabels' 三个字段
# 生成方式：按需运行项目根目录的数据提取命令（读取竞价空间/日前复盘/实时复盘 + Open-Meteo 天气 API）
with open(os.path.join(ROOT, '_tmp_html_data.json'), 'r', encoding='utf-8') as f:
    all_data = json.load(f)

html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>竞价空间 & 电价 & 天气综合分析 | 2026年7月</title>  <!-- DATE_RANGE: 修改这里和下面文件名中的日期范围 -->
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Microsoft YaHei','Segoe UI','PingFang SC',sans-serif;background:#f3f3f3;color:#333;min-height:100vh}
.header{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.header h1{font-size:20px;color:#0078d4;font-weight:600}
.date-tabs{display:flex;flex-wrap:wrap;gap:4px}
.date-tab{padding:5px 12px;border:1px solid #c8c8c8;border-radius:4px;cursor:pointer;background:#fff;color:#555;font-size:12px;transition:all .15s;white-space:nowrap}
.date-tab:hover{background:#e5f3ff;border-color:#0078d4;color:#0078d4}
.date-tab.active{background:#0078d4;border-color:#0078d4;color:#fff;font-weight:600}
.main-grid{display:grid;grid-template-columns:1fr 300px;gap:0;min-height:calc(100vh - 60px)}
@media(max-width:1200px){.main-grid{grid-template-columns:1fr}}
.charts-area{padding:10px;display:flex;flex-direction:column;gap:10px}
.chart-panel{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.chart-panel .panel-title{padding:8px 14px;font-size:13px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}
.chart-box{width:100%;height:380px}
.chart-box.short{height:300px}
.sidebar{background:#fff;border-left:1px solid #e0e0e0;padding:14px;overflow-y:auto;display:flex;flex-direction:column;gap:12px}
.weather-card{background:linear-gradient(180deg,#e8f4fd,#fff);border:1px solid #bcd4e8;border-radius:6px;padding:14px}
.weather-card h3{font-size:14px;color:#0078d4;margin-bottom:10px;border-bottom:1px solid #d0e4f2;padding-bottom:7px}
.weather-main{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.weather-icon{font-size:36px}
.weather-desc{font-size:16px;font-weight:600;color:#333}
.weather-temp{font-size:26px;font-weight:700;color:#d83b01}
.weather-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.weather-item{background:#f7f9fa;border:1px solid #e8e8e8;border-radius:4px;padding:6px 8px}
.weather-item .label{font-size:10px;color:#888;margin-bottom:2px}
.weather-item .value{font-size:13px;font-weight:600;color:#333}
.weather-item .value.highlight{color:#d83b01}
.weather-item .value.green{color:#107c10}
.weather-item .value.blue{color:#0078d4}
.weather-item .value.red{color:#d13438}
.stats-card{background:#fff;border:1px solid #e0e0e0;border-radius:6px;padding:14px}
.stats-card h3{font-size:14px;color:#0078d4;margin-bottom:10px;border-bottom:1px solid #e8e8e8;padding-bottom:7px}
.stat-row{display:flex;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px solid #f3f3f3}
.stat-row .label{color:#888}
.stat-row .val{font-weight:600;color:#333}
.stat-row .val.up{color:#107c10}
.stat-row .val.down{color:#d13438}
.stat-row .val.warn{color:#d83b01}
.legend-tip{font-size:10px;color:#999;margin-top:8px;line-height:1.5}
</style>
</head>
<body>
<div class="header">
  <h1>竞价空间 & 电价 & 天气综合分析</h1>
  <div class="date-tabs" id="dateTabs"></div>
</div>
<div class="main-grid">
  <div class="charts-area">
    <div class="chart-panel">
      <div class="panel-title">竞价空间对比 — 预测 vs 实际 <span style="font-weight:400;color:#78909c;font-size:12px">(MW)</span></div>
      <div class="chart-box" id="chartBS"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">日前电价 & 实时电价 & 充放电功率(日前计划+实时实际) <span style="font-weight:400;color:#78909c;font-size:12px">(元/MWh · MW)</span></div>
      <div class="chart-box" id="chartPrice"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">风电 / 光伏 — 预测 vs 实际 <span style="font-weight:400;color:#78909c;font-size:12px">(MW)</span></div>
      <div class="chart-box short" id="chartRE"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">直调负荷 & 联络线受电 — 预测 vs 实际 <span style="font-weight:400;color:#78909c;font-size:12px">(MW)</span></div>
      <div class="chart-box short" id="chartLoad"></div>
    </div>
  </div>
  <div class="sidebar" id="sidebar">
    <div class="weather-card" id="weatherCard"></div>
    <div class="stats-card" id="statsCard"></div>
    <div class="legend-tip">
      数据来源：<br>
      · 竞价空间：负荷预测 / 电网运行实际<br>
      · 电价：日前 & 实时机组组合收益复盘<br>
      · 天气：Open-Meteo Archive API<br>
      · 地点：德州 (37.45&deg;N, 116.30&deg;E)<br>
      · 键盘 ← → 切换日期
    </div>
  </div>
</div>
<script>
const DATA = ''' + json.dumps(all_data['data'], ensure_ascii=False) + ''';
const WEATHER = ''' + json.dumps(all_data['weather'], ensure_ascii=False) + ''';
const TIMES = ''' + json.dumps(all_data['timeLabels'], ensure_ascii=False) + ''';

const ALL_DATES = Object.keys(DATA).sort();
let currentDate = ALL_DATES[ALL_DATES.length - 1];

const tabsEl = document.getElementById('dateTabs');
ALL_DATES.forEach(function(d) {
  var btn = document.createElement('div');
  btn.className = 'date-tab';
  btn.textContent = d.slice(5);
  btn.onclick = function() { selectDate(d); };
  tabsEl.appendChild(btn);
});

function selectDate(d) {
  currentDate = d;
  var tabs = document.querySelectorAll('.date-tab');
  tabs.forEach(function(t) { t.classList.remove('active'); });
  var idx = ALL_DATES.indexOf(d);
  if (idx >= 0) tabs[idx].classList.add('active');
  renderAll();
}

var cBS = echarts.init(document.getElementById('chartBS'));
var cPrice = echarts.init(document.getElementById('chartPrice'));
var cRE = echarts.init(document.getElementById('chartRE'));
var cLoad = echarts.init(document.getElementById('chartLoad'));

function makeGrid() {
  return {left:50,right:30,top:30,bottom:40};
}

var echartsAxisCommon = {
  axisLabel: {color:'#888',fontSize:10},
  axisLine: {lineStyle:{color:'#d0d0d0'}},
  splitLine: {lineStyle:{color:'#f0f0f0'}}
};
var echartsLegendCommon = {textStyle:{color:'#666'},top:5};

function getOptBS(dd) {
  var d = DATA[dd];
  var series = [];
  if (d && d.pred_bs) series.push({name:'竞价空间(预测)',type:'line',data:d.pred_bs,smooth:true,lineStyle:{width:2,color:'#0078d4',type:'dashed'},itemStyle:{color:'#0078d4'},symbol:'none'});
  if (d && d.act_bs) series.push({name:'竞价空间(实际)',type:'line',data:d.act_bs,smooth:true,lineStyle:{width:2.5,color:'#d83b01'},itemStyle:{color:'#d83b01'},symbol:'none',areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(216,59,1,0.15)'},{offset:1,color:'rgba(216,59,1,0)'}])}});
  return {
    grid:makeGrid(),
    tooltip:{trigger:'axis'},
    legend:Object.assign({data:series.map(function(s){return s.name;})}, echartsLegendCommon),
    xAxis:Object.assign({type:'category',data:TIMES,axisLabel:{interval:7}}, echartsAxisCommon),
    yAxis:Object.assign({type:'value',name:'MW'}, echartsAxisCommon),
    series:series
  };
}

function getOptPrice(dd) {
  var d = DATA[dd];
  var series = [];
  if (d && d.da_price) series.push({name:'日前电价',type:'line',yAxisIndex:0,data:d.da_price,smooth:true,lineStyle:{width:2,color:'#107c10'},itemStyle:{color:'#107c10'},symbol:'none'});
  if (d && d.rt_price) series.push({name:'实时电价',type:'line',yAxisIndex:0,data:d.rt_price,smooth:true,lineStyle:{width:2,color:'#d13438'},itemStyle:{color:'#d13438'},symbol:'none'});
  if (d && d.da_power) series.push({name:'日前计划功率',type:'bar',yAxisIndex:1,data:d.da_power.map(function(v){return v||0;}),itemStyle:{color:function(p){return p.value>=0?'rgba(208,80,70,.35)':'rgba(0,120,212,.3)';}},barWidth:3,barGap:'0%'});
  if (d && d.rt_power) series.push({name:'实时实际功率',type:'bar',yAxisIndex:1,data:d.rt_power.map(function(v){return v||0;}),itemStyle:{color:function(p){return p.value>=0?'rgba(208,80,70,.75)':'rgba(0,120,212,.7)';}},barWidth:3});
  return {
    grid:{left:50,right:60,top:30,bottom:40},
    tooltip:{trigger:'axis'},
    legend:Object.assign({data:series.map(function(s){return s.name;})}, echartsLegendCommon),
    xAxis:Object.assign({type:'category',data:TIMES,axisLabel:{interval:7}}, echartsAxisCommon),
    yAxis:[
      Object.assign({type:'value',name:'元/MWh'}, echartsAxisCommon),
      Object.assign({type:'value',name:'MW',splitLine:{show:false}}, echartsAxisCommon)
    ],
    series:series
  };
}

function getOptRE(dd) {
  var d = DATA[dd];
  var series = [];
  if (d && d.pred_wind) series.push({name:'风电(预测)',type:'line',data:d.pred_wind,smooth:true,lineStyle:{width:1.5,color:'#0078d4',type:'dashed'},itemStyle:{color:'#0078d4'},symbol:'none'});
  if (d && d.act_wind) series.push({name:'风电(实际)',type:'line',data:d.act_wind,smooth:true,lineStyle:{width:2,color:'#0078d4'},itemStyle:{color:'#0078d4'},symbol:'none'});
  if (d && d.pred_solar) series.push({name:'光伏(预测)',type:'line',data:d.pred_solar,smooth:true,lineStyle:{width:1.5,color:'#d83b01',type:'dashed'},itemStyle:{color:'#d83b01'},symbol:'none'});
  if (d && d.act_solar) series.push({name:'光伏(实际)',type:'line',data:d.act_solar,smooth:true,lineStyle:{width:2,color:'#d83b01'},itemStyle:{color:'#d83b01'},symbol:'none',areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(216,59,1,0.12)'},{offset:1,color:'rgba(216,59,1,0)'}])}});
  // 风光加总
  if (d && d.pred_wind && d.pred_solar) {
    var predSum = d.pred_wind.map(function(v,i) { return (v||0) + (d.pred_solar[i]||0); });
    series.push({name:'风光加总(预测)',type:'line',data:predSum,smooth:true,lineStyle:{width:2,color:'#881798',type:'dashed'},itemStyle:{color:'#881798'},symbol:'none'});
  }
  if (d && d.act_wind && d.act_solar) {
    var actSum = d.act_wind.map(function(v,i) { return (v||0) + (d.act_solar[i]||0); });
    series.push({name:'风光加总(实际)',type:'line',data:actSum,smooth:true,lineStyle:{width:2.5,color:'#881798'},itemStyle:{color:'#881798'},symbol:'none',areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(136,23,152,0.12)'},{offset:1,color:'rgba(136,23,152,0)'}])}});
  }
  return {
    grid:makeGrid(),
    tooltip:{trigger:'axis'},
    legend:Object.assign({data:series.map(function(s){return s.name;})}, echartsLegendCommon),
    xAxis:Object.assign({type:'category',data:TIMES,axisLabel:{interval:7}}, echartsAxisCommon),
    yAxis:Object.assign({type:'value',name:'MW'}, echartsAxisCommon),
    series:series
  };
}

function getOptLoad(dd) {
  var d = DATA[dd];
  var series = [];
  if (d && d.pred_load) series.push({name:'直调负荷(预测)',type:'line',data:d.pred_load,smooth:true,lineStyle:{width:1.5,color:'#881798',type:'dashed'},itemStyle:{color:'#881798'},symbol:'none'});
  if (d && d.act_load) series.push({name:'直调负荷(实际)',type:'line',data:d.act_load,smooth:true,lineStyle:{width:2,color:'#881798'},itemStyle:{color:'#881798'},symbol:'none'});
  if (d && d.pred_load && d.pred_wind && d.pred_solar && d.pred_bs) {
    var lian = d.pred_load.map(function(v,i) { return v - (d.pred_wind[i]||0) - (d.pred_solar[i]||0) - (d.pred_bs[i]||0); });
    series.push({name:'联络线受电(预测)',type:'line',data:lian,smooth:true,lineStyle:{width:1.5,color:'#498205',type:'dashed'},itemStyle:{color:'#498205'},symbol:'none'});
  }
  return {
    grid:makeGrid(),
    tooltip:{trigger:'axis'},
    legend:Object.assign({data:series.map(function(s){return s.name;})}, echartsLegendCommon),
    xAxis:Object.assign({type:'category',data:TIMES,axisLabel:{interval:7}}, echartsAxisCommon),
    yAxis:Object.assign({type:'value',name:'MW'}, echartsAxisCommon),
    series:series
  };
}

function renderWeather(dd) {
  var w = WEATHER[dd];
  var card = document.getElementById('weatherCard');
  if (!w) { card.innerHTML = '<h3>天气信息</h3><p style="color:#78909c">无数据</p>'; return; }
  var iconMap = {0:'☀️',1:'🌤️',2:'⛅',3:'☁️',45:'🌫️',48:'🌫️',51:'🌦️',53:'🌦️',55:'🌧️',61:'🌧️',63:'🌧️',65:'🌧️',71:'🌨️',73:'🌨️',75:'🌨️',80:'🌦️',81:'🌧️',82:'🌧️',95:'⛈️',96:'⛈️',99:'⛈️'};
  var icon = iconMap[w.code] || '🌡️';
  var sunH = (w.sunshine / 3600).toFixed(1);
  card.innerHTML =
    '<h3>' + dd + ' 天气</h3>' +
    '<div class="weather-main">' +
      '<div class="weather-icon">' + icon + '</div>' +
      '<div>' +
        '<div class="weather-desc">' + w.desc + '</div>' +
        '<div class="weather-temp">' + w.temp_max + '°<span style="font-size:14px;color:#78909c"> / ' + w.temp_min + '°</span></div>' +
      '</div>' +
    '</div>' +
    '<div class="weather-grid">' +
      '<div class="weather-item"><div class="label">辐照度</div><div class="value highlight">' + w.radiation.toFixed(1) + ' MJ/m²</div></div>' +
      '<div class="weather-item"><div class="label">日照时长</div><div class="value highlight">' + sunH + ' h</div></div>' +
      '<div class="weather-item"><div class="label">最大风速</div><div class="value blue">' + w.wind_max + ' km/h</div></div>' +
      '<div class="weather-item"><div class="label">主导风向</div><div class="value blue">' + w.wind_dir_str + ' (' + w.wind_dir + '°)</div></div>' +
      '<div class="weather-item"><div class="label">降水量</div><div class="value ' + (w.precip>0?'red':'green') + '">' + w.precip + ' mm</div></div>' +
      '<div class="weather-item"><div class="label">相对湿度</div><div class="value">' + w.humidity + '%</div></div>' +
      '<div class="weather-item"><div class="label">云量</div><div class="value">' + w.cloud + '%</div></div>' +
      '<div class="weather-item"><div class="label">气温范围</div><div class="value">' + w.temp_min + '~' + w.temp_max + '°C</div></div>' +
    '</div>';
}

function renderStats(dd) {
  var d = DATA[dd];
  var card = document.getElementById('statsCard');
  if (!d) { card.innerHTML = '<h3>数据统计</h3><p style="color:#78909c">无数据</p>'; return; }
  var html = '<h3>' + dd + ' 关键指标</h3>';
  var fmt = function(v,d) { d=d||0; return v!=null ? v.toFixed(d) : '—'; };
  var clr = function(v,t) { return v>t?'up':(v<-t?'down':''); };

  if (d.pred_bs && d.act_bs) {
    var predAvg = d.pred_bs.reduce(function(a,b){return a+b;},0)/96;
    var actAvg = d.act_bs.reduce(function(a,b){return a+b;},0)/96;
    var diff = actAvg - predAvg;
    html += '<div class="stat-row"><span class="label">竞价空间(预测均值)</span><span class="val">' + fmt(predAvg,0) + ' MW</span></div>';
    html += '<div class="stat-row"><span class="label">竞价空间(实际均值)</span><span class="val">' + fmt(actAvg,0) + ' MW</span></div>';
    html += '<div class="stat-row"><span class="label">偏差</span><span class="val ' + clr(diff,500) + '">' + (diff>0?'+':'') + fmt(diff,0) + ' MW</span></div>';
  }
  if (d.da_price) {
    var daAvg = d.da_price.reduce(function(a,b){return a+b;},0)/96;
    var daMax = Math.max.apply(null, d.da_price);
    var daMin = Math.min.apply(null, d.da_price.filter(function(v){return v>0;}));
    html += '<div class="stat-row"><span class="label">日前电价均值</span><span class="val">' + fmt(daAvg,1) + ' 元/MWh</span></div>';
    html += '<div class="stat-row"><span class="label">日前电价范围</span><span class="val">' + fmt(daMin,0) + '~' + fmt(daMax,0) + '</span></div>';
  }
  if (d.rt_price) {
    var rtAvg = d.rt_price.reduce(function(a,b){return a+b;},0)/96;
    var rtMax = Math.max.apply(null, d.rt_price);
    var rtMin = Math.min.apply(null, d.rt_price.filter(function(v){return v>0;}));
    html += '<div class="stat-row"><span class="label">实时电价均值</span><span class="val">' + fmt(rtAvg,1) + ' 元/MWh</span></div>';
    html += '<div class="stat-row"><span class="label">实时电价范围</span><span class="val">' + fmt(rtMin,0) + '~' + fmt(rtMax,0) + '</span></div>';
  }
  if (d.pred_wind) {
    var wAvg = d.pred_wind.reduce(function(a,b){return a+b;},0)/96;
    html += '<div class="stat-row"><span class="label">风电预测均值</span><span class="val">' + fmt(wAvg,0) + ' MW</span></div>';
  }
  if (d.pred_solar) {
    var sAvg = d.pred_solar.reduce(function(a,b){return a+b;},0)/96;
    html += '<div class="stat-row"><span class="label">光伏预测均值</span><span class="val">' + fmt(sAvg,0) + ' MW</span></div>';
  }
  card.innerHTML = html;
}

function renderAll() {
  var dd = currentDate;
  cBS.setOption(getOptBS(dd), true);
  cPrice.setOption(getOptPrice(dd), true);
  cRE.setOption(getOptRE(dd), true);
  cLoad.setOption(getOptLoad(dd), true);
  renderWeather(dd);
  renderStats(dd);
}

selectDate(currentDate);

window.addEventListener('resize', function() {
  cBS.resize();
  cPrice.resize();
  cRE.resize();
  cLoad.resize();
});

document.addEventListener('keydown', function(e) {
  var idx = ALL_DATES.indexOf(currentDate);
  if (e.key === 'ArrowLeft' && idx > 0) selectDate(ALL_DATES[idx-1]);
  if (e.key === 'ArrowRight' && idx < ALL_DATES.length-1) selectDate(ALL_DATES[idx+1]);
});
</script>
</body>
</html>'''

out_path = os.path.join(ROOT, 'output', '竞价空间_电价_天气综合分析_202507.html')  # DATE_RANGE: 修改这里的日期范围
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'HTML saved to: {out_path}')
print(f'File size: {len(html):,} bytes')