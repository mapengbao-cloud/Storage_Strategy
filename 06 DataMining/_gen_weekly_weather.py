"""Generate weekly weather forecast HTML for Shandong 7-city average."""
import json, os, urllib.request, urllib.parse
from datetime import date

CITIES = {
    '德州': (37.45, 116.30), '济南': (36.67, 116.98), '青岛': (36.07, 120.38),
    '烟台': (37.53, 121.40), '临沂': (35.10, 118.35), '菏泽': (35.23, 115.48), '潍坊': (36.71, 119.16),
}

params_template = {
    'hourly': 'shortwave_radiation,direct_radiation,diffuse_radiation,wind_speed_10m,wind_speed_100m,temperature_2m,relative_humidity_2m,cloud_cover',
    'daily': 'sunshine_duration,shortwave_radiation_sum,sunrise,sunset',
    'timezone': 'Asia/Shanghai', 'forecast_days': 7, 'wind_speed_unit': 'kmh',
}

all_hourly, all_daily = {}, {}
for name, (lat, lon) in CITIES.items():
    params = dict(params_template, latitude=lat, longitude=lon)
    url = f"https://api.open-meteo.com/v1/forecast?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={'User-Agent': 'StorageStrategy/1.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    all_hourly[name] = data['hourly']
    all_daily[name] = data['daily']
    print(f'Fetched: {name}')

NC = len(CITIES)
hourly_keys = ['shortwave_radiation', 'direct_radiation', 'diffuse_radiation', 'wind_speed_10m',
               'wind_speed_100m', 'temperature_2m', 'relative_humidity_2m', 'cloud_cover']
daily_keys = ['sunshine_duration', 'shortwave_radiation_sum']

ref = all_hourly[list(CITIES.keys())[0]]
avg_hourly = {'time': ref['time']}
for k in hourly_keys:
    avg_hourly[k] = [sum(all_hourly[c][k][i] for c in CITIES) / NC for i in range(len(ref['time']))]

ref_d = all_daily[list(CITIES.keys())[0]]
avg_daily = {'time': ref_d['time'], 'sunrise': ref_d['sunrise'], 'sunset': ref_d['sunset']}
for k in daily_keys:
    avg_daily[k] = [sum(all_daily[c][k][i] for c in CITIES) / NC for i in range(len(ref_d['time']))]

RAW = {
    'hourly_units': {'time': 'iso8601', 'shortwave_radiation': 'W/m²', 'direct_radiation': 'W/m²',
                     'diffuse_radiation': 'W/m²', 'wind_speed_10m': 'km/h', 'wind_speed_100m': 'km/h',
                     'temperature_2m': '°C', 'relative_humidity_2m': '%', 'cloud_cover': '%'},
    'hourly': avg_hourly,
    'daily_units': {'time': 'iso8601', 'sunshine_duration': 's', 'sunrise': 'iso8601',
                    'sunset': 'iso8601', 'shortwave_radiation_sum': 'MJ/m²'},
    'daily': avg_daily,
    'latitude': 36.5, 'longitude': 118.0, 'generationtime_ms': 0, 'utc_offset_seconds': 28800,
    'timezone': 'Asia/Shanghai', 'timezone_abbreviation': 'GMT+8', 'elevation': 50.0,
}

dates = RAW['daily']['time']
weekday_map = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
DAYS = []
for d in dates:
    y, m, d2 = d.split('-')
    dt = date(int(y), int(m), int(d2))
    DAYS.append(f'{int(m)}/{int(d2)} {weekday_map[dt.weekday()]}')

update_date = dates[0]
date_range = f"{dates[0][5:].replace('-', '')}-{dates[-1][5:].replace('-', '')}"

raw_json = json.dumps(RAW, ensure_ascii=False)
days_json = json.dumps(DAYS, ensure_ascii=False)

COLORS = json.dumps(['#38bdf8', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#f97316'])

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>山东省未来一周气象预测 · 润津储能电站</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#fff;color:#1e293b;padding:24px}}
h1{{text-align:center;font-size:22px;margin-bottom:6px;color:#0f172a}}
.subtitle{{text-align:center;font-size:13px;color:#64748b;margin-bottom:24px}}
.cards{{display:grid;grid-template-columns:repeat(7,1fr);gap:10px;margin-bottom:24px}}
.card{{background:#f8fafc;border-radius:10px;padding:14px 10px;text-align:center;border:1px solid #e2e8f0;border-top:3px solid #38bdf8}}
.card.overcast{{border-top-color:#94a3b8}}
.card .day{{font-size:13px;color:#64748b;margin-bottom:4px}}
.card .date{{font-size:11px;color:#94a3b8;margin-bottom:8px}}
.card .label{{font-size:10px;color:#94a3b8;margin-bottom:2px}}
.card .val{{font-size:18px;font-weight:700;color:#0f172a}}
.card .val.small{{font-size:14px}}
.card .unit{{font-size:10px;color:#64748b}}
.row{{display:flex;gap:24px;margin-bottom:24px}}
.chart-box{{flex:1;background:#f8fafc;border-radius:10px;padding:16px;border:1px solid #e2e8f0}}
.chart-box h2{{font-size:14px;color:#64748b;margin-bottom:8px}}
.chart{{width:100%;height:380px}}
.chart.wide{{height:420px}}
.full{{width:100%}}
.note{{font-size:11px;color:#94a3b8;text-align:center;margin-top:16px}}
</style>
</head>
<body>
<h1>山东省未来一周气象预测 · 润津储能电站</h1>
<div class="subtitle">山东全省 7 市均值 (德州/济南/青岛/烟台/临沂/菏泽/潍坊) | 数据源 Open-Meteo | 更新于 {update_date}</div>
<div class="cards" id="cards"></div>
<div class="row">
  <div class="chart-box" style="flex:2"><h2>辐照度 24h 逐时曲线 (W/m²)</h2><div class="chart wide" id="c1"></div></div>
  <div class="chart-box" style="flex:1"><h2>日总辐照量 & 日照时长</h2><div class="chart wide" id="c2"></div></div>
</div>
<div class="row">
  <div class="chart-box"><h2>风速 10m / 100m (km/h)</h2><div class="chart" id="c3"></div></div>
  <div class="chart-box"><h2>温度 & 相对湿度</h2><div class="chart" id="c4"></div></div>
</div>
<div class="row">
  <div class="chart-box" style="flex:1"><h2>云量热力图 (%)</h2><div class="chart" id="c5"></div></div>
</div>
<div class="note">GHI = 短波辐照度 | DNI = 直接辐照度 | DHI = 散射辐照度 | 日照时长 = 日累计直射辐照度≥120W/m² 的时间</div>
<script>
const RAW = {raw_json};

const DAYS = {days_json};
const DATES = RAW.daily.time;
const N = 7;
const C = {COLORS};

function slice(d,arr){{return arr.slice(d*24,d*24+24)}}
function dayLabels(){{var a=[];for(var h=0;h<24;h++)a.push(('0'+h).slice(-2)+':00');return a}}
function theme(){{
  return {{
    textStyle:{{color:'#64748b'}},
    legend:{{textStyle:{{color:'#64748b'}}}},
    tooltip:{{backgroundColor:'rgba(255,255,255,0.95)',borderColor:'#cbd5e1',textStyle:{{color:'#1e293b'}}}},
    grid:{{left:50,right:20,top:40,bottom:30}},
    xAxis:{{axisLine:{{lineStyle:{{color:'#cbd5e1'}}}},axisTick:{{lineStyle:{{color:'#cbd5e1'}}}},splitLine:{{show:false}},axisLabel:{{color:'#94a3b8',fontSize:10,interval:3}}}},
    yAxis:{{axisLine:{{show:false}},splitLine:{{lineStyle:{{color:'#e2e8f0'}}}},axisLabel:{{color:'#94a3b8'}}}}
  }};
}}

// Cards
(function(){{
  var sunH=RAW.daily.sunshine_duration.map(function(s){{return s/3600}});
  var ghi=RAW.daily.shortwave_radiation_sum;
  var sr=RAW.daily.sunrise.map(function(s){{return s.slice(11,16)}});
  var ss=RAW.daily.sunset.map(function(s){{return s.slice(11,16)}});
  var peakG=[],peakW=[],dniH=[];
  for(var d=0;d<N;d++){{
    var sl=d*24;
    peakG.push(Math.max.apply(null,RAW.hourly.shortwave_radiation.slice(sl,sl+24)));
    peakW.push(Math.max.apply(null,RAW.hourly.wind_speed_10m.slice(sl,sl+24)));
    var c=0;
    for(var h=0;h<24;h++){{if(RAW.hourly.direct_radiation[sl+h]>=120)c++}}
    dniH.push(c);
  }}
  var h='';
  for(var d=0;d<N;d++){{
    h+='<div class="card'+(sunH[d]<2?' overcast':'')+'">'+
      '<div class="day">'+DAYS[d]+'</div>'+
      '<div class="date">'+DATES[d]+' '+sr[d]+'-'+ss[d]+'</div>'+
      '<div class="label">日照时长</div><div class="val">'+sunH[d].toFixed(1)+'<span class="unit"> h</span></div>'+
      '<div class="label" style="margin-top:6px">DNI有效时数</div><div class="val small">'+dniH[d]+'<span class="unit"> h</span></div>'+
      '<div class="label" style="margin-top:6px">日总辐照量</div><div class="val small">'+ghi[d].toFixed(1)+'<span class="unit"> MJ/m²</span></div>'+
      '<div class="label" style="margin-top:6px">峰值辐照度</div><div class="val small">'+peakG[d].toFixed(2)+'<span class="unit"> W/m²</span></div>'+
      '<div class="label" style="margin-top:6px">最大风速</div><div class="val small">'+peakW[d].toFixed(2)+'<span class="unit"> km/h</span></div>'+
    '</div>';
  }}
  document.getElementById('cards').innerHTML=h;
}})();

// chart 1: radiation
(function(){{
  var s=[];
  for(var d=0;d<N;d++){{
    s.push({{name:DAYS[d],type:'line',data:slice(d,RAW.hourly.shortwave_radiation),smooth:true,lineStyle:{{color:C[d],width:2}},itemStyle:{{color:C[d]}},symbol:'none',areaStyle:{{color:C[d],opacity:0.08}}}});
  }}
  var opt=Object.assign(theme(),{{
    tooltip:{{trigger:'axis',backgroundColor:'rgba(255,255,255,0.95)',borderColor:'#cbd5e1',textStyle:{{color:'#1e293b'}}}},
    legend:{{top:5,textStyle:{{color:'#64748b',fontSize:11}}}},
    grid:{{left:50,right:20,top:50,bottom:30}},
    xAxis:{{type:'category',data:dayLabels(),axisLabel:{{color:'#94a3b8',fontSize:10,interval:3}},axisLine:{{lineStyle:{{color:'#cbd5e1'}}}}}},
    yAxis:{{type:'value',name:'W/m²',splitLine:{{lineStyle:{{color:'#e2e8f0'}}}},axisLabel:{{color:'#94a3b8'}}}},
    series:s
  }});
  echarts.init(document.getElementById('c1')).setOption(opt);
}})();

// chart 2: daily bar+line
(function(){{
  var sunH=RAW.daily.sunshine_duration.map(function(s){{return +(s/3600).toFixed(1)}});
  var ghi=RAW.daily.shortwave_radiation_sum;
  var opt=Object.assign(theme(),{{
    tooltip:{{trigger:'axis',backgroundColor:'rgba(255,255,255,0.95)',borderColor:'#cbd5e1',textStyle:{{color:'#1e293b'}}}},
    legend:{{top:5,textStyle:{{color:'#64748b',fontSize:11}}}},
    grid:{{left:55,right:55,top:50,bottom:30}},
    xAxis:{{type:'category',data:DAYS,axisLabel:{{color:'#94a3b8',fontSize:10,rotate:20}},axisLine:{{lineStyle:{{color:'#cbd5e1'}}}}}},
    yAxis:[
      {{type:'value',name:'h',splitLine:{{show:false}},axisLabel:{{color:'#94a3b8'}},min:0}},
      {{type:'value',name:'MJ/m²',splitLine:{{show:false}},axisLabel:{{color:'#94a3b8'}},min:0}}
    ],
    series:[
      {{name:'日照时长',type:'bar',data:sunH,itemStyle:{{color:'#fbbf24',borderRadius:[4,4,0,0]}},barWidth:'40%',yAxisIndex:0,label:{{show:true,position:'top',color:'#92400e',fontSize:11,formatter:function(p){{return p.value+'h'}}}}}},
      {{name:'日总辐照量',type:'line',data:ghi,yAxisIndex:1,lineStyle:{{color:'#f97316',width:2}},itemStyle:{{color:'#f97316'}},symbol:'circle',symbolSize:8,label:{{show:true,position:'top',color:'#c2410c',fontSize:11,distance:15,formatter:function(p){{return p.value.toFixed(1)}}}}}}
    ]
  }});
  echarts.init(document.getElementById('c2')).setOption(opt);
}})();

// chart 3: wind
(function(){{
  var s=[];
  for(var d=0;d<N;d++){{
    s.push({{name:DAYS[d]+' 10m',type:'line',data:slice(d,RAW.hourly.wind_speed_10m),smooth:true,lineStyle:{{color:C[d],width:2}},symbol:'none'}});
    s.push({{name:DAYS[d]+' 100m',type:'line',data:slice(d,RAW.hourly.wind_speed_100m),smooth:true,lineStyle:{{color:C[d],width:1,type:'dashed'}},symbol:'none'}});
  }}
  var opt=Object.assign(theme(),{{
    tooltip:{{trigger:'axis',backgroundColor:'rgba(255,255,255,0.95)',borderColor:'#cbd5e1',textStyle:{{color:'#1e293b'}}}},
    legend:{{top:5,type:'scroll',textStyle:{{color:'#64748b',fontSize:10}}}},
    grid:{{left:50,right:20,top:60,bottom:30}},
    xAxis:{{type:'category',data:dayLabels(),axisLabel:{{color:'#94a3b8',fontSize:10,interval:3}},axisLine:{{lineStyle:{{color:'#cbd5e1'}}}}}},
    yAxis:{{type:'value',name:'km/h',splitLine:{{lineStyle:{{color:'#e2e8f0'}}}},axisLabel:{{color:'#94a3b8'}}}},
    series:s
  }});
  echarts.init(document.getElementById('c3')).setOption(opt);
}})();

// chart 4: temp + humidity
(function(){{
  var s=[];
  for(var d=0;d<N;d++){{
    s.push({{name:DAYS[d]+' 温度',type:'line',data:slice(d,RAW.hourly.temperature_2m),smooth:true,lineStyle:{{color:C[d],width:2}},symbol:'none',yAxisIndex:0}});
  }}
  s.push({{name:'湿度',type:'line',data:slice(0,RAW.hourly.relative_humidity_2m),smooth:true,lineStyle:{{color:'#06b6d4',width:1.5,type:'dotted'}},symbol:'none',yAxisIndex:1}});
  var opt=Object.assign(theme(),{{
    tooltip:{{trigger:'axis',backgroundColor:'rgba(255,255,255,0.95)',borderColor:'#cbd5e1',textStyle:{{color:'#1e293b'}}}},
    legend:{{top:5,type:'scroll',textStyle:{{color:'#64748b',fontSize:10}}}},
    grid:{{left:50,right:55,top:60,bottom:30}},
    xAxis:{{type:'category',data:dayLabels(),axisLabel:{{color:'#94a3b8',fontSize:10,interval:3}},axisLine:{{lineStyle:{{color:'#cbd5e1'}}}}}},
    yAxis:[
      {{type:'value',name:'°C',splitLine:{{lineStyle:{{color:'#e2e8f0'}}}},axisLabel:{{color:'#94a3b8'}}}},
      {{type:'value',name:'%',splitLine:{{show:false}},axisLabel:{{color:'#94a3b8'}},min:0,max:100}}
    ],
    series:s
  }});
  echarts.init(document.getElementById('c4')).setOption(opt);
}})();

// chart 5: cloud heatmap
(function(){{
  var d=[];
  for(var i=0;i<N;i++){{
    for(var h=0;h<24;h++){{d.push([h,i,RAW.hourly.cloud_cover[i*24+h]])}}
  }}
  var opt=Object.assign(theme(),{{
    tooltip:{{backgroundColor:'rgba(255,255,255,0.95)',borderColor:'#cbd5e1',textStyle:{{color:'#1e293b'}},formatter:function(p){{return DAYS[p.value[1]]+' '+('0'+p.value[0]).slice(-2)+':00<br/>云量: <b>'+p.value[2]+'%</b>'}}}},
    grid:{{left:80,right:30,top:10,bottom:30}},
    xAxis:{{type:'category',data:dayLabels(),axisLabel:{{color:'#94a3b8',fontSize:10,interval:2}},axisLine:{{lineStyle:{{color:'#cbd5e1'}}}},position:'bottom'}},
    yAxis:{{type:'category',data:DAYS,axisLabel:{{color:'#64748b',fontSize:11}},axisLine:{{lineStyle:{{color:'#cbd5e1'}}}}}},
    visualMap:{{min:0,max:100,calculable:true,orient:'vertical',right:5,top:'center',inRange:{{color:['#f1f5f9','#0f766e','#eab308','#f97316','#94a3b8']}},textStyle:{{color:'#64748b'}}}},
    series:[{{type:'heatmap',data:d,label:{{show:false}},emphasis:{{itemStyle:{{shadowBlur:10,shadowColor:'rgba(0,0,0,0.5)'}}}}}}]
  }});
  echarts.init(document.getElementById('c5')).setOption(opt);
}})();

window.addEventListener('resize',function(){{
  ['c1','c2','c3','c4','c5'].forEach(function(id){{
    var dom=document.getElementById(id);if(dom){{var inst=echarts.getInstanceByDom(dom);if(inst)inst.resize()}}
  }});
}});
</script>
</body>
</html>'''

BASE = os.path.dirname(os.path.abspath(__file__))
out_path = os.path.join(BASE, f'{date_range}周气象预报.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved: {out_path}')
print(f'Size: {len(html):,} bytes')
print(f'Dates: {dates[0]} ~ {dates[-1]}')