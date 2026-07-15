"""统计0628-0708火电日前出清：中午最低2h均值 & 晚高峰最高2h均值 + 台数 + 电价 → HTML."""
import json, os, pymysql
from datetime import datetime

DATES = ['2026-06-28','2026-06-29','2026-06-30','2026-07-01','2026-07-02','2026-07-03','2026-07-04','2026-07-05','2026-07-06','2026-07-07','2026-07-08']
TIMES = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0,15,30,45)]

conn = pymysql.connect(host='rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com', port=3306,
    user='pengyiqiang', password='pengyiqiang123', database='tianrun_new',
    charset='utf8mb4', connect_timeout=10, read_timeout=60)
cur = conn.cursor()

# Query thermal clearing + number + price
th_da = {}; th_num = {}; da_price = {}; es_da = {}; dr_da = {}
for d in DATES:
    cur.execute('SELECT thermal_clearing, thermal_number, independent_clearing, draw_clearing FROM shandong_px_dayahead_clearing_quantity_number WHERE date=%s ORDER BY time_point', (d,))
    rows = cur.fetchall()
    th_da[d] = [float(r[0] or 0) * 4 for r in rows]  # MWh→MW
    th_num[d] = [float(r[1] or 0) for r in rows]
    es_da[d] = [float(r[2] or 0) * 4 for r in rows]  # 独立储能 MW
    dr_da[d] = [float(r[3] or 0) * 4 for r in rows]  # 抽蓄 MW

    cur.execute("SELECT price FROM shandong_px_reliable_clearing_unit_data WHERE date=%s AND member_id='b9e64e64a713458eba94c9af05c0a757' AND unit_name NOT LIKE '%%发电%%' AND unit_name NOT LIKE '%%用电%%' ORDER BY time_point", (d,))
    rows = cur.fetchall()
    da_price[d] = [float(r[0] or 0) for r in rows] if rows else [0]*96

cur.close(); conn.close()

# Define periods (15-min indices)
# 中午: 11:00-13:00 → indices 44-51 (8 points, 2h window = all 8)
NOON_START, NOON_END = 44, 51   # 8 points = exactly 2h
# 晚高峰: 17:00-20:00 → indices 68-79 (12 points, slide 2h window)
PEAK_START, PEAK_END = 68, 79

def window_mean(arr, start, length=8):
    return sum(arr[start:start+length]) / length

def find_best_window(arr, start, end, mode='min'):
    """Find 2h (8-point) window within [start, end] that gives min or max mean."""
    best_val = 1e9 if mode == 'min' else -1e9
    best_idx = start
    for i in range(start, end - 8 + 2):  # inclusive end
        m = window_mean(arr, i, 8)
        if (mode == 'min' and m < best_val) or (mode == 'max' and m > best_val):
            best_val = m
            best_idx = i
    return best_idx, best_val

# Compute stats
stats = []
for d in DATES:
    # 中午最低2h
    noon_idx, noon_th = find_best_window(th_da[d], NOON_START, NOON_END, 'min')
    noon_num = window_mean(th_num[d], noon_idx, 8)
    noon_price = window_mean(da_price[d], noon_idx, 8)
    noon_time = f'{TIMES[noon_idx]}-{TIMES[noon_idx+7]}'

    # 晚高峰最高2h
    peak_idx, peak_th = find_best_window(th_da[d], PEAK_START, PEAK_END, 'max')
    peak_num = window_mean(th_num[d], peak_idx, 8)
    peak_price = window_mean(da_price[d], peak_idx, 8)
    peak_time = f'{TIMES[peak_idx]}-{TIMES[peak_idx+7]}'

    # 中午谷值储能+抽蓄充电功率（正值=放电，负值=充电，取均值）
    noon_es = window_mean(es_da[d], noon_idx, 8)
    noon_dr = window_mean(dr_da[d], noon_idx, 8)
    # 晚高峰储能+抽蓄放电功率
    peak_es = window_mean(es_da[d], peak_idx, 8)
    peak_dr = window_mean(dr_da[d], peak_idx, 8)

    stats.append({
        'date': d[5:],
        'noon_th': round(noon_th, 0),
        'noon_num': round(noon_num, 1),
        'noon_price': round(noon_price, 0),
        'noon_time': noon_time,
        'noon_ratio': round(noon_th / noon_num, 1) if noon_num > 0 else 0,
        'peak_th': round(peak_th, 0),
        'peak_num': round(peak_num, 1),
        'peak_price': round(peak_price, 0),
        'peak_time': peak_time,
        'peak_ratio': round(peak_th / peak_num, 1) if peak_num > 0 else 0,
        'noon_es': round(noon_es, 0),
        'noon_dr': round(noon_dr, 0),
        'peak_es': round(peak_es, 0),
        'peak_dr': round(peak_dr, 0),
    })

# Build HTML
labels = [s['date'] for s in stats]
noon_th = [s['noon_th'] for s in stats]
peak_th = [s['peak_th'] for s in stats]
noon_num = [s['noon_num'] for s in stats]
peak_num = [s['peak_num'] for s in stats]
noon_price = [s['noon_price'] for s in stats]
peak_price = [s['peak_price'] for s in stats]
noon_ratio = [s['noon_ratio'] for s in stats]
peak_ratio = [s['peak_ratio'] for s in stats]
noon_es = [s['noon_es'] for s in stats]
noon_dr = [s['noon_dr'] for s in stats]
peak_es = [s['peak_es'] for s in stats]
peak_dr = [s['peak_dr'] for s in stats]

# Build table HTML
table_html = '<table><thead><tr><th>日期</th><th>中午最低2h</th><th>火电(MW)</th><th>台数</th><th>单机</th><th>电价</th><th>储能充电</th><th>抽蓄充电</th><th>晚高峰最高2h</th><th>火电(MW)</th><th>台数</th><th>单机</th><th>电价</th><th>储能放电</th><th>抽蓄放电</th><th>峰谷差</th></tr></thead><tbody>'
for s in stats:
    diff = s['peak_th'] - s['noon_th']
    sign = '+' if diff > 0 else ''
    table_html += f'<tr><td>{s["date"]}</td><td>{s["noon_time"]}</td><td>{s["noon_th"]:.0f}</td><td>{s["noon_num"]:.1f}</td><td>{s["noon_ratio"]:.0f}</td><td style="color:#107c10">{s["noon_price"]:.0f}</td><td style="color:#0078d4">{s["noon_es"]:.0f}</td><td style="color:#f2a900">{s["noon_dr"]:.0f}</td><td>{s["peak_time"]}</td><td>{s["peak_th"]:.0f}</td><td>{s["peak_num"]:.1f}</td><td>{s["peak_ratio"]:.0f}</td><td style="color:#d13438">{s["peak_price"]:.0f}</td><td style="color:#e67e22">{s["peak_es"]:.0f}</td><td style="color:#107c10">{s["peak_dr"]:.0f}</td><td>{sign}{diff:.0f}</td></tr>'
table_html += '</tbody></table>'

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>火电日前出清 中午低谷 & 晚高峰 分析 | 0628-0708</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}}
.header{{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600;margin-bottom:4px}}
.header .info{{font-size:11px;color:#888}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:8px 24px}}
@media(max-width:1200px){{.charts{{grid-template-columns:1fr}}}}
.panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.panel .t{{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.panel .c{{width:100%;height:400px}}
.panel.full{{grid-column:1/-1}}
.panel.full .c{{height:420px}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
table{{width:100%;border-collapse:collapse;font-size:11px;margin:8px 0}}
table th{{background:#f5f5f5;color:#333;padding:6px 8px;text-align:center;border-bottom:2px solid #e0e0e0}}
table td{{padding:5px 8px;border-bottom:1px solid #f0f0f0;text-align:center}}
table tr:hover td{{background:#e5f3ff}}
</style>
</head>
<body>
<div class="header">
<h1>火电日前出清 — 中午低谷 & 晚高峰分析 | 0628 ~ 0708</h1>
<div class="info">数据来源：天机库 shandong_px_dayahead_clearing_quantity_number · 中午=11:00-13:00最低2h窗口 · 晚高峰=17:00-20:00最高2h窗口</div>
</div>
<div class="charts">
<div class="panel"><div class="t">火电出清电力：中午最低2h vs 晚高峰最高2h（MW）</div><div class="c" id="c1"></div></div>
<div class="panel"><div class="t">同时段火电开机台数（台）</div><div class="c" id="c2"></div></div>
<div class="panel"><div class="t">同时段日前电价（元/MWh）</div><div class="c" id="c3"></div></div>
<div class="panel"><div class="t">峰谷差（晚高峰 - 中午低谷，MW）</div><div class="c" id="c4"></div></div>
<div class="panel"><div class="t">储能+抽蓄功率 — 中午谷值充电 vs 晚高峰放电（MW）<span style="font-weight:400;color:#888;font-size:11px"> — 负=充电，正=放电</span></div><div class="c" id="c6"></div></div>
<div class="panel full"><div class="t">单机出力 vs 电价 — 中午低谷 & 晚高峰（MW/台 vs 元/MWh）<span style="font-weight:400;color:#888;font-size:11px"> — 气泡大小=总出力(MW)，标签=日期</span></div><div class="c" id="c5" style="height:450px"></div></div>
<div class="panel full"><div class="t">数据明细表</div><div class="c" id="c7" style="height:auto;padding:16px">{table_html}</div></div>
</div>
<div class="footer">润津储能 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<script>
var T={json.dumps(TIMES, ensure_ascii=False)};
var LABELS={json.dumps(labels)};
var NOON_TH={json.dumps(noon_th)};
var PEAK_TH={json.dumps(peak_th)};
var NOON_NUM={json.dumps(noon_num)};
var PEAK_NUM={json.dumps(peak_num)};
var NOON_PRICE={json.dumps(noon_price)};
var PEAK_PRICE={json.dumps(peak_price)};
var NOON_RATIO={json.dumps(noon_ratio)};
var PEAK_RATIO={json.dumps(peak_ratio)};
var NOON_ES={json.dumps(noon_es)};
var NOON_DR={json.dumps(noon_dr)};
var PEAK_ES={json.dumps(peak_es)};
var PEAK_DR={json.dumps(peak_dr)};

var diffs=NOON_TH.map(function(v,i){{return PEAK_TH[i]-v;}});

var g={{left:55,right:20,top:20,bottom:40}};
var ec={{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var el={{textStyle:{{color:'#666',fontSize:10}},top:3}};
var xA=Object.assign({{type:'category',data:LABELS,axisLabel:{{rotate:30}}}},ec);

var c1=echarts.init(document.getElementById('c1'));
c1.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:['中午最低2h','晚高峰最高2h']}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:[
  {{name:'中午最低2h',type:'bar',data:NOON_TH,barWidth:14,itemStyle:{{color:'#107c10'}},label:{{show:true,position:'bottom',fontSize:9,formatter:'{{c}}'}}}},
  {{name:'晚高峰最高2h',type:'bar',data:PEAK_TH,barWidth:14,itemStyle:{{color:'#d13438'}},label:{{show:true,position:'top',fontSize:9,formatter:'{{c}}'}}}}
]}});

var c2=echarts.init(document.getElementById('c2'));
c2.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:['中午台数','晚高峰台数']}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'台'}},ec),series:[
  {{name:'中午台数',type:'bar',data:NOON_NUM,barWidth:14,itemStyle:{{color:'#107c10'}},label:{{show:true,position:'bottom',fontSize:9,formatter:'{{c}}'}}}},
  {{name:'晚高峰台数',type:'bar',data:PEAK_NUM,barWidth:14,itemStyle:{{color:'#d13438'}},label:{{show:true,position:'top',fontSize:9,formatter:'{{c}}'}}}}
]}});

var c3=echarts.init(document.getElementById('c3'));
c3.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:['中午电价','晚高峰电价']}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'元/MWh'}},ec),series:[
  {{name:'中午电价',type:'bar',data:NOON_PRICE,barWidth:14,itemStyle:{{color:'#107c10'}},label:{{show:true,position:'bottom',fontSize:9,formatter:'{{c}}'}}}},
  {{name:'晚高峰电价',type:'bar',data:PEAK_PRICE,barWidth:14,itemStyle:{{color:'#d13438'}},label:{{show:true,position:'top',fontSize:9,formatter:'{{c}}'}}}}
]}});

var c4=echarts.init(document.getElementById('c4'));
c4.setOption({{grid:g,tooltip:{{trigger:'axis'}},xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:[
  {{name:'峰谷差',type:'bar',data:diffs,barWidth:18,itemStyle:{{color:function(p){{return p.value>=0?'#d13438':'#107c10';}}}},label:{{show:true,position:'top',fontSize:10,formatter:'{{c}}'}}}}
]}});

// Chart 5: 单机出力 vs 电价 气泡图
var c5=echarts.init(document.getElementById('c5'));
var bubData=[];
LABELS.forEach(function(d,i){{
  bubData.push([NOON_RATIO[i], NOON_PRICE[i], NOON_TH[i], d, '中午低谷']);
  bubData.push([PEAK_RATIO[i], PEAK_PRICE[i], PEAK_TH[i], d, '晚高峰']);
}});
c5.setOption({{grid:{{left:70,right:20,top:20,bottom:40}},tooltip:{{trigger:'item',formatter:function(p){{return p.data[4]+'<br/>'+p.data[3]+'<br/>单机出力: '+p.data[0].toFixed(1)+' MW/台<br/>电价: '+p.data[1].toFixed(0)+' 元/MWh<br/>总出力: '+p.data[2].toFixed(0)+' MW';}}}},xAxis:Object.assign({{type:'value',name:'单机出力 (MW/台)'}},ec),yAxis:Object.assign({{type:'value',name:'电价 (元/MWh)'}},ec),series:[
  {{name:'中午低谷',type:'scatter',data:bubData.filter(function(d){{return d[4]==='中午低谷';}}),symbolSize:function(p){{return Math.max(8, Math.sqrt(p[2])/8);}},itemStyle:{{color:'#107c10',opacity:0.7}},label:{{show:true,position:'right',fontSize:9,formatter:function(p){{return p.data[3];}}}}}},
  {{name:'晚高峰',type:'scatter',data:bubData.filter(function(d){{return d[4]==='晚高峰';}}),symbolSize:function(p){{return Math.max(8, Math.sqrt(p[2])/8);}},itemStyle:{{color:'#d13438',opacity:0.7}},label:{{show:true,position:'right',fontSize:9,formatter:function(p){{return p.data[3];}}}}}}
]}});

// Chart 6: 储能+抽蓄功率
var c6=echarts.init(document.getElementById('c6'));
var esPrice=NOON_ES.map(function(v,i){{return v+PEAK_ES[i];}});
var drPrice=NOON_DR.map(function(v,i){{return v+PEAK_DR[i];}});
c6.setOption({{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:['储能中午充电','储能晚高峰放电','抽蓄中午充电','抽蓄晚高峰放电']}},el),xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:[
  {{name:'储能中午充电',type:'bar',data:NOON_ES,barWidth:10,itemStyle:{{color:'#0078d4'}},label:{{show:true,position:'bottom',fontSize:8,formatter:function(p){{return p.value!==0?p.value.toFixed(0):'';}}}}}},
  {{name:'储能晚高峰放电',type:'bar',data:PEAK_ES,barWidth:10,itemStyle:{{color:'#e67e22'}},label:{{show:true,position:'top',fontSize:8,formatter:function(p){{return p.value!==0?p.value.toFixed(0):'';}}}}}},
  {{name:'抽蓄中午充电',type:'bar',data:NOON_DR,barWidth:10,itemStyle:{{color:'#f2a900'}},label:{{show:true,position:'bottom',fontSize:8,formatter:function(p){{return p.value!==0?p.value.toFixed(0):'';}}}}}},
  {{name:'抽蓄晚高峰放电',type:'bar',data:PEAK_DR,barWidth:10,itemStyle:{{color:'#107c10'}},label:{{show:true,position:'top',fontSize:8,formatter:function(p){{return p.value!==0?p.value.toFixed(0):'';}}}}}}
]}});

window.addEventListener('resize',function(){{c1.resize();c2.resize();c3.resize();c4.resize();c5.resize();c6.resize();}});
</script>
</body>
</html>'''

OUT = 'E:/DataWork/Storage_Strategy/output/火电日前出清_中午低谷_晚高峰_0628-0708.html'
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)

# Also print summary
print(f'Saved: {OUT} ({os.path.getsize(OUT):,} bytes)')
print()
print(f'{"日期":>6}  {"中午最低2h":>10}  {"时间":>14}  {"台数":>6}  {"电价":>6}  |  {"晚高峰最高2h":>10}  {"时间":>14}  {"台数":>6}  {"电价":>6}  {"峰谷差":>8}')
print('-' * 120)
for s in stats:
    print(f'{s["date"]:>6}  {s["noon_th"]:>8.0f} MW  {s["noon_time"]:>14}  {s["noon_num"]:>4.1f}台  {s["noon_price"]:>4.0f}元  |  {s["peak_th"]:>8.0f} MW  {s["peak_time"]:>14}  {s["peak_num"]:>4.1f}台  {s["peak_price"]:>4.0f}元  {s["peak_th"]-s["noon_th"]:>+.0f}')