"""Analyze 火电出清 vs 电价 relationship for 0628-0708."""
import json, os, pymysql
from datetime import datetime

DATES = ['2026-06-28','2026-06-29','2026-06-30','2026-07-01','2026-07-02','2026-07-03','2026-07-04','2026-07-05','2026-07-06','2026-07-07','2026-07-08']
TIMES = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0,15,30,45)]

conn = pymysql.connect(host='rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com', port=3306,
    user='pengyiqiang', password='pengyiqiang123', database='tianrun_new',
    charset='utf8mb4', connect_timeout=10, read_timeout=60)
cur = conn.cursor()

# ── 1. 火电日前出清 (MWh→MW) ──
th_da = {}  # {date: [96 MW values]}
for d in DATES:
    cur.execute('SELECT thermal_clearing FROM shandong_px_dayahead_clearing_quantity_number WHERE date=%s ORDER BY time_point', (d,))
    rows = cur.fetchall()
    th_da[d] = [float(r[0] or 0) * 4 for r in rows] if rows else [0]*96

# ── 2. 日前电价 ──
da_price = {}
for d in DATES:
    cur.execute("SELECT price FROM shandong_px_reliable_clearing_unit_data WHERE date=%s AND member_id='b9e64e64a713458eba94c9af05c0a757' AND unit_name NOT LIKE '%%发电%%' AND unit_name NOT LIKE '%%用电%%' ORDER BY time_point", (d,))
    rows = cur.fetchall()
    da_price[d] = [float(r[0] or 0) for r in rows] if rows else [0]*96

# ── 3. Actual data for thermal actual computation ──
ac = {}
for d in DATES:
    cur.execute('''SELECT actual_dispatched_load, actual_tie_line_load, actual_wind_power,
        actual_photovoltaic_power, actual_nuclear_power, actual_pumped_storage_power,
        actual_local_power, actual_self_power
        FROM shandong_px_spot_actual_load_info WHERE date=%s ORDER BY time_order''', (d,))
    rows = cur.fetchall()
    if rows:
        ac[d] = {
            'dispatched': [float(r[0] or 0) for r in rows],
            'tie_line': [float(r[1] or 0) for r in rows],
            'wind': [float(r[2] or 0) for r in rows],
            'pv': [float(r[3] or 0) for r in rows],
            'nuclear': [float(r[4] or 0) for r in rows],
            'pumped': [float(r[5] or 0) for r in rows],
            'local': [float(r[6] or 0) for r in rows],
            'self': [float(r[7] or 0) for r in rows],
        }

# ── 4. 日前储能出清 ──
es_da = {}
for d in DATES:
    cur.execute('SELECT independent_clearing FROM shandong_px_dayahead_clearing_quantity_number WHERE date=%s ORDER BY time_point', (d,))
    rows = cur.fetchall()
    es_da[d] = [float(r[0] or 0) * 4 for r in rows] if rows else [0]*96

# ── 5. 实时电价 ──
rt_price = {}
for d in DATES:
    cur.execute("SELECT price FROM shandong_px_realtime_clearing_results_query WHERE date=%s AND member_id='b9e64e64a713458eba94c9af05c0a757' ORDER BY time_point", (d,))
    rows = cur.fetchall()
    rt_price[d] = [float(r[0] or 0) for r in rows] if rows else [0]*96

cur.close(); conn.close()

# ── 6. Compute 火电实际出清 = 实际(直调-联络-风-光-核-抽蓄-地方-自备) - 日前储能 ──
th_actual = {}
for d in DATES:
    if d in ac and d in es_da:
        th_actual[d] = [
            ac[d]['dispatched'][i] - ac[d]['tie_line'][i] - ac[d]['wind'][i]
            - ac[d]['pv'][i] - ac[d]['nuclear'][i]
            - ac[d]['pumped'][i] - ac[d]['local'][i] - ac[d]['self'][i]
            - es_da[d][i]
            for i in range(96)
        ]

# ── 7. Compute correlations ──
import math
def pearson(x, y):
    n = len(x)
    mx = sum(x)/n; my = sum(y)/n
    num = sum((x[i]-mx)*(y[i]-my) for i in range(n))
    dx = math.sqrt(sum((v-mx)**2 for v in x))
    dy = math.sqrt(sum((v-my)**2 for v in y))
    return num/(dx*dy) if dx and dy else 0

stats = []
for d in DATES:
    if d in th_actual and d in rt_price:
        corr_da = pearson(th_da[d], da_price[d])
        corr_rt = pearson(th_actual[d], rt_price[d])
        avg_th_da = sum(th_da[d])/96
        avg_price_da = sum(da_price[d])/96
        avg_th_ac = sum(th_actual[d])/96
        avg_price_rt = sum(rt_price[d])/96
        stats.append({
            'date': d[5:],
            'corr_da': round(corr_da, 4),
            'corr_rt': round(corr_rt, 4),
            'avg_th_da': round(avg_th_da, 0),
            'avg_price_da': round(avg_price_da, 0),
            'avg_th_ac': round(avg_th_ac, 0),
            'avg_price_rt': round(avg_price_rt, 0),
        })

# ── Build scatter data ──
scatter_da = {'dates': [], 'x': [], 'y': []}  # all 96*11 points
scatter_rt = {'dates': [], 'x': [], 'y': []}
for d in DATES:
    if d in th_actual:
        for i in range(96):
            scatter_da['dates'].append(d[5:])
            scatter_da['x'].append(th_da[d][i])
            scatter_da['y'].append(da_price[d][i])
            scatter_rt['dates'].append(d[5:])
            scatter_rt['x'].append(th_actual[d][i])
            scatter_rt['y'].append(rt_price[d][i])

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>火电出清与电价关系分析 | 0628-0708</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}}
.header{{background:#fff;padding:12px 24px;border-bottom:1px solid #d9d9d9;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600;margin-bottom:4px}}
.header .info{{font-size:11px;color:#888}}
.stats{{display:flex;gap:8px;padding:8px 24px;flex-wrap:wrap}}
.stat{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:10px 14px;min-width:130px;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.stat .l{{font-size:10px;color:#888}}
.stat .v{{font-size:18px;font-weight:600;color:#2c7be5}}
.stat .s{{font-size:10px;color:#aaa}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:8px 24px}}
@media(max-width:1200px){{.charts{{grid-template-columns:1fr}}}}
.panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.panel .t{{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.panel .c{{width:100%;height:420px}}
.panel.full{{grid-column:1/-1}}
.panel.full .c{{height:450px}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
table{{width:100%;border-collapse:collapse;font-size:11px;margin:8px 0}}
table th{{background:#f5f5f5;color:#333;padding:6px 8px;text-align:center;border-bottom:2px solid #e0e0e0}}
table td{{padding:5px 8px;border-bottom:1px solid #f0f0f0;text-align:center}}
table tr:hover td{{background:#e5f3ff}}
.pos{{color:#d13438}} .neg{{color:#107c10}}
</style>
</head>
<body>
<div class="header">
<h1>火电出清与电价关系分析 | 0628 ~ 0708</h1>
<div class="info">数据来源：天机库 · 火电日前出清 = thermal_clearing×4(MW) · 火电实际出清 = 实际(直调-联络线-风光核-抽蓄-地方) - 日前储能</div>
</div>
<div class="charts">
<div class="panel full"><div class="t">火电日前出清 vs 日前电价 — 散点图（96点/天）</div><div class="c" id="c1"></div></div>
<div class="panel full"><div class="t">火电实际出清 vs 实时电价 — 散点图（96点/天）</div><div class="c" id="c2"></div></div>
<div class="panel"><div class="t">火电日前出清 + 日前电价 — 时序对比（MW / 元/MWh）</div><div class="c" id="c3"></div></div>
<div class="panel"><div class="t">火电实际出清 + 实时电价 — 时序对比（MW / 元/MWh）</div><div class="c" id="c4"></div></div>
<div class="panel full"><div class="t">每日相关系数汇总</div><div class="c" id="c5"></div></div>
</div>
<div class="footer">润津储能 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<script>
var T={json.dumps(TIMES, ensure_ascii=False)};
var DATES={json.dumps(DATES, ensure_ascii=False)};
var TH_DA={json.dumps(th_da)};
var DA_P={json.dumps(da_price)};
var TH_AC={json.dumps(th_actual)};
var RT_P={json.dumps(rt_price)};
var STATS={json.dumps(stats)};
var SCATTER_DA={json.dumps(scatter_da)};
var SCATTER_RT={json.dumps(scatter_rt)};

var g={{left:65,right:20,top:20,bottom:40}};
var g2={{left:55,right:70,top:20,bottom:35}};
var ec={{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var ec2={{axisLabel:{{color:'#e67e22',fontSize:10}},axisLine:{{lineStyle:{{color:'#e67e22'}}}},splitLine:{{show:false}}}};
var el={{textStyle:{{color:'#666',fontSize:10}},top:3}};
var xA=Object.assign({{type:'category',data:T,axisLabel:{{interval:7}}}},ec);

var COLORS=['#0078d4','#d13438','#107c10','#f2a900','#9a60b4','#5470c6','#d83b01','#73c0de','#fc8452','#3ba272','#e67e22'];

// Scatter chart 1: 日前
var c1=echarts.init(document.getElementById('c1'));
var s1=[];
DATES.forEach(function(d,i){{
  if(!TH_DA[d]||!DA_P[d]) return;
  var c=COLORS[i%COLORS.length];
  var data=TH_DA[d].map(function(v,j){{return [v,DA_P[d][j]];}});
  s1.push({{name:d.slice(5),type:'scatter',data:data,symbolSize:4,itemStyle:{{color:c,opacity:0.5}}}});
}});
c1.setOption({{grid:g,tooltip:{{trigger:'item',formatter:function(p){{return p.seriesName+'<br/>火电: '+p.value[0].toFixed(0)+' MW<br/>电价: '+p.value[1].toFixed(0)+' 元/MWh';}}}},legend:Object.assign({{data:DATES.map(function(d){{return d.slice(5);}}),type:'scroll',bottom:0}},el),xAxis:Object.assign({{type:'value',name:'火电日前出清 (MW)'}},ec),yAxis:Object.assign({{type:'value',name:'日前电价 (元/MWh)'}},ec),series:s1}});

// Scatter chart 2: 实际
var c2=echarts.init(document.getElementById('c2'));
var s2=[];
DATES.forEach(function(d,i){{
  if(!TH_AC[d]||!RT_P[d]) return;
  var c=COLORS[i%COLORS.length];
  var data=TH_AC[d].map(function(v,j){{return [v,RT_P[d][j]];}});
  s2.push({{name:d.slice(5),type:'scatter',data:data,symbolSize:4,itemStyle:{{color:c,opacity:0.5}}}});
}});
c2.setOption({{grid:g,tooltip:{{trigger:'item',formatter:function(p){{return p.seriesName+'<br/>火电: '+p.value[0].toFixed(0)+' MW<br/>电价: '+p.value[1].toFixed(0)+' 元/MWh';}}}},legend:Object.assign({{data:DATES.map(function(d){{return d.slice(5);}}),type:'scroll',bottom:0}},el),xAxis:Object.assign({{type:'value',name:'火电实际出清 (MW)'}},ec),yAxis:Object.assign({{type:'value',name:'实时电价 (元/MWh)'}},ec),series:s2}});

// Chart 3: 火电日前 + 日前电价 时序
var fd=DATES[DATES.length-1];
var c3=echarts.init(document.getElementById('c3'));
var s3=[];
DATES.forEach(function(d,i){{
  if(!TH_DA[d]) return;
  var c=COLORS[i%COLORS.length];
  s3.push({{name:d.slice(5)+' 火电',type:'line',data:TH_DA[d],smooth:true,lineStyle:{{width:1.5,color:c}},itemStyle:{{color:c}},symbol:'none'}});
}});
if(DA_P[fd]) s3.push({{name:'日前电价',type:'line',data:DA_P[fd],smooth:true,lineStyle:{{width:2.5,color:'#d13438'}},itemStyle:{{color:'#d13438'}},symbol:'none',yAxisIndex:1}});
c3.setOption({{grid:g2,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:s3.map(function(x){{return x.name;}}),type:'scroll',bottom:0}},el),xAxis:xA,yAxis:[Object.assign({{type:'value',name:'MW'}},ec),Object.assign({{type:'value',name:'元/MWh'}},ec2)],series:s3}});

// Chart 4: 火电实际 + 实时电价 时序
var c4=echarts.init(document.getElementById('c4'));
var s4=[];
DATES.forEach(function(d,i){{
  if(!TH_AC[d]) return;
  var c=COLORS[i%COLORS.length];
  s4.push({{name:d.slice(5)+' 火电',type:'line',data:TH_AC[d],smooth:true,lineStyle:{{width:1.5,color:c}},itemStyle:{{color:c}},symbol:'none'}});
}});
if(RT_P[fd]) s4.push({{name:'实时电价',type:'line',data:RT_P[fd],smooth:true,lineStyle:{{width:2.5,color:'#d13438'}},itemStyle:{{color:'#d13438'}},symbol:'none',yAxisIndex:1}});
c4.setOption({{grid:g2,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:s4.map(function(x){{return x.name;}}),type:'scroll',bottom:0}},el),xAxis:xA,yAxis:[Object.assign({{type:'value',name:'MW'}},ec),Object.assign({{type:'value',name:'元/MWh'}},ec2)],series:s4}});

// Chart 5: 相关系数柱状图
var c5=echarts.init(document.getElementById('c5'));
var daCors=STATS.map(function(s){{return s.corr_da;}});
var rtCors=STATS.map(function(s){{return s.corr_rt;}});
var dateLabels=STATS.map(function(s){{return s.date;}});
c5.setOption({{grid:{{left:55,right:55,top:20,bottom:60}},tooltip:{{trigger:'axis'}},legend:Object.assign({{data:['火电日前-日前电价 相关系数','火电实际-实时电价 相关系数']}},el),xAxis:Object.assign({{type:'category',data:dateLabels,axisLabel:{{rotate:45}}}},ec),yAxis:Object.assign({{type:'value',name:'Pearson r',min:-1,max:1}},ec),series:[
  {{name:'火电日前-日前电价 相关系数',type:'bar',data:daCors,barWidth:15,itemStyle:{{color:'#0078d4'}},label:{{show:true,position:'top',fontSize:10,formatter:function(p){{return p.value.toFixed(3);}}}}}},
  {{name:'火电实际-实时电价 相关系数',type:'bar',data:rtCors,barWidth:15,itemStyle:{{color:'#d13438'}},label:{{show:true,position:'bottom',fontSize:10,formatter:function(p){{return p.value.toFixed(3);}}}}}}
]}});

window.addEventListener('resize',function(){{c1.resize();c2.resize();c3.resize();c4.resize();c5.resize();}});
</script>
</body>
</html>'''

OUT = 'E:/DataWork/Storage_Strategy/output/火电出清_电价关系分析_0628-0708.html'
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)

# Print summary
print(f'Saved: {OUT} ({os.path.getsize(OUT):,} bytes)')
print()
print(f'{"日期":>6}  {"日前r":>8}  {"实时r":>8}  {"日前火电均值":>12}  {"日前电价均值":>12}  {"实际火电均值":>12}  {"实时电价均值":>12}')
print('-' * 80)
for s in stats:
    print(f'{s["date"]:>6}  {s["corr_da"]:>8.4f}  {s["corr_rt"]:>8.4f}  {s["avg_th_da"]:>10.0f} MW  {s["avg_price_da"]:>10.0f}   {s["avg_th_ac"]:>10.0f} MW  {s["avg_price_rt"]:>10.0f}')