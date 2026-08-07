"""修正版：单台调节机组出力 vs 地板价
1. 从预调度表识别必开/调节机组（CV<5%=必开，其余=调节）
2. 计算调节机组谷段总容量和单台均值（从预调度）
3. 用「谷段火电出清 - 必开估算」计算单台调节机组出力
4. 对比地板价日 vs 非地板价日的区分度
"""
import pymysql, os, json, math
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

# ── 1. 预调度：识别必开/调节机组 ──
print('=== 1. 预调度机组分类 ===')
# 用2026-07-24（7月唯一有数据的日期）
cur.execute("""SELECT generator_name, AVG(declaration_power), STDDEV(declaration_power)
    FROM shandong_px_provincial_prescheduling_results
    WHERE date='2026-07-24' AND declaration_power > 0
    GROUP BY generator_name""")
presched_units = {}
for name, avg, std in cur.fetchall():
    cv = float(std or 0) / float(avg or 1) * 100
    presched_units[name] = {'avg': float(avg), 'cv': cv}

must_run_units = {n: u for n, u in presched_units.items() if u['cv'] < 5}
regulating_units = {n: u for n, u in presched_units.items() if u['cv'] >= 5}
print(f'  必开机组: {len(must_run_units)}台, 平均出力={sum(u["avg"] for u in must_run_units.values())/len(must_run_units):.0f}MW')
print(f'  调节机组: {len(regulating_units)}台, 平均出力={sum(u["avg"] for u in regulating_units.values())/len(regulating_units):.0f}MW')

# 调节机组总容量（从预调度，这是「可调节能力」的上限）
regulating_total_capacity = sum(u['avg'] for u in regulating_units.values())
print(f'  调节机组总容量: {regulating_total_capacity:.0f}MW')

# ── 2. 逐日计算（5-7月） ──
print('\n=== 2. 逐日计算 ===')

# 日前出清
cur.execute("""SELECT date, time_point, thermal_clearing, thermal_number, independent_clearing, draw_clearing, virtual_clearing
    FROM shandong_px_dayahead_clearing_quantity_number
    WHERE date >= '2026-05-01' AND date <= '2026-07-31' ORDER BY date, time_point""")
da_clearing = defaultdict(list)
for r in cur.fetchall():
    da_clearing[str(r[0])].append({
        'thermal': float(r[2] or 0) * 4,
        'num': float(r[3] or 0),
        'es_dr_vi': (float(r[4] or 0) + float(r[5] or 0) + float(r[6] or 0)) * 4
    })

# 实际负荷
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

# 日前电价
cur.execute("""SELECT date, time_point, price FROM shandong_px_reliable_clearing_unit_data
    WHERE date >= '2026-05-01' AND date <= '2026-07-31' AND member_id = %s
    AND unit_name NOT LIKE '%%发电%%' AND unit_name NOT LIKE '%%用电%%'
    ORDER BY date, time_point""", ('b9e64e64a713458eba94c9af05c0a757',))
da_price = defaultdict(list)
for r in cur.fetchall():
    da_price[str(r[0])].append(float(r[2] or 0))

# 实时电价
cur.execute("""SELECT date, time_point, price FROM shandong_px_realtime_clearing_results_query
    WHERE date >= '2026-05-01' AND date <= '2026-07-31' AND member_id = %s
    ORDER BY date, time_point""", ('b9e64e64a713458eba94c9af05c0a757',))
rt_price = defaultdict(list)
for r in cur.fetchall():
    rt_price[str(r[0])].append(float(r[2] or 0))

cur.close(); conn.close()

common_dates = sorted(set(da_clearing.keys()) & set(actual_load.keys()) &
                      set(da_price.keys()) & set(rt_price.keys()))
print(f'  共同日期: {len(common_dates)}天')

TIMES = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0, 15, 30, 45)]
W = 8

rows = []
for d in common_dates:
    da = da_clearing[d]; al = actual_load[d]
    dp = da_price.get(d, []); rp = rt_price.get(d, [])
    if len(da) != 96 or len(al) != 96 or len(dp) != 96 or len(rp) != 96:
        continue

    th_da = [x['thermal'] for x in da]
    # 找谷段窗口
    best_vi, best_vs = 0, float('inf')
    for i in range(96 - W + 1):
        s = sum(th_da[i:i+W])
        if s < best_vs: best_vs = s; best_vi = i

    # 谷段数据
    valley_thermal = sum(th_da[best_vi:best_vi+W]) / W
    valley_num = sum(x['num'] for x in da[best_vi:best_vi+W]) / W
    valley_dispatched = sum(al[i]['dispatched'] for i in range(best_vi, best_vi+W)) / W
    valley_bs = sum(al[i]['bs'] for i in range(best_vi, best_vi+W)) / W
    valley_local = sum(al[i]['local'] for i in range(best_vi, best_vi+W)) / W
    valley_es = sum(da[i]['es_dr_vi'] for i in range(best_vi, best_vi+W)) / W

    # 实际火电
    valley_act_thermal = valley_bs - valley_local - valley_es

    # 必开估算（两种方法）
    # 方法1：直调负荷×13%
    must_run_est_13pct = valley_dispatched * 0.13
    # 方法2：预调度实测（仅07-24可用，其他日期用比例推算）
    # 07-24: 必开=9192MW, 直调负荷=79082MW, 比例=11.6%
    must_run_est_presched = valley_dispatched * 0.116

    # 必开台数估算（单台~290MW）
    must_run_units_est = round(must_run_est_13pct / 290)

    # 调节机组台数
    reg_units = valley_num - must_run_units_est
    if reg_units <= 0:
        reg_units = 1

    # 调节机组出力
    reg_output = valley_thermal - must_run_est_13pct
    reg_output_act = valley_act_thermal - must_run_est_13pct

    # 单台调节机组出力（关键指标）
    unit_output_reg = reg_output / reg_units
    unit_output_reg_act = reg_output_act / reg_units

    # 单台出力（含必开，旧算法）
    unit_output_all = valley_thermal / valley_num if valley_num > 0 else 0

    # 电价
    da_p = sum(dp[best_vi:best_vi+W]) / W
    rt_p = sum(rp[best_vi:best_vi+W]) / W
    rt_min = min(rp[best_vi:best_vi+W])
    is_floor = rt_p <= 0 or rt_min <= -50

    rows.append({
        'date': d, 'mmdd': d[5:],
        'valley_thermal': round(valley_thermal, 0),
        'valley_act_thermal': round(valley_act_thermal, 0),
        'valley_num': round(valley_num, 1),
        'valley_dispatched': round(valley_dispatched, 0),
        'must_run_est': round(must_run_est_13pct, 0),
        'must_run_units': must_run_units_est,
        'reg_units': round(reg_units, 1),
        'reg_output': round(reg_output, 0),
        'reg_output_act': round(reg_output_act, 0),
        'unit_output_reg': round(unit_output_reg, 0),
        'unit_output_reg_act': round(unit_output_reg_act, 0),
        'unit_output_all': round(unit_output_all, 0),
        'da_price': round(da_p, 1),
        'rt_price': round(rt_p, 1),
        'rt_min': round(rt_min, 1),
        'is_floor': is_floor,
    })

# ── 3. 统计对比 ──
floor_days = [r for r in rows if r['is_floor']]
normal_days = [r for r in rows if not r['is_floor']]

print(f'\n=== 3. 地板价日({len(floor_days)}) vs 正常日({len(normal_days)}) ===')
print(f'{"指标":<25}{"地板价日":<15}{"正常日":<15}{"区分度":<10}')
print('-' * 65)
for key, label in [
    ('valley_thermal', '谷段火电(MW)'),
    ('valley_act_thermal', '谷段实际火电(MW)'),
    ('valley_dispatched', '谷段直调负荷(MW)'),
    ('must_run_est', '必开估算(MW)'),
    ('reg_output', '调节出力(日前,MW)'),
    ('reg_output_act', '调节出力(实际,MW)'),
    ('unit_output_reg', '单台调节出力(日前)'),
    ('unit_output_reg_act', '单台调节出力(实际)'),
    ('unit_output_all', '单台出力含必开(旧)'),
    ('da_price', '谷段日前电价'),
    ('rt_price', '谷段实时电价'),
]:
    f_vals = [r[key] for r in floor_days]
    n_vals = [r[key] for r in normal_days]
    fm = sum(f_vals)/len(f_vals) if f_vals else 0
    nm = sum(n_vals)/len(n_vals) if n_vals else 0
    sep = abs(nm - fm) / ((nm + fm) / 2) * 100 if (nm + fm) != 0 else 0
    print(f'{label:<25}{fm:<15.0f}{nm:<15.0f}{sep:<10.1f}%')

# ── 4. 按单台调节出力分段统计 ──
print(f'\n=== 4. 按单台调节出力(日前)分段 ===')
for lo, hi in [(0,100),(100,130),(130,160),(160,190),(190,220),(220,300),(300,500)]:
    group = [r for r in rows if lo <= r['unit_output_reg'] < hi]
    n = len(group)
    floor_n = sum(1 for r in group if r['is_floor'])
    avg_rt = sum(r['rt_price'] for r in group) / n if n else 0
    print(f'{lo}-{hi}MW: {n:>2}天, 地板价{floor_n:>2}天({floor_n/n*100 if n else 0:.0f}%), 平均实时{avg_rt:.0f}元')

# ── 5. 关键阈值 ──
print(f'\n=== 5. 关键阈值分析 ===')
for th in [130, 150, 170, 190, 210, 250]:
    below = [r for r in rows if r['unit_output_reg'] < th]
    above = [r for r in rows if r['unit_output_reg'] >= th]
    fb = sum(1 for r in below if r['is_floor']) / len(below) * 100 if below else 0
    fa = sum(1 for r in above if r['is_floor']) / len(above) * 100 if above else 0
    print(f'单台调节<{th}MW: {len(below):>2}天 地板价率{fb:.0f}% | ≥{th}MW: {len(above):>2}天 地板价率{fa:.0f}%')

# ── 6. 地板价日详细列表（按单台调节出力排序） ──
print(f'\n=== 6. 地板价日详细（按单台调节出力排序） ===')
print(f'{"日期":<12}{"单台调节":<10}{"单台含必开":<12}{"火电":<10}{"台数":<8}{"必开":<8}{"调节":<8}{"实时电价":<10}')
for r in sorted(floor_days, key=lambda x: x['unit_output_reg']):
    print(f"{r['mmdd']:<12}{r['unit_output_reg']:<10.0f}{r['unit_output_all']:<12.0f}{r['valley_thermal']:<10.0f}{r['valley_num']:<8.1f}{r['must_run_est']:<8.0f}{r['reg_output']:<8.0f}{r['rt_price']:<10.1f}")

# ── 7. 输出HTML ──
OUT_DIR = r'E:\DataWork\Storage_Strategy\output\竞价空间分析结果'
os.makedirs(OUT_DIR, exist_ok=True)
html_path = os.path.join(OUT_DIR, '单台调节机组出力_vs_地板价_修正版.html')

dates_js = json.dumps([r['mmdd'] for r in rows], ensure_ascii=False)
unit_reg = json.dumps([r['unit_output_reg'] for r in rows])
unit_all = json.dumps([r['unit_output_all'] for r in rows])
rt_p = json.dumps([r['rt_price'] for r in rows])
floor_flags = json.dumps([1 if r['is_floor'] else 0 for r in rows])

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>单台调节机组出力 vs 地板价(修正版) | 5-7月</title>
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
<h1>单台调节机组出力 vs 地板价(修正版) | 5-7月</h1>
<div class="info">必开估算=谷段直调负荷×13% · 调节出力=谷段火电-必开 · 单台调节=调节出力/调节台数 · 地板价=谷段实时≤0或最低≤-50 · {len(rows)}天</div>
</div>
<div class="panel"><div class="t">单台调节机组出力(扣除必开) vs 单台出力(含必开) + 实时电价（红柱=地板价日）</div><div class="c" id="c1"></div></div>
<div class="panel"><div class="t">散点：单台调节机组出力 vs 实时电价（红色=地板价日）</div><div class="c" id="c2"></div></div>
<div class="footer">润津储能 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} · 必开=直调负荷×13%</div>
<script>
var D={dates_js};var N={len(rows)};
var g={{left:55,right:90,top:20,bottom:50}};
var ec={{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var ec2={{axisLabel:{{color:'#e67e22',fontSize:10}},axisLine:{{lineStyle:{{color:'#e67e22'}}}},splitLine:{{show:false}}}};
var el={{textStyle:{{color:'#666',fontSize:10}},top:3}};
var floorIdx={floor_flags};
var unitReg={unit_reg};var unitAll={unit_all};
var colors=[];for(var i=0;i<N;i++)colors.push(floorIdx[i]?'#d13438':'#0078d4');

var c1=echarts.init(document.getElementById('c1'));
c1.setOption({{
grid:g,tooltip:{{trigger:'axis',formatter:function(ps){{
  var i=ps[0].dataIndex;var s=D[i]+'<br/>';
  ps.forEach(function(p){{s+=p.marker+p.seriesName+':'+p.value.toFixed(0)+'<br/>';}});
  s+=floorIdx[i]?'<b style="color:red">地板价日</b>':'正常日';return s;
}}}}}},
legend:Object.assign({{data:['单台调节出力(扣除必开)','单台出力(含必开)','实时电价']}},el),
dataZoom:[{{type:'slider',start:0,end:100,height:25,bottom:10}},{{type:'inside'}}],
xAxis:Object.assign({{type:'category',data:D,axisLabel:{{interval:Math.floor(N/20),fontSize:9,rotate:45}}}},ec),
yAxis:[Object.assign({{type:'value',name:'MW'}},ec),Object.assign({{type:'value',name:'元/MWh'}},ec2)],
series:[
  {{name:'单台调节出力(扣除必开)',type:'bar',data:unitReg.map(function(v,i){{return{{value:v,itemStyle:{{color:colors[i]}}}}}}),barWidth:6}},
  {{name:'单台出力(含必开)',type:'bar',data:unitAll,barWidth:6,itemStyle:{{color:'#999',opacity:0.5}}}},
  {{name:'实时电价',type:'line',data:rt_p_data,smooth:true,lineStyle:{{width:2,color:'#e67e22'}},itemStyle:{{color:'#e67e22'}},symbol:'none',yAxisIndex:1}}
]
}});

var scatter=[],floorScatter=[];
var rt_p_data={rt_p};
for(var i=0;i<N;i++){{var pt=[unitReg[i],rt_p_data[i]];floorIdx[i]?floorScatter.push(pt):scatter.push(pt);}}
var c2=echarts.init(document.getElementById('c2'));
c2.setOption({{
grid:g,tooltip:{{trigger:'item',formatter:function(p){{return D[p.dataIndex]+'<br/>单台调节:'+p.value[0].toFixed(0)+'MW<br/>实时:'+p.value[1].toFixed(1)+'元';}}}},
xAxis:Object.assign({{type:'value',name:'单台调节机组出力(MW)'}},ec),
yAxis:Object.assign({{type:'value',name:'谷段实时电价(元/MWh)'}},ec),
series:[
  {{name:'正常日',type:'scatter',data:scatter,symbolSize:8,itemStyle:{{color:'#0078d4'}}}},
  {{name:'地板价日',type:'scatter',data:floorScatter,symbolSize:10,itemStyle:{{color:'#d13438'}}}}
]
}});
window.addEventListener('resize',function(){{[c1,c2].forEach(function(c){{c.resize();}});}});
</script>
</body>
</html>'''

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'\nSaved: {html_path} ({len(html.encode("utf-8")):,} bytes)')
print(f'Done. {len(rows)} days, {len(floor_days)} floor-price days.')