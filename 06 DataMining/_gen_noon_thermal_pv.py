"""Generate 2026 noon thermal vs PV analysis HTML."""
import json, os, sqlite3, pymysql
from datetime import datetime
from statistics import mean, stdev

conn = pymysql.connect(host='rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com', port=3306,
    user='pengyiqiang', password='pengyiqiang123', database='tianrun_new',
    charset='utf8mb4', connect_timeout=10, read_timeout=120)
cur = conn.cursor()

# Noon period: 11:00-13:00
cur.execute('''SELECT date, AVG(thermal_clearing)*4 as th_mw, AVG(thermal_number) as th_num
    FROM shandong_px_dayahead_clearing_quantity_number
    WHERE date >= '2026-01-01' AND time_point >= '11:00' AND time_point <= '13:00'
    GROUP BY date ORDER BY date''')
clr = [(str(r[0]), float(r[1]), float(r[2])) for r in cur.fetchall()]
cur.close(); conn.close()

db = sqlite3.connect('E:/DataWork/Storage_Strategy/data/cache/local.db')
cur2 = db.cursor()
cur2.execute('''SELECT date, AVG(photovoltaic_power) as pv_mw
    FROM bidding_space_forecast WHERE date >= '2026-01-01' AND time_order BETWEEN 45 AND 52
    GROUP BY date ORDER BY date''')
pv = {r[0]: float(r[1]) for r in cur2.fetchall()}
db.close()

dates = [d for d,_,_ in clr if d in pv]
th_mw = [t for d,t,_ in clr if d in pv]
th_num = [n for d,_,n in clr if d in pv]
pv_mw = [pv[d] for d in dates]
months = [d[5:7] for d in dates]
mo_labels = [d[5:] for d in dates]

MONTH_NAMES = {str(i).zfill(2): f'{i}月' for i in range(1,13)}
MONTH_COLORS = ['#5470c6','#73c0de','#3ba272','#fc8452','#9a60b4','#d13438','#f2a900']

n = len(dates)
print(f'Days: {n}')
print(f'中午火电: {mean(th_mw):.0f}±{stdev(th_mw):.0f} MW  台数: {mean(th_num):.1f}±{stdev(th_num):.1f}  光伏: {mean(pv_mw):.0f}±{stdev(pv_mw):.0f} MW')

for m in sorted(set(months)):
    idxs = [i for i,mm in enumerate(months) if mm==m]
    print(f'  {MONTH_NAMES[m]}: 火电={mean(th_mw[i] for i in idxs):.0f}MW 台数={mean(th_num[i] for i in idxs):.1f}台 光伏={mean(pv_mw[i] for i in idxs):.0f}MW')

# Scatter series
mos = sorted(set(months))
scatter_series = ''
for m in mos:
    idxs = [i for i,mm in enumerate(months) if mm==m]
    data = [[th_mw[i], pv_mw[i], dates[i][5:]] for i in idxs]
    c = MONTH_COLORS[int(m)-1]
    scatter_series += f'{{name:"{MONTH_NAMES[m]}",type:"scatter",data:{json.dumps(data)},symbolSize:6,itemStyle:{{color:"{c}",opacity:0.7}}}},'

# Monthly stats
mo_th_avg = [mean(th_mw[i] for i in [j for j,mm in enumerate(months) if mm==m]) for m in mos]
mo_th_std = [stdev(th_mw[i] for i in [j for j,mm in enumerate(months) if mm==m]) for m in mos]
mo_num_avg = [mean(th_num[i] for i in [j for j,mm in enumerate(months) if mm==m]) for m in mos]
mo_pv_avg = [mean(pv_mw[i] for i in [j for j,mm in enumerate(months) if mm==m]) for m in mos]
mo_labels = [MONTH_NAMES[m] for m in mos]

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>2026年 中午时段火电-光伏关系分析</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}}
.header{{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
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
</style>
</head>
<body>
<div class="header">
<h1>2026年 中午时段(11:00-13:00)火电-光伏关系分析</h1>
<div class="info">数据来源：天机库 · {n}天 · 1月1日 ~ 7月9日 · 中午=11:00-13:00时段均值</div>
</div>
<div class="stats">
<div class="stat"><div class="l">天数</div><div class="v">{n} 天</div></div>
<div class="stat"><div class="l">火电出清均值</div><div class="v">{mean(th_mw):.0f} MW</div><div class="s">±{stdev(th_mw):.0f} MW</div></div>
<div class="stat"><div class="l">开机台数均值</div><div class="v">{mean(th_num):.1f} 台</div><div class="s">±{stdev(th_num):.1f} 台</div></div>
<div class="stat"><div class="l">光伏出力均值</div><div class="v">{mean(pv_mw):.0f} MW</div><div class="s">±{stdev(pv_mw):.0f} MW</div></div>
</div>
<div class="charts">
<div class="panel full"><div class="t">火电出清 vs 光伏出力 散点图 — 按月着色（中午11:00-13:00均值）</div><div class="c" id="c1"></div></div>
<div class="panel"><div class="t">月度火电出清功率（MW）— 中午时段均值 ± 标准差</div><div class="c" id="c2"></div></div>
<div class="panel"><div class="t">月度开机台数（台）— 中午时段均值</div><div class="c" id="c3"></div></div>
<div class="panel"><div class="t">月度光伏出力（MW）— 中午时段均值</div><div class="c" id="c4"></div></div>
<div class="panel full"><div class="t">火电出清 & 开机台数 & 光伏出力 — 日度时序（中午时段）</div><div class="c" id="c5"></div></div>
</div>
<div class="footer">润津储能 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<script>
var DATES={json.dumps(mo_labels)};
var TH_MW={json.dumps(th_mw)};
var TH_NUM={json.dumps(th_num)};
var PV_MW={json.dumps(pv_mw)};
var MO_TH={json.dumps(mo_th_avg)};
var MO_TH_STD={json.dumps(mo_th_std)};
var MO_NUM={json.dumps(mo_num_avg)};
var MO_PV={json.dumps(mo_pv_avg)};
var MO_LABELS={json.dumps(mo_labels)};

var g={{left:65,right:20,top:20,bottom:40}};
var g2={{left:55,right:55,top:20,bottom:50}};
var ec={{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var ec2={{axisLabel:{{color:'#2c7be5',fontSize:10}},axisLine:{{lineStyle:{{color:'#2c7be5'}}}},splitLine:{{show:false}}}};
var el={{textStyle:{{color:'#666',fontSize:10}},top:3}};

var c1=echarts.init(document.getElementById('c1'));
c1.setOption({{grid:g,tooltip:{{trigger:'item',formatter:function(p){{return p.seriesName+' '+p.value[2]+'<br/>火电: '+p.value[0].toFixed(0)+' MW<br/>光伏: '+p.value[1].toFixed(0)+' MW';}}}},legend:Object.assign({{data:MO_LABELS,top:3}},el),xAxis:Object.assign({{type:'value',name:'火电出清 (MW)'}},ec),yAxis:Object.assign({{type:'value',name:'光伏出力 (MW)'}},ec),series:[{scatter_series}]}});

var c2=echarts.init(document.getElementById('c2'));
c2.setOption({{grid:g,tooltip:{{trigger:'axis'}},xAxis:Object.assign({{type:'category',data:MO_LABELS}},ec),yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:[
  {{name:'火电出清',type:'bar',data:MO_TH.map(function(v,i){{return {{value:v,itemStyle:{{color:['#5470c6','#73c0de','#3ba272','#fc8452','#9a60b4','#d13438','#f2a900'][i]}}}};}}),barWidth:30,label:{{show:true,position:'top',fontSize:10,formatter:function(p){{return p.value.toFixed(0);}}}}}},
  {{name:'±标准差',type:'errorbar',data:MO_TH.map(function(v,i){{return [v-MO_TH_STD[i],v+MO_TH_STD[i]];}}),itemStyle:{{color:'#888'}}}}
]}});

var c3=echarts.init(document.getElementById('c3'));
c3.setOption({{grid:g,tooltip:{{trigger:'axis'}},xAxis:Object.assign({{type:'category',data:MO_LABELS}},ec),yAxis:Object.assign({{type:'value',name:'台'}},ec),series:[
  {{name:'开机台数',type:'bar',data:MO_NUM.map(function(v,i){{return {{value:v,itemStyle:{{color:['#5470c6','#73c0de','#3ba272','#fc8452','#9a60b4','#d13438','#f2a900'][i]}}}};}}),barWidth:30,label:{{show:true,position:'top',fontSize:10,formatter:function(p){{return p.value.toFixed(1);}}}}}}
]}});

var c4=echarts.init(document.getElementById('c4'));
c4.setOption({{grid:g,tooltip:{{trigger:'axis'}},xAxis:Object.assign({{type:'category',data:MO_LABELS}},ec),yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:[
  {{name:'光伏出力',type:'bar',data:MO_PV.map(function(v,i){{return {{value:v,itemStyle:{{color:['#5470c6','#73c0de','#3ba272','#fc8452','#9a60b4','#d13438','#f2a900'][i]}}}};}}),barWidth:30,label:{{show:true,position:'top',fontSize:10,formatter:function(p){{return p.value.toFixed(0);}}}}}}
]}});

var xA=Object.assign({{type:'category',data:DATES,axisLabel:{{interval:9,rotate:30}}}},ec);
var c5=echarts.init(document.getElementById('c5'));
c5.setOption({{grid:g2,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:['火电出清','开机台数','光伏出力']}},el),xAxis:xA,
yAxis:[Object.assign({{type:'value',name:'MW'}},ec),Object.assign({{type:'value',name:'台',min:50,max:130}},ec2)],
series:[
  {{name:'火电出清',type:'line',data:TH_MW,smooth:true,lineStyle:{{width:1.5,color:'#d13438'}},itemStyle:{{color:'#d13438'}},symbol:'none'}},
  {{name:'开机台数',type:'line',data:TH_NUM,smooth:true,lineStyle:{{width:1.5,color:'#0078d4'}},itemStyle:{{color:'#0078d4'}},symbol:'none',yAxisIndex:1}},
  {{name:'光伏出力',type:'line',data:PV_MW,smooth:true,lineStyle:{{width:1.5,color:'#107c10'}},itemStyle:{{color:'#107c10'}},symbol:'none'}}
]}});

window.addEventListener('resize',function(){{c1.resize();c2.resize();c3.resize();c4.resize();c5.resize();}});
</script>
</body>
</html>'''

OUT = 'E:/DataWork/Storage_Strategy/output/火电_光伏_中午时段_2026年分析.html'
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'')
print(f'Saved: {OUT} ({os.path.getsize(OUT):,} bytes)')