"""Generate two HTML files for 火电出清-台数-电价 analysis, July 1-9."""
import json, os, pymysql
from datetime import datetime

conn = pymysql.connect(host='rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com', port=3306,
    user='pengyiqiang', password='pengyiqiang123', database='tianrun_new',
    charset='utf8mb4', connect_timeout=10, read_timeout=60)
cur = conn.cursor()

DATES = ['2026-07-01','2026-07-02','2026-07-03','2026-07-04','2026-07-05','2026-07-06','2026-07-07','2026-07-08','2026-07-09']
TIMES = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0,15,30,45)]
COLORS = ['#0078d4','#d13438','#107c10','#f2a900','#9a60b4','#5470c6','#d83b01','#73c0de','#fc8452']

th = {}; th_num = {}; da_p = {}
for d in DATES:
    cur.execute('SELECT thermal_clearing, thermal_number FROM shandong_px_dayahead_clearing_quantity_number WHERE date=%s ORDER BY time_point', (d,))
    rows = cur.fetchall()
    th[d] = [float(r[0] or 0)*4 for r in rows]
    th_num[d] = [float(r[1] or 0) for r in rows]
    cur.execute("SELECT price FROM shandong_px_reliable_clearing_unit_data WHERE date=%s AND member_id='b9e64e64a713458eba94c9af05c0a757' AND unit_name NOT LIKE '%%发电%%' AND unit_name NOT LIKE '%%用电%%' ORDER BY time_point", (d,))
    rows = cur.fetchall()
    da_p[d] = [float(r[0] or 0) for r in rows] if rows else [0]*96
cur.close(); conn.close()

labels = [d[5:] for d in DATES]

# === File 1: All-in-one overlay ===
s1 = ''
for i, d in enumerate(DATES):
    c = COLORS[i]
    s1 += f'{{name:"{labels[i]} 火电",type:"line",data:{json.dumps(th[d])},smooth:true,lineStyle:{{width:1.5,color:"{c}"}},itemStyle:{{color:"{c}"}},symbol:"none"}},'
    s1 += f'{{name:"{labels[i]} 台数",type:"line",data:{json.dumps(th_num[d])},smooth:false,step:"end",lineStyle:{{width:1,color:"{c}",type:"dotted"}},itemStyle:{{color:"{c}"}},symbol:"none",yAxisIndex:1}},'
s1 += f'{{name:"日前电价(0701)",type:"line",data:{json.dumps(da_p[DATES[0]])},smooth:true,lineStyle:{{width:2.5,color:"#e67e22"}},itemStyle:{{color:"#e67e22"}},symbol:"none",yAxisIndex:2}}'

leg1 = ','.join(f'"{labels[i]} 火电","{labels[i]} 台数"' for i in range(9)) + ',"日前电价(0701)"'

html1 = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>火电出清 & 台数 & 电价 | 7月1-9日</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}}
.header{{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600;margin-bottom:4px}}
.header .info{{font-size:11px;color:#888}}
.charts{{padding:8px 24px}}
.panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.panel .t{{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.panel .c{{width:100%;height:550px}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
</style>
</head>
<body>
<div class="header">
<h1>火电日前出清 & 开机台数 & 日前电价 | 7月1日 ~ 9日</h1>
<div class="info">数据来源：天机库 · 火电出清=thermal_clearing×4(MW) · 右轴台数(虚线) · 右轴电价(仅0701参考)</div>
</div>
<div class="charts">
<div class="panel"><div class="t">9天叠加对比 — 火电出清(MW) + 台数 + 日前电价(元/MWh)</div><div class="c" id="c1"></div></div>
</div>
<div class="footer">润津储能 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<script>
var T={json.dumps(TIMES, ensure_ascii=False)};
var g={{left:55,right:80,top:20,bottom:40}};
var ec={{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var ec2={{axisLabel:{{color:'#2c7be5',fontSize:10}},axisLine:{{lineStyle:{{color:'#2c7be5'}}}},splitLine:{{show:false}}}};
var ec3={{axisLabel:{{color:'#e67e22',fontSize:10}},axisLine:{{lineStyle:{{color:'#e67e22'}}}},splitLine:{{show:false}}}};
var el={{textStyle:{{color:'#666',fontSize:10}},top:3}};
var xA=Object.assign({{type:'category',data:T,axisLabel:{{interval:7}}}},ec);
var c1=echarts.init(document.getElementById('c1'));
c1.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:[{leg1}],type:'scroll',bottom:0}},el),xAxis:xA,yAxis:[Object.assign({{type:'value',name:'MW'}},ec),Object.assign({{type:'value',name:'台',min:65,max:105}},ec2),Object.assign({{type:'value',name:'元/MWh'}},ec3)],series:[{s1}]}});
window.addEventListener('resize',function(){{c1.resize();}});
</script>
</body>
</html>'''

OUT1 = 'E:/DataWork/Storage_Strategy/output/火电出清_台数_电价_7月_叠加.html'
with open(OUT1, 'w', encoding='utf-8') as f: f.write(html1)
print(f'File 1: {OUT1} ({os.path.getsize(OUT1):,} bytes)')

# === File 2: Single-day with keyboard nav ===
html2 = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>火电出清 & 台数 & 电价 | 7月 逐日</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}}
.header{{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600}}
.nav{{display:flex;align-items:center;gap:10px;font-size:13px}}
.nav button{{padding:6px 16px;border:1px solid #c8c8c8;border-radius:4px;cursor:pointer;background:#fff;font-size:13px}}
.nav button:hover{{background:#e5f3ff;border-color:#0078d4}}
.nav select{{padding:5px 10px;border:1px solid #c8c8c8;border-radius:4px;font-size:13px}}
.nav .current{{font-weight:700;font-size:16px;color:#0078d4;min-width:60px;text-align:center}}
.stats{{display:flex;gap:8px;padding:8px 24px;flex-wrap:wrap}}
.stat{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:10px 14px;min-width:120px;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.stat .l{{font-size:10px;color:#888}}
.stat .v{{font-size:18px;font-weight:600;color:#2c7be5}}
.charts{{padding:8px 24px}}
.panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.panel .t{{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.panel .c{{width:100%;height:500px}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
</style>
</head>
<body>
<div class="header">
<h1>火电日前出清 & 开机台数 & 日前电价 | 逐日</h1>
<div class="nav">
<button onclick="prevDay()">◀</button>
<span class="current" id="curLabel">0701</span>
<button onclick="nextDay()">▶</button>
<select id="dateSelect" onchange="jumpTo()"></select>
</div>
</div>
<div class="stats" id="statsBar"></div>
<div class="charts">
<div class="panel"><div class="t" id="chartTitle">火电出清(MW) + 台数 + 日前电价(元/MWh)</div><div class="c" id="c1"></div></div>
</div>
<div class="footer">润津储能 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} · 键盘 ← → 切换日期</div>
<script>
var T={json.dumps(TIMES, ensure_ascii=False)};
var DATES={json.dumps(DATES)};
var LABELS={json.dumps(labels)};
var TH={json.dumps(th)};
var TH_NUM={json.dumps(th_num)};
var DA_P={json.dumps(da_p)};

var curIdx=0;
var g={{left:55,right:80,top:20,bottom:40}};
var ec={{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var ec2={{axisLabel:{{color:'#2c7be5',fontSize:10}},axisLine:{{lineStyle:{{color:'#2c7be5'}}}},splitLine:{{show:false}}}};
var ec3={{axisLabel:{{color:'#e67e22',fontSize:10}},axisLine:{{lineStyle:{{color:'#e67e22'}}}},splitLine:{{show:false}}}};
var el={{textStyle:{{color:'#666',fontSize:10}},top:3}};
var xA=Object.assign({{type:'category',data:T,axisLabel:{{interval:7}}}},ec);

var sel=document.getElementById('dateSelect');
DATES.forEach(function(d,i){{var o=document.createElement('option');o.value=i;o.textContent=LABELS[i];sel.appendChild(o);}});

function render(d){{
var thnMin=Math.min.apply(null,TH_NUM[d]);var thnMax=Math.max.apply(null,TH_NUM[d]);
var thnYmin=Math.max(0,thnMin-5);var thnYmax=Math.min(100,thnMax+5);
c1.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:['火电出清','开机台数','日前电价']}},el),xAxis:xA,
yAxis:[Object.assign({{type:'value',name:'MW'}},ec),Object.assign({{type:'value',name:'台',min:thnYmin,max:thnYmax}},ec2),Object.assign({{type:'value',name:'元/MWh'}},ec3)],
series:[
{{name:'火电出清',type:'bar',data:TH[d],barWidth:3,itemStyle:{{color:'#d13438'}}}},
{{name:'开机台数',type:'line',data:TH_NUM[d],smooth:false,step:'end',lineStyle:{{width:2,color:'#0078d4'}},itemStyle:{{color:'#0078d4'}},symbol:'none',yAxisIndex:1}},
{{name:'日前电价',type:'line',data:DA_P[d],smooth:true,lineStyle:{{width:2,color:'#e67e22'}},itemStyle:{{color:'#e67e22'}},symbol:'none',yAxisIndex:2}}
]}},true);
var thAvg=TH[d].reduce(function(a,b){{return a+b;}},0)/96;
var thnAvg=TH_NUM[d].reduce(function(a,b){{return a+b;}},0)/96;
var prAvg=DA_P[d].reduce(function(a,b){{return a+b;}},0)/96;
var prMin=Math.min.apply(null,DA_P[d]);var prMax=Math.max.apply(null,DA_P[d]);
document.getElementById('statsBar').innerHTML=
'<div class="stat"><div class="l">火电出清均值</div><div class="v">'+thAvg.toFixed(0)+' MW</div></div>'+
'<div class="stat"><div class="l">开机台数均值</div><div class="v">'+thnAvg.toFixed(1)+' 台</div><div class="s">'+thnMin+'~'+thnMax+'台</div></div>'+
'<div class="stat"><div class="l">日前电价均值</div><div class="v">'+prAvg.toFixed(0)+' 元/MWh</div><div class="s">'+prMin.toFixed(0)+'~'+prMax.toFixed(0)+'元</div></div>';
document.getElementById('chartTitle').innerHTML='火电出清(MW) + 台数 + 日前电价(元/MWh) — '+LABELS[curIdx];
document.getElementById('curLabel').textContent=LABELS[curIdx];
sel.value=curIdx;
}}

function prevDay(){{if(curIdx>0){{curIdx--;render(DATES[curIdx]);}}}}
function nextDay(){{if(curIdx<DATES.length-1){{curIdx++;render(DATES[curIdx]);}}}}
function jumpTo(){{curIdx=parseInt(sel.value);render(DATES[curIdx]);}}
document.addEventListener('keydown',function(e){{if(e.key==='ArrowLeft')prevDay();if(e.key==='ArrowRight')nextDay();}});

var c1=echarts.init(document.getElementById('c1'));
render(DATES[0]);
window.addEventListener('resize',function(){{c1.resize();}});
</script>
</body>
</html>'''

OUT2 = 'E:/DataWork/Storage_Strategy/output/火电出清_台数_电价_7月_逐日.html'
with open(OUT2, 'w', encoding='utf-8') as f: f.write(html2)
print(f'File 2: {OUT2} ({os.path.getsize(OUT2):,} bytes)')