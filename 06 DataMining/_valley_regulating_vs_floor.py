"""验证：谷段调节机组出力 vs 谷段是否地板价
核心假设：谷段火电出清 - 必开估算 ≈ 调节机组谷段出力
        调节机组谷段出力越接近最小出力总和，越可能地板价
数据：5-7月共有日期（日前出清 + 实际负荷 + 日前电价 + 实时电价）
     必开估算用「直调负荷×13%」（非供暖期）
     谷段窗口：从日前火电出清96点曲线找2h(8点)连续最小窗口
"""
import pymysql, os, json
from collections import defaultdict
from datetime import datetime

for line in open(r'E:\DataWork\Storage_Strategy\.env', encoding='utf-8'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

conn = pymysql.connect(host=os.getenv('DB_TIANJI_HOST'), port=int(os.getenv('DB_TIANJI_PORT', 3306)),
    user=os.getenv('DB_TIANJI_USER'), password=os.getenv('DB_TIANJI_PASSWORD'),
    database=os.getenv('DB_TIANJI_DATABASE'), charset='utf8mb4', connect_timeout=10, read_timeout=120)
cur = conn.cursor()
MEMBER_ID = 'b9e64e64a713458eba94c9af05c0a757'

# 1. 日前火电出清（找谷段窗口用）
print('Loading dayahead clearing...')
cur.execute("""SELECT date, time_point, thermal_clearing, independent_clearing, draw_clearing, virtual_clearing
    FROM shandong_px_dayahead_clearing_quantity_number
    WHERE date >= '2026-05-01' AND date <= '2026-07-31' ORDER BY date, time_point""")
da_clearing = defaultdict(list)
for r in cur.fetchall():
    da_clearing[str(r[0])].append({
        'thermal': float(r[2] or 0) * 4,
        'es_dr_vi': (float(r[3] or 0) + float(r[4] or 0) + float(r[5] or 0)) * 4
    })

# 2. 实际负荷（直调负荷 + 竞价空间 + 地方公用）
print('Loading actual load...')
cur.execute("""SELECT date, time_order, actual_dispatched_load, actual_tie_line_load, actual_wind_power,
    actual_photovoltaic_power, actual_nuclear_power, actual_self_power, actual_local_power
    FROM shandong_px_spot_actual_load_info
    WHERE date >= '2026-05-01' AND date <= '2026-07-31' ORDER BY date, time_order""")
actual_load = defaultdict(list)
for r in cur.fetchall():
    d = str(r[0])
    dispatched = float(r[2] or 0)
    bs = dispatched - float(r[3] or 0) - float(r[4] or 0) - float(r[5] or 0) - float(r[6] or 0) - float(r[7] or 0)
    actual_load[d].append({'dispatched': dispatched, 'bs': bs, 'local': float(r[8] or 0)})

# 3. 日前电价
print('Loading dayahead price...')
cur.execute("""SELECT date, time_point, price FROM shandong_px_reliable_clearing_unit_data
    WHERE date >= '2026-05-01' AND date <= '2026-07-31' AND member_id = %s
    AND unit_name NOT LIKE '%%发电%%' AND unit_name NOT LIKE '%%用电%%'
    ORDER BY date, time_point""", (MEMBER_ID,))
da_price = defaultdict(list)
for r in cur.fetchall():
    da_price[str(r[0])].append(float(r[2] or 0))

# 4. 实时电价
print('Loading realtime price...')
cur.execute("""SELECT date, time_point, price FROM shandong_px_realtime_clearing_results_query
    WHERE date >= '2026-05-01' AND date <= '2026-07-31' AND member_id = %s
    ORDER BY date, time_point""", (MEMBER_ID,))
rt_price = defaultdict(list)
for r in cur.fetchall():
    rt_price[str(r[0])].append(float(r[2] or 0))

cur.close(); conn.close()

common_dates = sorted(set(da_clearing.keys()) & set(actual_load.keys()) &
                      set(da_price.keys()) & set(rt_price.keys()))
print(f'\nCommon dates: {len(common_dates)} ({common_dates[0]} ~ {common_dates[-1]})')

TIMES = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0, 15, 30, 45)]
W = 8  # 2h = 8个15min点

# ── 逐日计算 ──
rows = []
for d in common_dates:
    da = da_clearing[d]; al = actual_load[d]
    dp = da_price.get(d, []); rp = rt_price.get(d, [])
    if len(da) != 96 or len(al) != 96 or len(dp) != 96 or len(rp) != 96:
        continue

    th_da = [x['thermal'] for x in da]
    # 找谷段窗口（2h连续和最小）
    best_vi = 0; best_vs = float('inf')
    for i in range(96 - W + 1):
        s = sum(th_da[i:i+W])
        if s < best_vs:
            best_vs = s; best_vi = i

    # 谷段窗口内各项
    valley_da_thermal = sum(th_da[best_vi:best_vi+W]) / W
    valley_dispatched = sum(al[i]['dispatched'] for i in range(best_vi, best_vi+W)) / W
    valley_bs = sum(al[i]['bs'] for i in range(best_vi, best_vi+W)) / W
    valley_local = sum(al[i]['local'] for i in range(best_vi, best_vi+W)) / W
    valley_es_dr_vi = sum(da[i]['es_dr_vi'] for i in range(best_vi, best_vi+W)) / W

    # 实际火电谷段 = bs - local - es_dr_vi
    valley_act_thermal = valley_bs - valley_local - valley_es_dr_vi

    # 必开估算 = 谷段直调负荷 × 13%
    must_run_est = valley_dispatched * 0.13

    # 调节机组谷段出力（两个口径）
    # 口径1：基于日前火电出清
    regulating_valley_da = valley_da_thermal - must_run_est
    # 口径2：基于实际火电
    regulating_valley_act = valley_act_thermal - must_run_est

    # 谷段电价
    da_price_valley = sum(dp[best_vi:best_vi+W]) / W
    rt_price_valley = sum(rp[best_vi:best_vi+W]) / W
    # 谷段最低实时电价
    rt_price_min = min(rp[best_vi:best_vi+W])
    da_price_min = min(dp[best_vi:best_vi+W])
    # 是否地板价：谷段实时均价 ≤ 0 或最低 ≤ -50
    is_floor = rt_price_valley <= 0 or rt_price_min <= -50

    rows.append({
        'date': d, 'mmdd': d[5:],
        'valley_window': f'{TIMES[best_vi]}-{TIMES[best_vi+W-1]}',
        'valley_da_thermal': round(valley_da_thermal, 0),
        'valley_act_thermal': round(valley_act_thermal, 0),
        'valley_dispatched': round(valley_dispatched, 0),
        'must_run_est': round(must_run_est, 0),
        'regulating_valley_da': round(regulating_valley_da, 0),
        'regulating_valley_act': round(regulating_valley_act, 0),
        'da_price_valley': round(da_price_valley, 1),
        'rt_price_valley': round(rt_price_valley, 1),
        'rt_price_min': round(rt_price_min, 1),
        'da_price_min': round(da_price_min, 1),
        'is_floor': is_floor,
    })

floor_days = [r for r in rows if r['is_floor']]
normal_days = [r for r in rows if not r['is_floor']]

print(f'\n=== 谷段地板价日 vs 正常日 ===')
print(f'地板价日: {len(floor_days)} 天')
print(f'正常日: {len(normal_days)} 天')

# ── 统计对比 ──
def stats(group, key):
    vals = [r[key] for r in group]
    if not vals: return 0, 0, 0
    return sum(vals)/len(vals), min(vals), max(vals)

print(f'\n{"指标":<30}{"地板价日均值":<15}{"正常日均值":<15}{"区分度":<10}')
print('-' * 70)
for key, label in [
    ('valley_da_thermal', '谷段日前火电(MW)'),
    ('valley_act_thermal', '谷段实际火电(MW)'),
    ('valley_dispatched', '谷段直调负荷(MW)'),
    ('must_run_est', '必开估算(MW)'),
    ('regulating_valley_da', '调节机组出力(日前,MW)'),
    ('regulating_valley_act', '调节机组出力(实际,MW)'),
    ('da_price_valley', '谷段日前电价(元/MWh)'),
    ('rt_price_valley', '谷段实时电价(元/MWh)'),
]:
    fm, fmin, fmax = stats(floor_days, key)
    nm, nmin, nmax = stats(normal_days, key)
    sep = (nm - fm) / ((nm + fm) / 2) * 100 if (nm + fm) != 0 else 0
    print(f'{label:<30}{fm:<15.0f}{nm:<15.0f}{sep:<10.1f}%')

# ── 按调节机组出力排序看地板价分布 ──
print(f'\n=== 按调节机组出力(日前)排序 ===')
sorted_rows = sorted(rows, key=lambda r: r['regulating_valley_da'])
print(f'{"日期":<12}{"调节出力MW":<12}{"直调负荷":<12}{"日前电价":<10}{"实时电价":<10}{"地板价?":<8}')
for r in sorted_rows:
    flag = '***' if r['is_floor'] else ''
    print(f"{r['mmdd']:<12}{r['regulating_valley_da']:<12.0f}{r['valley_dispatched']:<12.0f}{r['da_price_valley']:<10.1f}{r['rt_price_valley']:<10.1f}{flag:<8}")

# ── 输出 HTML ──
OUT_DIR = r'E:\DataWork\Storage_Strategy\output\竞价空间分析结果'
os.makedirs(OUT_DIR, exist_ok=True)
html_path = os.path.join(OUT_DIR, '谷段调节机组出力_vs_地板价.html')

dates_js = json.dumps([r['mmdd'] for r in rows], ensure_ascii=False)
reg_da = json.dumps([r['regulating_valley_da'] for r in rows])
reg_act = json.dumps([r['regulating_valley_act'] for r in rows])
da_p = json.dumps([r['da_price_valley'] for r in rows])
rt_p = json.dumps([r['rt_price_valley'] for r in rows])
floor_flags = json.dumps([1 if r['is_floor'] else 0 for r in rows])
must_run = json.dumps([r['must_run_est'] for r in rows])
dispatched = json.dumps([r['valley_dispatched'] for r in rows])

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>谷段调节机组出力 vs 地板价 | 5-7月</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}}
.header{{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600}}
.header .info{{font-size:11px;color:#888}}
.panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;margin:8px 24px;overflow:hidden}}
.panel .t{{padding:6px 14px;font-size:12px;font-weight:600;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.panel .c{{width:100%;height:420px}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
</style>
</head>
<body>
<div class="header">
<h1>谷段调节机组出力 vs 地板价 | 5-7月</h1>
<div class="info">必开估算 = 谷段直调负荷 × 13% · 调节机组出力 = 谷段火电 - 必开估算 · 地板价 = 谷段实时均价≤0 或 最低≤-50 · {len(rows)}天 · 数据来源：天机库</div>
</div>

<div class="panel"><div class="t">调节机组谷段出力(日前/实际) + 谷段电价（红柱=地板价日）</div><div class="c" id="c1"></div></div>
<div class="panel"><div class="t">散点：调节机组出力(日前) vs 谷段实时电价（红色=地板价日）</div><div class="c" id="c2"></div></div>
<div class="panel"><div class="t">必开估算 vs 谷段直调负荷（验证13%估算合理性）</div><div class="c" id="c3"></div></div>

<div class="footer">润津储能 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} · 必开估算=谷段直调负荷×13%</div>
<script>
var D={dates_js};
var N={len(rows)};
var g={{left:55,right:90,top:20,bottom:50}};
var ec={{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var ec2={{axisLabel:{{color:'#e67e22',fontSize:10}},axisLine:{{lineStyle:{{color:'#e67e22'}}}},splitLine:{{show:false}}}};
var el={{textStyle:{{color:'#666',fontSize:10}},top:3}};

// Chart 1: 调节机组出力 + 电价（地板价日高亮）
var floorIdx={floor_flags};
var regDa={reg_da};
var colors=[];
for(var i=0;i<N;i++) colors.push(floorIdx[i]?'#d13438':'#0078d4');
var c1=echarts.init(document.getElementById('c1'));
c1.setOption({{
grid:g,tooltip:{{trigger:'axis',formatter:function(ps){{
  var i=ps[0].dataIndex;
  var s=D[i]+'<br/>';
  ps.forEach(function(p){{s+=p.marker+p.seriesName+':'+p.value.toFixed(0)+'<br/>';}});
  s+=floorIdx[i]?'<b style="color:red">地板价日</b>':'正常日';
  return s;
}}}}}},
legend:Object.assign({{data:['调节出力(日前)','调节出力(实际)','谷段日前电价','谷段实时电价']}},el),
dataZoom:[{{type:'slider',start:0,end:100,height:25,bottom:10}},{{type:'inside'}}],
xAxis:Object.assign({{type:'category',data:D,axisLabel:{{interval:Math.floor(N/20),fontSize:9,rotate:45}}}},ec),
yAxis:[
  Object.assign({{type:'value',name:'MW'}},ec),
  Object.assign({{type:'value',name:'元/MWh'}},ec2)
],
series:[
  {{name:'调节出力(日前)',type:'bar',data:regDa.map(function(v,i){{return{{value:v,itemStyle:{{color:colors[i]}}}}}}),barWidth:6}},
  {{name:'调节出力(实际)',type:'bar',data:{reg_act},barWidth:6,itemStyle:{{color:'#2c7be5',opacity:0.5}}}},
  {{name:'谷段日前电价',type:'line',data:{da_p},smooth:true,lineStyle:{{width:2,color:'#e67e22'}},itemStyle:{{color:'#e67e22'}},symbol:'none',yAxisIndex:1}},
  {{name:'谷段实时电价',type:'line',data:{rt_p},smooth:true,lineStyle:{{width:2,color:'#9b59b6'}},itemStyle:{{color:'#9b59b6'}},symbol:'none',yAxisIndex:1}}
]
}});

// Chart 2: 散点 调节出力 vs 实时电价
var scatter=[], floorScatter=[];
for(var i=0;i<N;i++){{
  var pt=[regDa[i],{rt_p}[i]];
  floorIdx[i]?floorScatter.push(pt):scatter.push(pt);
}}
var c2=echarts.init(document.getElementById('c2'));
c2.setOption({{
grid:g,tooltip:{{trigger:'item',formatter:function(p){{return D[p.dataIndex]+'<br/>调节出力:'+p.value[0].toFixed(0)+' MW<br/>实时电价:'+p.value[1].toFixed(1)+' 元/MWh';}}}},
xAxis:Object.assign({{type:'value',name:'调节机组出力(MW)'}},ec),
yAxis:Object.assign({{type:'value',name:'谷段实时电价(元/MWh)'}},ec),
series:[
  {{name:'正常日',type:'scatter',data:scatter,symbolSize:8,itemStyle:{{color:'#0078d4'}}}},
  {{name:'地板价日',type:'scatter',data:floorScatter,symbolSize:10,itemStyle:{{color:'#d13438'}}}}
]
}});

// Chart 3: 必开估算 vs 直调负荷
var c3=echarts.init(document.getElementById('c3'));
c3.setOption({{
grid:g,tooltip:{{trigger:'axis'}},
legend:Object.assign({{data:['谷段直调负荷','必开估算(13%)']}},el),
dataZoom:[{{type:'slider',start:0,end:100,height:25,bottom:10}},{{type:'inside'}}],
xAxis:Object.assign({{type:'category',data:D,axisLabel:{{interval:Math.floor(N/20),fontSize:9,rotate:45}}}},ec),
yAxis:Object.assign({{type:'value',name:'MW'}},ec),
series:[
  {{name:'谷段直调负荷',type:'line',data:{dispatched},smooth:true,lineStyle:{{width:2,color:'#0078d4'}},itemStyle:{{color:'#0078d4'}},symbol:'none'}},
  {{name:'必开估算(13%)',type:'line',data:{must_run},smooth:true,lineStyle:{{width:2,color:'#e67e22'}},itemStyle:{{color:'#e67e22'}},symbol:'none'}}
]
}});

window.addEventListener('resize',function(){{[c1,c2,c3].forEach(function(c){{c.resize();}});}});
</script>
</body>
</html>'''

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'\nSaved: {html_path} ({len(html.encode("utf-8")):,} bytes)')
print(f'Done. {len(rows)} days, {len(floor_days)} floor-price days.')