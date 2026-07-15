"""Generate 日对比分析 HTML for 0628-0708 per 日对比分析.txt requirements.

7 charts with date chip selector, forecast vs actual comparison.
"""
import json, os, pymysql
from datetime import datetime

DATES = ['2026-07-01','2026-07-02','2026-07-03','2026-07-04','2026-07-05','2026-07-06','2026-07-07','2026-07-08','2026-07-09','2026-07-10','2026-07-11','2026-07-12','2026-07-13','2026-07-14']
TIMES = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0,15,30,45)]
COLORS = ['#0078d4','#d13438','#107c10','#f2a900','#9a60b4','#5470c6','#d83b01','#73c0de','#fc8452','#3ba272','#e67e22','#8b5cf6','#00bcd4','#ff5722']

conn = pymysql.connect(host='rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com', port=3306,
    user='pengyiqiang', password='pengyiqiang123', database='tianrun_new',
    charset='utf8mb4', connect_timeout=10, read_timeout=60)
cur = conn.cursor()

# ── 1. Load forecast data ──
fc = {}  # {date: {all_load, dispatched_load, tie_line, wind, pv, nuclear}}
for d in DATES:
    cur.execute('''SELECT all_load_forecast, dispatched_load_forecast, tie_line_load_forecast,
        wind_power_forecast, photovoltaic_power_forecast, nuclear_power_forecast
        FROM shandong_px_spot_dayahead_load_info WHERE date=%s ORDER BY time_order''', (d,))
    rows = cur.fetchall()
    if rows:
        fc[d] = {
            'all_load': [float(r[0] or 0) for r in rows],
            'dispatched': [float(r[1] or 0) for r in rows],
            'tie_line': [float(r[2] or 0) for r in rows],
            'wind': [float(r[3] or 0) for r in rows],
            'pv': [float(r[4] or 0) for r in rows],
            'nuclear': [float(r[5] or 0) for r in rows],
        }
        fc[d]['new_energy'] = [fc[d]['wind'][i] + fc[d]['pv'][i] for i in range(96)]
        fc[d]['bidding_space'] = [fc[d]['dispatched'][i] - fc[d]['tie_line'][i] - fc[d]['wind'][i] - fc[d]['pv'][i] - fc[d]['nuclear'][i] for i in range(96)]

# ── 2. Load actual data ──
ac = {}
for d in DATES:
    cur.execute('''SELECT actual_all_load, actual_dispatched_load, actual_tie_line_load,
        actual_wind_power, actual_photovoltaic_power, actual_nuclear_power,
        actual_pumped_storage_power, actual_local_power
        FROM shandong_px_spot_actual_load_info WHERE date=%s ORDER BY time_order''', (d,))
    rows = cur.fetchall()
    if rows:
        ac[d] = {
            'all_load': [float(r[0] or 0) for r in rows],
            'dispatched': [float(r[1] or 0) for r in rows],
            'tie_line': [float(r[2] or 0) for r in rows],
            'wind': [float(r[3] or 0) for r in rows],
            'pv': [float(r[4] or 0) for r in rows],
            'nuclear': [float(r[5] or 0) for r in rows],
            'pumped_storage': [float(r[6] or 0) for r in rows],
            'local_power': [float(r[7] or 0) for r in rows],
        }
        ac[d]['new_energy'] = [ac[d]['wind'][i] + ac[d]['pv'][i] for i in range(96)]
        ac[d]['bidding_space'] = [ac[d]['dispatched'][i] - ac[d]['tie_line'][i] - ac[d]['wind'][i] - ac[d]['pv'][i] - ac[d]['nuclear'][i] for i in range(96)]

# ── 3. Load clearing quantity (MWh→MW ×4) ──
clr = {}
for d in DATES:
    cur.execute('''SELECT time_point, thermal_clearing, thermal_number, nuclear_clearing,
        new_energy_clearing, independent_clearing, draw_clearing, virtual_clearing
        FROM shandong_px_dayahead_clearing_quantity_number WHERE date=%s ORDER BY time_point''', (d,))
    rows = cur.fetchall()
    if rows:
        clr[d] = {
            'thermal': [float(r[1] or 0) * 4 for r in rows],
            'thermal_num': [float(r[2] or 0) for r in rows],
            'nuclear': [float(r[3] or 0) * 4 for r in rows],
            'new_energy': [float(r[4] or 0) * 4 for r in rows],
            'independent': [float(r[5] or 0) * 4 for r in rows],
            'draw': [float(r[6] or 0) * 4 for r in rows],
            'virtual': [float(r[7] or 0) * 4 for r in rows],
        }
        # 火电实际出清 = 实际(直调 - 联络线 - 风电 - 光伏 - 核电 - 抽蓄 - 地方公用电厂) - 日前出清储能(独立储能×4)
        if d in ac:
            clr[d]['thermal_actual'] = [
                ac[d]['dispatched'][i] - ac[d]['tie_line'][i] - ac[d]['wind'][i]
                - ac[d]['pv'][i] - ac[d]['nuclear'][i]
                - ac[d]['pumped_storage'][i] - ac[d]['local_power'][i]
                - clr[d]['independent'][i]
                for i in range(96)
            ]

# ── 4. Load 润津 prices ──
daP = {}; rtP = {}; daPower = {}
for d in DATES:
    cur.execute("SELECT time_point, power, price FROM shandong_px_reliable_clearing_unit_data WHERE date=%s AND member_id='b9e64e64a713458eba94c9af05c0a757' AND unit_name NOT LIKE '%%发电%%' AND unit_name NOT LIKE '%%用电%%' ORDER BY time_point", (d,))
    rows = cur.fetchall()
    daP[d] = [float(r[2] or 0) for r in rows] if rows else [0]*96
    daPower[d] = [float(r[1] or 0) for r in rows] if rows else [0]*96

    cur.execute("SELECT time_point, price, power FROM shandong_px_realtime_clearing_results_query WHERE date=%s AND member_id='b9e64e64a713458eba94c9af05c0a757' ORDER BY time_point", (d,))
    rows = cur.fetchall()
    rtP[d] = [float(r[1] or 0) for r in rows] if rows else [0]*96

cur.close(); conn.close()

# ── Build JSON data ──
fc_json = json.dumps(fc, ensure_ascii=False)
ac_json = json.dumps(ac, ensure_ascii=False)
clr_json = json.dumps(clr, ensure_ascii=False)
daP_json = json.dumps(daP, ensure_ascii=False)
rtP_json = json.dumps(rtP, ensure_ascii=False)
daPower_json = json.dumps(daPower, ensure_ascii=False)
dates_json = json.dumps(DATES, ensure_ascii=False)
labels_json = json.dumps([d[5:] for d in DATES], ensure_ascii=False)
times_json = json.dumps(TIMES, ensure_ascii=False)
colors_json = json.dumps(COLORS, ensure_ascii=False)

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>日运营复盘对比分析 | 0701 ~ 0714</title>
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
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:8px 24px}}
@media(max-width:1200px){{.charts{{grid-template-columns:1fr}}}}
.panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.panel .t{{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.panel .c{{width:100%;height:400px}}
.panel.full{{grid-column:1/-1}}
.panel.full .c{{height:420px}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
</style>
</head>
<body>
<div class="header">
<h1>日运营复盘对比分析 | 0701 ~ 0714</h1>
<div class="info">数据来源：天机库 · 点击日期筛选 · 供需/竞价空间/充放/全景/火电/储能/光伏</div>
</div>
<div class="date-bar">
<span class="label">选择日期：</span>
<div id="dateChips"></div>
<div class="actions">
<button onclick="selectAll()">全选</button>
<button onclick="clearAll()">清除</button>
</div>
</div>
<div class="charts">
<div class="panel"><div class="t">全网负荷 预测 vs 实际（MW）<span style="font-weight:400;color:#888;font-size:11px"> — 实线=预测，虚线=实际</span></div><div class="c" id="c1a"></div></div>
<div class="panel"><div class="t">直调负荷 预测 vs 实际（MW）</div><div class="c" id="c1b"></div></div>
<div class="panel"><div class="t">新能源（风电+光伏）预测 vs 实际（MW）</div><div class="c" id="c1c"></div></div>
<div class="panel"><div class="t">光伏 预测 vs 实际（MW）</div><div class="c" id="c1d"></div></div>
<div class="panel full"><div class="t">竞价空间 + 火电出清 + 电价（MW / 元/MWh）<span style="font-weight:400;color:#888;font-size:11px"> — 预测竞价空间(实线)、实际竞价空间(虚线)、火电日前出清(条形)、火电实际出清(点线)</span></div><div class="c" id="c2"></div></div>
<div class="panel full"><div class="t">润津储能充放功率 + 电价（MW / 元/MWh）<span style="font-weight:400;color:#888;font-size:11px"> — 正=放电，负=充电</span></div><div class="c" id="c3"></div></div>
<div class="panel full"><div class="t">日前出清全景 — 各类电源出清电力（MW）<span style="font-weight:400;color:#888;font-size:11px"> — 堆叠面积图</span></div><div class="c" id="c4"></div></div>
<div class="panel"><div class="t">全省火电出清电力 + 台数 + 日前电价（MW）</div><div class="c" id="c5"></div></div>
<div class="panel"><div class="t">全省抽蓄 + 独立储能出清（MW）</div><div class="c" id="c6"></div></div>
<div class="panel full"><div class="t">新能源（风电+光伏）日前出清 vs 实际运行（MW）</div><div class="c" id="c7"></div></div>
</div>
<div class="footer">润津储能 · 日运营复盘对比分析 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<script>
var T={times_json};
var DATES={dates_json};
var LABELS={labels_json};
var FC={fc_json};
var AC={ac_json};
var CLR={clr_json};
var DAP={daP_json};
var RTP={rtP_json};
var DAPOWER={daPower_json};
var COLORS={colors_json};

var g={{left:55,right:60,top:20,bottom:35}};
var g2={{left:55,right:70,top:20,bottom:35}};
var ec={{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var ec2={{axisLabel:{{color:'#e67e22',fontSize:10}},axisLine:{{lineStyle:{{color:'#e67e22'}}}},splitLine:{{show:false}}}};
var ec3={{axisLabel:{{color:'#9a60b4',fontSize:10}},axisLine:{{lineStyle:{{color:'#9a60b4'}}}},splitLine:{{show:false}}}};
var el={{textStyle:{{color:'#666',fontSize:10}},top:3}};
var xA=Object.assign({{type:'category',data:T,axisLabel:{{interval:7}}}},ec);

var selected=DATES.filter(function(d){{return FC.hasOwnProperty(d) && AC.hasOwnProperty(d) && CLR.hasOwnProperty(d);}});
var validDates=DATES.filter(function(d){{return FC.hasOwnProperty(d) && AC.hasOwnProperty(d) && CLR.hasOwnProperty(d);}});

function renderChips(){{
  var html='';
  DATES.forEach(function(d,i){{
    var hasData=FC.hasOwnProperty(d)&&AC.hasOwnProperty(d)&&CLR.hasOwnProperty(d);
    var active=selected.indexOf(d)>=0?' active':'';
    var disabled=hasData?'':' disabled';
    var style=hasData?'':' style="opacity:0.35;cursor:not-allowed"';
    html+='<span class="date-chip'+active+disabled+'" data-date="'+d+'" onclick="toggleDate(this)"'+style+'>'+LABELS[i]+'</span>';
  }});
  document.getElementById('dateChips').innerHTML=html;
}}

function toggleDate(el){{
  var d=el.dataset.date;
  if(!FC.hasOwnProperty(d)||!AC.hasOwnProperty(d)||!CLR.hasOwnProperty(d)) return;
  var idx=selected.indexOf(d);
  if(idx>=0){{selected.splice(idx,1);el.classList.remove('active');}}
  else{{selected.push(d);el.classList.add('active');}}
  selected.sort(function(a,b){{return DATES.indexOf(a)-DATES.indexOf(b);}});
  refreshAll();
}}

function selectAll(){{
  selected=validDates.slice();
  document.querySelectorAll('.date-chip').forEach(function(c){{if(FC.hasOwnProperty(c.dataset.date))c.classList.add('active');}});
  refreshAll();
}}

function clearAll(){{
  selected=[];
  document.querySelectorAll('.date-chip').forEach(function(c){{c.classList.remove('active');}});
  refreshAll();
}}

function getColor(i){{return COLORS[i%COLORS.length];}}
function lb(d){{return d.slice(5);}}

function buildFcAcSeries(fcMap,acMap,key){{
  var s=[];
  selected.forEach(function(d,i){{
    var c=getColor(i);
    if(fcMap[d]&&fcMap[d][key]) s.push({{name:lb(d)+' 预测',type:'line',data:fcMap[d][key],smooth:true,lineStyle:{{width:2,color:c}},itemStyle:{{color:c}},symbol:'none'}});
    if(acMap[d]&&acMap[d][key]) s.push({{name:lb(d)+' 实际',type:'line',data:acMap[d][key],smooth:true,lineStyle:{{width:2,color:c,type:'dashed'}},itemStyle:{{color:c}},symbol:'none'}});
  }});
  return s;
}}

function buildLineSeries(dataMap,key,style,colorFn){{
  var s=[];
  selected.forEach(function(d,i){{
    var c=colorFn?colorFn(i):getColor(i);
    if(dataMap[d]&&dataMap[d][key]){{
      var opt={{name:lb(d),type:'line',data:dataMap[d][key],smooth:true,lineStyle:Object.assign({{width:2,color:c}},style||{{}}),itemStyle:{{color:c}},symbol:'none'}};
      s.push(opt);
    }}
  }});
  return s;
}}

function buildBarSeries(dataMap,key){{
  var s=[];
  selected.forEach(function(d,i){{
    var c=getColor(i);
    if(dataMap[d]&&dataMap[d][key]) s.push({{name:lb(d),type:'bar',data:dataMap[d][key],barWidth:3,itemStyle:{{color:c,opacity:0.6}}}});
  }});
  return s;
}}

function buildLegend(fcMap,acMap,key){{
  var leg=[];
  selected.forEach(function(d,i){{leg.push(lb(d)+' 预测',lb(d)+' 实际');}});
  return leg;
}}

function buildLegendSimple(dataMap,key){{
  return selected.map(function(d){{return lb(d);}});
}}

function refreshAll(){{
  if(selected.length===0){{clearCharts();return;}}

  // Chart 1a: 全网负荷
  c1a.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:buildLegend(FC,AC,'all_load'),type:'scroll',bottom:0}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:buildFcAcSeries(FC,AC,'all_load')}},true);

  // Chart 1b: 直调负荷
  c1b.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:buildLegend(FC,AC,'dispatched'),type:'scroll',bottom:0}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:buildFcAcSeries(FC,AC,'dispatched')}},true);

  // Chart 1c: 新能源(风电+光伏)
  c1c.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:buildLegend(FC,AC,'new_energy'),type:'scroll',bottom:0}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:buildFcAcSeries(FC,AC,'new_energy')}},true);

  // Chart 1d: 光伏
  c1d.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:buildLegend(FC,AC,'pv'),type:'scroll',bottom:0}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:buildFcAcSeries(FC,AC,'pv')}},true);

  // Chart 2: 竞价空间+火电+电价
  var c2series=[];
  selected.forEach(function(d,i){{
    var c=getColor(i);
    // 预测竞价空间
    if(FC[d]) c2series.push({{name:lb(d)+' 预测竞价',type:'line',data:FC[d].bidding_space,smooth:true,lineStyle:{{width:2,color:c}},itemStyle:{{color:c}},symbol:'none'}});
    // 实际竞价空间
    if(AC[d]) c2series.push({{name:lb(d)+' 实际竞价',type:'line',data:AC[d].bidding_space,smooth:true,lineStyle:{{width:2,color:c,type:'dashed'}},itemStyle:{{color:c}},symbol:'none'}});
    // 火电日前出清
    if(CLR[d]) c2series.push({{name:lb(d)+' 火电日前',type:'line',data:CLR[d].thermal,smooth:true,lineStyle:{{width:2,color:c}},itemStyle:{{color:c}},symbol:'none'}});
    // 火电实际出清
    if(CLR[d]&&CLR[d].thermal_actual) c2series.push({{name:lb(d)+' 火电实际',type:'line',data:CLR[d].thermal_actual,smooth:true,lineStyle:{{width:2,color:c,type:'dotted'}},itemStyle:{{color:c}},symbol:'none'}});
  }});
  // 电价 (use first selected day's price)
  var fd=selected[0];
  if(DAP[fd]&&DAP[fd].some(function(v){{return v!==0;}})) c2series.push({{name:'日前电价',type:'line',data:DAP[fd],smooth:true,lineStyle:{{width:2,color:'#9a60b4'}},itemStyle:{{color:'#9a60b4'}},symbol:'none',yAxisIndex:1}});
  if(RTP[fd]&&RTP[fd].some(function(v){{return v!==0;}})) c2series.push({{name:'实时电价',type:'line',data:RTP[fd],smooth:true,lineStyle:{{width:2,color:'#d13438'}},itemStyle:{{color:'#d13438'}},symbol:'none',yAxisIndex:1}});
  c2.setOption({{grid:g2,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:c2series.map(function(x){{return x.name;}}),type:'scroll',bottom:0}},el),xAxis:xA,yAxis:[Object.assign({{type:'value',name:'MW'}},ec),Object.assign({{type:'value',name:'元/MWh'}},ec2)],series:c2series}},true);

  // Chart 3: 润津充放+电价
  var c3series=[];
  selected.forEach(function(d,i){{
    var c=getColor(i);
    if(DAPOWER[d]) c3series.push({{name:lb(d)+' 充放功率',type:'bar',data:DAPOWER[d],barWidth:3,itemStyle:{{color:function(p){{return p.value>=0?c:'#e67e22';}},opacity:0.7}}}});
  }});
  if(DAP[fd]&&DAP[fd].some(function(v){{return v!==0;}})) c3series.push({{name:'日前电价',type:'line',data:DAP[fd],smooth:true,lineStyle:{{width:2,color:'#9a60b4'}},itemStyle:{{color:'#9a60b4'}},symbol:'none',yAxisIndex:1}});
  if(RTP[fd]&&RTP[fd].some(function(v){{return v!==0;}})) c3series.push({{name:'实时电价',type:'line',data:RTP[fd],smooth:true,lineStyle:{{width:2,color:'#d13438'}},itemStyle:{{color:'#d13438'}},symbol:'none',yAxisIndex:1}});
  c3.setOption({{grid:g2,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:c3series.map(function(x){{return x.name;}}),type:'scroll',bottom:0}},el),xAxis:xA,yAxis:[Object.assign({{type:'value',name:'MW'}},ec),Object.assign({{type:'value',name:'元/MWh'}},ec2)],series:c3series}},true);

  // Chart 4: 日前出清全景堆叠 (use first selected day)
  var d0=selected[0];
  if(CLR[d0]){{
    c4.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:['火电','核电','新能源','抽蓄','独立储能','虚拟'],bottom:0}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:[
      {{name:'火电',type:'line',data:CLR[d0].thermal,smooth:true,stack:'total',areaStyle:{{}},lineStyle:{{width:1,color:'#d13438'}},itemStyle:{{color:'#d13438'}},symbol:'none'}},
      {{name:'核电',type:'line',data:CLR[d0].nuclear,smooth:true,stack:'total',areaStyle:{{}},lineStyle:{{width:1,color:'#9a60b4'}},itemStyle:{{color:'#9a60b4'}},symbol:'none'}},
      {{name:'新能源',type:'line',data:CLR[d0].new_energy,smooth:true,stack:'total',areaStyle:{{}},lineStyle:{{width:1,color:'#107c10'}},itemStyle:{{color:'#107c10'}},symbol:'none'}},
      {{name:'抽蓄',type:'line',data:CLR[d0].draw,smooth:true,stack:'total',areaStyle:{{}},lineStyle:{{width:1,color:'#f2a900'}},itemStyle:{{color:'#f2a900'}},symbol:'none'}},
      {{name:'独立储能',type:'line',data:CLR[d0].independent,smooth:true,stack:'total',areaStyle:{{}},lineStyle:{{width:1,color:'#0078d4'}},itemStyle:{{color:'#0078d4'}},symbol:'none'}},
      {{name:'虚拟',type:'line',data:CLR[d0].virtual,smooth:true,stack:'total',areaStyle:{{}},lineStyle:{{width:1,color:'#ccc'}},itemStyle:{{color:'#ccc'}},symbol:'none'}}
    ]}},true);
  }}

  // Chart 5: 火电出清电力+台数+电价
  if(CLR[d0]){{
    var thnMin=Math.min.apply(null,CLR[d0].thermal_num);
    var thnMax=Math.max.apply(null,CLR[d0].thermal_num);
    c5.setOption({{grid:g2,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:['火电出清电力','火电台数','日前电价']}},el),xAxis:xA,
      yAxis:[Object.assign({{type:'value',name:'MW'}},ec),Object.assign({{type:'value',name:'台',min:Math.max(0,thnMin-5),max:Math.min(100,thnMax+5)}},ec2),Object.assign({{type:'value',name:'元/MWh'}},ec3)],
      series:[
        {{name:'火电出清电力',type:'bar',data:CLR[d0].thermal,barWidth:3,itemStyle:{{color:'#d13438'}}}},
        {{name:'火电台数',type:'line',data:CLR[d0].thermal_num,smooth:false,step:'end',lineStyle:{{width:2,color:'#0078d4'}},itemStyle:{{color:'#0078d4'}},symbol:'none',yAxisIndex:1}},
        {{name:'日前电价',type:'line',data:DAP[d0],smooth:true,lineStyle:{{width:2,color:'#9a60b4'}},itemStyle:{{color:'#9a60b4'}},symbol:'none',yAxisIndex:2}}
    ]}},true);
  }}

  // Chart 6: 抽蓄+独立储能
  if(CLR[d0]){{
    c6.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:['抽蓄','独立储能','零线']}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:[
      {{name:'抽蓄',type:'bar',data:CLR[d0].draw,barWidth:5,itemStyle:{{color:function(p){{return p.value>=0?'#107c10':'#d13438';}}}}}},
      {{name:'独立储能',type:'bar',data:CLR[d0].independent,barWidth:5,itemStyle:{{color:function(p){{return p.value>=0?'#0078d4':'#e67e22';}}}}}},
      {{name:'零线',type:'line',data:Array(96).fill(0),lineStyle:{{color:'#ccc',width:1}},symbol:'none',silent:true}}
    ]}},true);
  }}

  // Chart 7: 新能源日前出清 vs 实际新能源出力
  var c7series=[];
  if(CLR[d0]){{
    var neClr = CLR[d0].new_energy;  // MWh→MW already ×4
    c7series.push({{name:'新能源日前出清',type:'line',data:neClr,smooth:true,lineStyle:{{width:2,color:'#107c10'}},itemStyle:{{color:'#107c10'}},symbol:'none',areaStyle:{{color:new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:'rgba(16,124,16,0.15)'}},{{offset:1,color:'rgba(16,124,16,0)'}}])}}}});
  }}
  if(AC[d0]){{
    var neAct = AC[d0].new_energy;  // 风电+光伏实际
    c7series.push({{name:'新能源实际出力',type:'line',data:neAct,smooth:true,lineStyle:{{width:2,color:'#f2a900',type:'dashed'}},itemStyle:{{color:'#f2a900'}},symbol:'none'}});
  }}
  c7.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:['新能源日前出清','新能源实际出力']}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:c7series}},true);
}}

function clearCharts(){{
  var empty={{grid:g,xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:[]}};
  [c1a,c1b,c1c,c1d,c2,c3,c4,c5,c6,c7].forEach(function(c){{c.setOption(empty,true);}});
}}

var c1a=echarts.init(document.getElementById('c1a'));
var c1b=echarts.init(document.getElementById('c1b'));
var c1c=echarts.init(document.getElementById('c1c'));
var c1d=echarts.init(document.getElementById('c1d'));
var c2=echarts.init(document.getElementById('c2'));
var c3=echarts.init(document.getElementById('c3'));
var c4=echarts.init(document.getElementById('c4'));
var c5=echarts.init(document.getElementById('c5'));
var c6=echarts.init(document.getElementById('c6'));
var c7=echarts.init(document.getElementById('c7'));

renderChips();
refreshAll();

window.addEventListener('resize',function(){{c1a.resize();c1b.resize();c1c.resize();c1d.resize();c2.resize();c3.resize();c4.resize();c5.resize();c6.resize();c7.resize();}});
</script>
</body>
</html>'''

OUT = 'E:/DataWork/Storage_Strategy/output/日运营复盘对比分析_0701-0714.html'
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved: {OUT} ({os.path.getsize(OUT):,} bytes)')