"""Generate 日前出清全景 HTML for a given date, using 0605 template style."""
import json, os, sys, pymysql

if len(sys.argv) < 2:
    print('Usage: python _gen_clearing_panorama.py MMDD')
    sys.exit(1)

mmdd = sys.argv[1]
date_str = f'2026-{mmdd[:2]}-{mmdd[2:]}'
title_date = f'2026年{int(mmdd[:2])}月{int(mmdd[2:])}日'

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, f'日前出清全景_{mmdd}.html')

conn = pymysql.connect(host='rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com', port=3306, user='pengyiqiang', password='pengyiqiang123', database='tianrun_new', charset='utf8mb4', connect_timeout=10, read_timeout=30)
cur = conn.cursor()

cur.execute('SELECT time_point, thermal_clearing, thermal_number, nuclear_clearing, new_energy_clearing, independent_clearing, draw_clearing, virtual_clearing FROM shandong_px_dayahead_clearing_quantity_number WHERE date=%s ORDER BY time_point', (date_str,))
rows = cur.fetchall()
if not rows:
    print(f'No clearing_quantity_number data for {date_str}')
    sys.exit(1)
times = [r[0] for r in rows]
thC = [float(r[1]) for r in rows]; thN = [float(r[2]) for r in rows]
nuC = [float(r[3]) for r in rows]; neC = [float(r[4]) for r in rows]
inC = [float(r[5]) for r in rows]; drC = [float(r[6]) for r in rows]
viC = [float(r[7]) for r in rows]

cur.execute("SELECT time_point, price FROM shandong_px_reliable_clearing_unit_data WHERE date=%s AND member_id='b9e64e64a713458eba94c9af05c0a757' ORDER BY time_point", (date_str,))
prows = cur.fetchall()
daP = [float(r[1]) for r in prows] if prows else [0]*96

cur.execute('SELECT time_order, wind_power_forecast, photovoltaic_power_forecast FROM shandong_px_spot_dayahead_load_info WHERE date=%s ORDER BY time_order', (date_str,))
frows = cur.fetchall()
wind_f = [float(r[1]) / 4.0 for r in frows] if frows else [0]*96
pv_f = [float(r[2]) / 4.0 for r in frows] if frows else [0]*96

cur.close(); conn.close()

bs = [thC[i] + nuC[i] + neC[i] + inC[i] + drC[i] + viC[i] for i in range(96)]
bs_mw = [v / 4.0 for v in bs]
thC_mw = [v / 4.0 for v in thC]

T = json.dumps(times, ensure_ascii=False)

html = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>日前出清全景 | __TITLE_DATE__</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}
.header{background:#fff;padding:12px 24px;border-bottom:1px solid #d9d9d9;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.header h1{font-size:18px;color:#0078d4;font-weight:600}
.header .info{font-size:11px;color:#888}
.stats{display:flex;gap:8px;padding:8px 10px 0 10px;flex-wrap:wrap}
.stat{background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:10px 14px;min-width:120px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.stat .l{font-size:10px;color:#888}
.stat .v{font-size:18px;font-weight:600;color:#2c7be5}
.stat .s{font-size:10px;color:#aaa}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:8px}
@media(max-width:1000px){.charts{grid-template-columns:1fr}}
.panel{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.panel .t{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}
.panel .c{width:100%;height:400px}
.panel.full{grid-column:1/-1}
.panel.full .c{height:380px}
.footer{text-align:center;padding:8px;font-size:10px;color:#aaa}
</style>
</head>
<body>
<div class="header">
<h1>日前出清全景 | __TITLE_DATE__</h1>
<div class="info">数据来源：天机库 shandong_px_dayahead_clearing_quantity_number（出清电量 MWh） + 负荷预测（MW→MWh÷4） + 润津日前电价</div>
</div>
<div class="stats">
<div class="stat"><div class="l">火电出清电量均值</div><div class="v">__THC_AVG__ MWh</div><div class="s">台数 __THN_MIN__~__THN_MAX__</div></div>
<div class="stat"><div class="l">新能源出清/预测</div><div class="v">__NEC_AVG__ / __NEW_F_AVG__ MWh</div><div class="s">出清 vs 预测合计</div></div>
<div class="stat"><div class="l">竞价空间均值</div><div class="v">__BS_AVG__ MWh</div><div class="s">谷值 __BS_MIN__ MWh</div></div>
<div class="stat"><div class="l">日前电价均值</div><div class="v">__DAP_AVG__ 元/MWh</div><div class="s">最低 __DAP_MIN__ 最高 __DAP_MAX__</div></div>
<div class="stat"><div class="l">风电预测均值</div><div class="v">__WIND_AVG__ MWh</div><div class="s">范围 __WIND_MIN__~__WIND_MAX__</div></div>
<div class="stat"><div class="l">光伏预测均值</div><div class="v">__PV_AVG__ MWh</div><div class="s">午峰 __PV_MAX__ MWh</div></div>
</div>
<div class="charts">
<div class="panel"><div class="t">各类电源出清电量（堆叠 · MWh/15min）</div><div class="c" id="c1"></div></div>
<div class="panel"><div class="t">火电出清电量（MWh） + 台数</div><div class="c" id="c2"></div></div>
<div class="panel"><div class="t">火电出清电力 + 台数 + 日前电价</div><div class="c" id="c6"></div></div>
<div class="panel"><div class="t">竞价电力 vs 火电出清电力（MW）</div><div class="c" id="c7"></div></div>
<div class="panel"><div class="t">新能源出清电量 vs 预测（MWh/15min）</div><div class="c" id="c3"></div></div>
<div class="panel"><div class="t">抽蓄 + 独立储能出清电量（MWh）</div><div class="c" id="c4"></div></div>
<div class="panel full"><div class="t">竞价空间（MWh） + 日前电价（元/MWh）</div><div class="c" id="c5"></div></div>
</div>
<div class="footer">润津储能 · 生成时间: __GEN_TIME__ · 预测出力 MW → MWh = MW÷4（15min为1/4小时）</div>
<script>
var T=__TIMES__;
var thC=__THC__,thN=__THN__,nuC=__NUC__,neC=__NEC__,inC=__INC__,drC=__DRC__,viC=__VIC__,bs=__BS__,daP=__DAP__;
var wind=__WIND__,pv=__PV__;
var thC_mw=__THC_MW__;
var bs_mw=__BS_MW__;
var g={left:55,right:60,top:20,bottom:35};
var ec={axisLabel:{color:'#888',fontSize:10},axisLine:{lineStyle:{color:'#d0d0d0'}},splitLine:{lineStyle:{color:'#f0f0f0'}}};
var ec2={axisLabel:{color:'#e67e22',fontSize:10},axisLine:{lineStyle:{color:'#e67e22'}},splitLine:{show:false}};
var ec3={axisLabel:{color:'#9a60b4',fontSize:10},axisLine:{lineStyle:{color:'#9a60b4'}},splitLine:{show:false}};
var el={textStyle:{color:'#666',fontSize:10},top:3};
var xA=Object.assign({type:'category',data:T,axisLabel:{interval:7}},ec);
var c1=echarts.init(document.getElementById('c1'));
c1.setOption({grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:['火电','核电','新能源','抽蓄','独立储能','虚拟'],bottom:0},el),xAxis:xA,yAxis:Object.assign({type:'value',name:'MWh'},ec),series:[{name:'火电',type:'line',data:thC,smooth:true,stack:'total',areaStyle:{},lineStyle:{width:1,color:'#d13438'},itemStyle:{color:'#d13438'},symbol:'none'},{name:'核电',type:'line',data:nuC,smooth:true,stack:'total',areaStyle:{},lineStyle:{width:1,color:'#9a60b4'},itemStyle:{color:'#9a60b4'},symbol:'none'},{name:'新能源',type:'line',data:neC,smooth:true,stack:'total',areaStyle:{},lineStyle:{width:1,color:'#107c10'},itemStyle:{color:'#107c10'},symbol:'none'},{name:'抽蓄',type:'line',data:drC,smooth:true,stack:'total',areaStyle:{},lineStyle:{width:1,color:'#f2a900'},itemStyle:{color:'#f2a900'},symbol:'none'},{name:'独立储能',type:'line',data:inC,smooth:true,stack:'total',areaStyle:{},lineStyle:{width:1,color:'#0078d4'},itemStyle:{color:'#0078d4'},symbol:'none'},{name:'虚拟',type:'line',data:viC,smooth:true,stack:'total',areaStyle:{},lineStyle:{width:1,color:'#ccc'},itemStyle:{color:'#ccc'},symbol:'none'}]});
var c2=echarts.init(document.getElementById('c2'));
c2.setOption({grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:['火电出清电量','火电台数']},el),xAxis:xA,yAxis:[Object.assign({type:'value',name:'MWh'},ec),Object.assign({type:'value',name:'台',min:__THN_YMIN__,max:__THN_YMAX__},ec2)],series:[{name:'火电出清电量',type:'bar',data:thC,barWidth:3,itemStyle:{color:'#d13438'}},{name:'火电台数',type:'line',data:thN,smooth:false,step:'end',lineStyle:{width:2,color:'#0078d4'},symbol:'none',yAxisIndex:1}]});
var c6=echarts.init(document.getElementById('c6'));
c6.setOption({grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:['火电出清电力','火电台数','日前电价']},el),xAxis:xA,yAxis:[Object.assign({type:'value',name:'MW'},ec),Object.assign({type:'value',name:'台',min:__THN_YMIN__,max:__THN_YMAX__},ec2),Object.assign({type:'value',name:'元/MWh',min:-100,max:__DAP_YMAX__},ec3)],series:[{name:'火电出清电力',type:'bar',data:thC_mw,barWidth:3,itemStyle:{color:'#d13438'}},{name:'火电台数',type:'line',data:thN,smooth:false,step:'end',lineStyle:{width:2,color:'#0078d4'},symbol:'none',yAxisIndex:1},{name:'日前电价',type:'line',data:daP,smooth:true,lineStyle:{width:2,color:'#9a60b4'},symbol:'none',yAxisIndex:2}]});
var c7=echarts.init(document.getElementById('c7'));
c7.setOption({grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:['竞价电力','火电出清电力','价差(竞价-火电)']},el),xAxis:xA,yAxis:Object.assign({type:'value',name:'MW'},ec),series:[{name:'竞价电力',type:'line',data:bs_mw,smooth:true,lineStyle:{width:2,color:'#0078d4'},symbol:'none',areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(0,120,212,0.1)'},{offset:1,color:'rgba(0,120,212,0)'}])}},{name:'火电出清电力',type:'line',data:thC_mw,smooth:true,lineStyle:{width:2,color:'#d13438'},symbol:'none'},{name:'价差(竞价-火电)',type:'bar',data:bs_mw.map(function(v,i){return v-thC_mw[i];}),barWidth:3,itemStyle:{color:function(p){return p.value>=0?'#107c10':'#e67e22';}}}]});
var c3=echarts.init(document.getElementById('c3'));
c3.setOption({grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:['新能源出清','风电预测','光伏预测','新能源预测合计']},el),xAxis:xA,yAxis:Object.assign({type:'value',name:'MWh'},ec),series:[{name:'新能源出清',type:'line',data:neC,smooth:true,lineStyle:{width:2.5,color:'#107c10'},symbol:'none',areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(16,124,16,0.15)'},{offset:1,color:'rgba(16,124,16,0)'}])}},{name:'风电预测',type:'line',data:wind,smooth:true,lineStyle:{width:1.5,color:'#0078d4',type:'dashed'},symbol:'none'},{name:'光伏预测',type:'line',data:pv,smooth:true,lineStyle:{width:1.5,color:'#f2a900',type:'dashed'},symbol:'none'},{name:'新能源预测合计',type:'line',data:wind.map(function(v,i){return v+pv[i];}),smooth:true,lineStyle:{width:2,color:'#5470c6',type:'dotted'},symbol:'none'}]});
var c4=echarts.init(document.getElementById('c4'));
c4.setOption({grid:g,tooltip:{trigger:'axis'},legend:Object.assign({data:['抽蓄','独立储能','零线']},el),xAxis:xA,yAxis:Object.assign({type:'value',name:'MWh'},ec),series:[{name:'抽蓄',type:'bar',data:drC,barWidth:5,itemStyle:{color:function(p){return p.value>=0?'#107c10':'#d13438';}}},{name:'独立储能',type:'bar',data:inC,barWidth:5,itemStyle:{color:function(p){return p.value>=0?'#0078d4':'#e67e22';}}},{name:'零线',type:'line',data:Array(96).fill(0),lineStyle:{color:'#ccc',width:1},symbol:'none',silent:true}]});
var c5=echarts.init(document.getElementById('c5'));
c5.setOption({grid:g,tooltip:{trigger:'axis',valueFormatter:function(v){return v!=null?(Math.abs(v)<1000?v.toFixed(2):v.toFixed(0)):'-';}},legend:Object.assign({data:['竞价空间','日前电价(润津)']},el),xAxis:xA,yAxis:[Object.assign({type:'value',name:'MWh'},ec),Object.assign({type:'value',name:'元/MWh',min:-100,max:__DAP_YMAX__},ec2)],series:[{name:'竞价空间',type:'line',data:bs,smooth:true,lineStyle:{width:2,color:'#0078d4'},symbol:'none',areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(0,120,212,0.15)'},{offset:1,color:'rgba(0,120,212,0)'}])}},{name:'日前电价(润津)',type:'line',data:daP,smooth:true,lineStyle:{width:2,color:'#d13438'},symbol:'none',yAxisIndex:1}]});
window.addEventListener('resize',function(){c1.resize();c2.resize();c3.resize();c4.resize();c5.resize();c6.resize();c7.resize();});
</script>
</body>
</html>'''

from datetime import datetime

html = html.replace('__TITLE_DATE__', title_date)
html = html.replace('__GEN_TIME__', datetime.now().strftime('%Y-%m-%d %H:%M'))
html = html.replace('__TIMES__', T)
html = html.replace('__THC__', json.dumps(thC))
html = html.replace('__THN__', json.dumps(thN))
html = html.replace('__NUC__', json.dumps(nuC))
html = html.replace('__NEC__', json.dumps(neC))
html = html.replace('__INC__', json.dumps(inC))
html = html.replace('__DRC__', json.dumps(drC))
html = html.replace('__VIC__', json.dumps(viC))
html = html.replace('__BS__', json.dumps(bs))
html = html.replace('__DAP__', json.dumps(daP))
html = html.replace('__WIND__', json.dumps(wind_f))
html = html.replace('__PV__', json.dumps(pv_f))
html = html.replace('__THC_MW__', json.dumps(thC_mw))
html = html.replace('__BS_MW__', json.dumps(bs_mw))

# Dynamic y-axis max for price
dap_max = max(daP) if daP else 900
dap_ymax = max(900, int(dap_max * 1.1 + 50))
html = html.replace('__DAP_YMAX__', str(dap_ymax))

# Dynamic y-axis for thermal unit count
thn_min = min(thN) if thN else 65
thn_max = max(thN) if thN else 95
thn_ymin = max(0, int(thn_min - 5))
thn_ymax = min(100, int(thn_max + 5))
html = html.replace('__THN_YMIN__', str(thn_ymin))
html = html.replace('__THN_YMAX__', str(thn_ymax))

html = html.replace('__THC_AVG__', f'{sum(thC)/96:.0f}')
html = html.replace('__THN_MIN__', f'{min(thN):.0f}')
html = html.replace('__THN_MAX__', f'{max(thN):.0f}')
html = html.replace('__NEC_AVG__', f'{sum(neC)/96:.0f}')
new_f_total = sum(wind_f)/96 + sum(pv_f)/96
html = html.replace('__NEW_F_AVG__', f'{new_f_total:.0f}')
html = html.replace('__BS_AVG__', f'{sum(bs)/96:.0f}')
html = html.replace('__BS_MIN__', f'{min(bs):.0f}')
html = html.replace('__DAP_AVG__', f'{sum(daP)/96:.0f}')
html = html.replace('__DAP_MIN__', f'{min(daP):.0f}')
html = html.replace('__DAP_MAX__', f'{max(daP):.0f}')
html = html.replace('__WIND_MIN__', f'{min(wind_f):.0f}')
html = html.replace('__WIND_MAX__', f'{max(wind_f):.0f}')
html = html.replace('__WIND_AVG__', f'{sum(wind_f)/96:.0f}')
html = html.replace('__PV_AVG__', f'{sum(pv_f)/96:.0f}')
html = html.replace('__PV_MIN__', f'{min(pv_f):.0f}')
html = html.replace('__PV_MAX__', f'{max(pv_f):.0f}')

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved: {OUT} ({os.path.getsize(OUT):,} bytes)')