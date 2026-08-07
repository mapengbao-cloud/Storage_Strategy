"""5-7月 火电出清 峰谷对标分析
每天10个值：
1-3: 日前火电出清 2h谷值均值(MW), 2h峰值均值(MW), 谷/峰百分比(%)
4-6: 实际火电出清 2h谷值均值(MW), 2h峰值均值(MW), 谷/峰百分比(%)
7-8: 谷时段 日前电价均值(元/MWh), 实时电价均值(元/MWh)
9-10: 峰时段 日前电价均值(元/MWh), 实时电价均值(元/MWh)

实际火电出清 = 竞价空间(实际) - 地方公用电厂 - (独立储能+抽蓄+虚拟)*4
峰谷窗口：从96点日前火电出清中找2h连续窗口(8点)和最大/最小和
"""
import pymysql, os, json
from datetime import datetime, date
from collections import defaultdict
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# ── 数据库连接 ──
for line in open(r'E:\DataWork\Storage_Strategy\.env', encoding='utf-8'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

conn = pymysql.connect(
    host=os.getenv('DB_TIANJI_HOST'), port=int(os.getenv('DB_TIANJI_PORT', 3306)),
    user=os.getenv('DB_TIANJI_USER'), password=os.getenv('DB_TIANJI_PASSWORD'),
    database=os.getenv('DB_TIANJI_DATABASE'), charset='utf8mb4',
    connect_timeout=10, read_timeout=120)
cur = conn.cursor()
MEMBER_ID = 'b9e64e64a713458eba94c9af05c0a757'

# ── 1. 日前火电出清 + 独立储能/抽蓄/虚拟 (96点) ──
print('Loading dayahead clearing quantity...')
cur.execute("""SELECT date, time_point, thermal_clearing, independent_clearing, draw_clearing, virtual_clearing
    FROM shandong_px_dayahead_clearing_quantity_number
    WHERE date >= '2026-05-01' AND date <= '2026-07-31'
    ORDER BY date, time_point""")
da_clearing = defaultdict(list)
for r in cur.fetchall():
    d = str(r[0])
    da_clearing[d].append({
        'thermal': float(r[2] or 0) * 4,  # MWh→MW
        'es_dr_vi': (float(r[3] or 0) + float(r[4] or 0) + float(r[5] or 0)) * 4
    })
print(f'  dayahead clearing: {len(da_clearing)} dates')

# ── 2. 实际竞价空间 + 地方公用电厂 (96点) ──
print('Loading actual load info...')
cur.execute("""SELECT date, time_order,
    actual_dispatched_load, actual_tie_line_load, actual_wind_power,
    actual_photovoltaic_power, actual_nuclear_power, actual_self_power,
    actual_local_power
    FROM shandong_px_spot_actual_load_info
    WHERE date >= '2026-05-01' AND date <= '2026-07-31'
    ORDER BY date, time_order""")
actual_load = defaultdict(list)
for r in cur.fetchall():
    d = str(r[0])
    dispatched = float(r[2] or 0)
    tie_line = float(r[3] or 0)
    wind = float(r[4] or 0)
    pv = float(r[5] or 0)
    nuclear = float(r[6] or 0)
    self_p = float(r[7] or 0)
    local_p = float(r[8] or 0)
    bs = dispatched - tie_line - wind - pv - nuclear - self_p
    actual_load[d].append({'bs': bs, 'local': local_p})
print(f'  actual load: {len(actual_load)} dates')

# ── 3. 日前电价 (润津96点) ──
print('Loading dayahead price...')
cur.execute("""SELECT date, time_point, price
    FROM shandong_px_reliable_clearing_unit_data
    WHERE date >= '2026-05-01' AND date <= '2026-07-31'
    AND member_id = %s
    AND unit_name NOT LIKE '%%发电%%' AND unit_name NOT LIKE '%%用电%%'
    ORDER BY date, time_point""", (MEMBER_ID,))
da_price = defaultdict(list)
for r in cur.fetchall():
    da_price[str(r[0])].append(float(r[2] or 0))
print(f'  dayahead price: {len(da_price)} dates')

# ── 4. 实时电价 (润津96点) ──
print('Loading realtime price...')
cur.execute("""SELECT date, time_point, price
    FROM shandong_px_realtime_clearing_results_query
    WHERE date >= '2026-05-01' AND date <= '2026-07-31'
    AND member_id = %s
    ORDER BY date, time_point""", (MEMBER_ID,))
rt_price = defaultdict(list)
for r in cur.fetchall():
    rt_price[str(r[0])].append(float(r[2] or 0))
print(f'  realtime price: {len(rt_price)} dates')

cur.close(); conn.close()

# ── 交叠日期 ──
common_dates = sorted(set(da_clearing.keys()) & set(actual_load.keys()) &
                      set(da_price.keys()) & set(rt_price.keys()))
print(f'\nCommon dates: {len(common_dates)} ({common_dates[0]} ~ {common_dates[-1]})')

# ── 峰谷窗口查找（从日前火电出清） ──
def find_peak_valley_windows(thermal_curve):
    """Return (valley_start_idx, peak_start_idx) for 2h (8 point) windows."""
    W = 8
    best_valley_idx = 0
    best_valley_sum = float('inf')
    best_peak_idx = 0
    best_peak_sum = float('-inf')
    for i in range(len(thermal_curve) - W + 1):
        s = sum(thermal_curve[i:i+W])
        if s < best_valley_sum:
            best_valley_sum = s
            best_valley_idx = i
        if s > best_peak_sum:
            best_peak_sum = s
            best_peak_idx = i
    return best_valley_idx, best_peak_idx

TIMES = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0, 15, 30, 45)]

# ── 逐日计算 ──
rows = []
for d in common_dates:
    da = da_clearing[d]
    al = actual_load[d]
    dp = da_price.get(d, [])
    rp = rt_price.get(d, [])
    if len(da) != 96 or len(al) != 96 or len(dp) != 96 or len(rp) != 96:
        continue

    # 日前火电出清
    th_da = [x['thermal'] for x in da]
    # 实际火电出清 = 竞价空间 - 地方公用电厂 - (独立储能+抽蓄+虚拟)*4
    th_actual = [al[i]['bs'] - al[i]['local'] - da[i]['es_dr_vi'] for i in range(96)]

    # 峰谷窗口
    vi, pi = find_peak_valley_windows(th_da)
    W = 8

    # 日前火电
    da_valley_mean = sum(th_da[vi:vi+W]) / W
    da_peak_mean = sum(th_da[pi:pi+W]) / W
    da_vp_pct = da_valley_mean / da_peak_mean * 100 if da_peak_mean else 0

    # 实际火电
    act_valley_mean = sum(th_actual[vi:vi+W]) / W
    act_peak_mean = sum(th_actual[pi:pi+W]) / W
    act_vp_pct = act_valley_mean / act_peak_mean * 100 if act_peak_mean else 0

    # 日前电价
    da_p_valley = sum(dp[vi:vi+W]) / W
    da_p_peak = sum(dp[pi:pi+W]) / W

    # 实时电价
    rt_p_valley = sum(rp[vi:vi+W]) / W
    rt_p_peak = sum(rp[pi:pi+W]) / W

    rows.append({
        'date': d,
        'mmdd': d[5:],
        'da_valley_mw': round(da_valley_mean, 1),
        'da_peak_mw': round(da_peak_mean, 1),
        'da_vp_pct': round(da_vp_pct, 1),
        'act_valley_mw': round(act_valley_mean, 1),
        'act_peak_mw': round(act_peak_mean, 1),
        'act_vp_pct': round(act_vp_pct, 1),
        'da_price_valley': round(da_p_valley, 1),
        'rt_price_valley': round(rt_p_valley, 1),
        'da_price_peak': round(da_p_peak, 1),
        'rt_price_peak': round(rt_p_peak, 1),
        'valley_start': TIMES[vi],
        'valley_end': TIMES[vi+W-1],
        'peak_start': TIMES[pi],
        'peak_end': TIMES[pi+W-1],
    })

print(f'Computed: {len(rows)} days')

# ══════════════════════════════════════════════════════════════
# 输出 Excel
# ══════════════════════════════════════════════════════════════
OUT_DIR = r'E:\DataWork\Storage_Strategy\output\竞价空间分析结果'
os.makedirs(OUT_DIR, exist_ok=True)
xlsx_path = os.path.join(OUT_DIR, '火电峰谷对标_5-7月.xlsx')

wb = openpyxl.Workbook()
ws = wb.active
ws.title = '火电峰谷对标'

# 样式
hdr_font = Font(name='Microsoft YaHei', size=10, bold=True, color='FFFFFF')
hdr_fill = PatternFill(start_color='0078D4', end_color='0078D4', fill_type='solid')
hdr_fill2 = PatternFill(start_color='2C7BE5', end_color='2C7BE5', fill_type='solid')
hdr_fill3 = PatternFill(start_color='E67E22', end_color='E67E22', fill_type='solid')
data_font = Font(name='Microsoft YaHei', size=10)
pct_font = Font(name='Microsoft YaHei', size=10, bold=True)
thin_border = Border(
    left=Side(style='thin', color='D0D0D0'),
    right=Side(style='thin', color='D0D0D0'),
    top=Side(style='thin', color='D0D0D0'),
    bottom=Side(style='thin', color='D0D0D0'))
center = Alignment(horizontal='center', vertical='center', wrap_text=True)

# 标题行
title_row = ['日期', '日期(MMDD)',
    '日前火电谷值\n均值(MW)', '日前火电峰值\n均值(MW)', '日前谷/峰\n百分比(%)',
    '实际火电谷值\n均值(MW)', '实际火电峰值\n均值(MW)', '实际谷/峰\n百分比(%)',
    '谷段日前电价\n(元/MWh)', '谷段实时电价\n(元/MWh)',
    '峰段日前电价\n(元/MWh)', '峰段实时电价\n(元/MWh)',
    '谷段窗口', '峰段窗口']

for c, t in enumerate(title_row, 1):
    cell = ws.cell(row=1, column=c, value=t)
    cell.font = hdr_font
    if c in (3, 4, 5):
        cell.fill = hdr_fill
    elif c in (6, 7, 8):
        cell.fill = hdr_fill2
    elif c in (9, 10, 11, 12):
        cell.fill = hdr_fill3
    else:
        cell.fill = hdr_fill
    cell.alignment = center
    cell.border = thin_border

# 数据行
for i, r in enumerate(rows):
    row_num = i + 2
    vals = [r['date'], r['mmdd'],
        r['da_valley_mw'], r['da_peak_mw'], r['da_vp_pct'],
        r['act_valley_mw'], r['act_peak_mw'], r['act_vp_pct'],
        r['da_price_valley'], r['rt_price_valley'],
        r['da_price_peak'], r['rt_price_peak'],
        f"{r['valley_start']}-{r['valley_end']}",
        f"{r['peak_start']}-{r['peak_end']}"]
    for c, v in enumerate(vals, 1):
        cell = ws.cell(row=row_num, column=c, value=v)
        cell.font = pct_font if c in (5, 8) else data_font
        cell.alignment = center
        cell.border = thin_border
        if isinstance(v, (int, float)):
            cell.number_format = '0.0' if c in (5, 8) else '0'

# 列宽
widths = [12, 12, 16, 16, 14, 16, 16, 14, 16, 16, 16, 16, 18, 18]
for c, w in enumerate(widths, 1):
    ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = w

ws.freeze_panes = 'A2'
wb.save(xlsx_path)
print(f'Saved: {xlsx_path}')

# ══════════════════════════════════════════════════════════════
# 输出 HTML
# ══════════════════════════════════════════════════════════════
html_path = os.path.join(OUT_DIR, '火电峰谷对标_5-7月.html')

dates_js = json.dumps([r['date'] for r in rows], ensure_ascii=False)
mmdd_js = json.dumps([r['mmdd'] for r in rows], ensure_ascii=False)
da_valley = json.dumps([r['da_valley_mw'] for r in rows])
da_peak = json.dumps([r['da_peak_mw'] for r in rows])
da_vp = json.dumps([r['da_vp_pct'] for r in rows])
act_valley = json.dumps([r['act_valley_mw'] for r in rows])
act_peak = json.dumps([r['act_peak_mw'] for r in rows])
act_vp = json.dumps([r['act_vp_pct'] for r in rows])
da_pv = json.dumps([r['da_price_valley'] for r in rows])
rt_pv = json.dumps([r['rt_price_valley'] for r in rows])
da_pp = json.dumps([r['da_price_peak'] for r in rows])
rt_pp = json.dumps([r['rt_price_peak'] for r in rows])

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>火电峰谷对标 | 5-7月</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}}
.header{{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600;margin-bottom:4px}}
.header .info{{font-size:11px;color:#888}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:8px 24px}}
.panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.panel .t{{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.panel .c{{width:100%;height:400px}}
.panel.full{{grid-column:1/-1}}
.panel.full .c{{height:480px}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
</style>
</head>
<body>
<div class="header">
<h1>火电日前出清 & 实际出清 峰谷对标 | 5-7月</h1>
<div class="info">窗口：2h滑动窗口(8个15min点) · 实际火电=竞价空间(实际)-地方公用电厂-(独立储能+抽蓄+虚拟)×4 · {len(rows)}天 · 数据来源：天机库</div>
</div>
<div class="grid">
<div class="panel full"><div class="t">日前火电出清 谷值/峰值(MW) + 谷/峰百分比(%)</div><div class="c" id="c1"></div></div>
<div class="panel full"><div class="t">实际火电出清 谷值/峰值(MW) + 谷/峰百分比(%)</div><div class="c" id="c2"></div></div>
<div class="panel"><div class="t">日前 vs 实际 谷/峰百分比(%) 对比</div><div class="c" id="c3"></div></div>
<div class="panel"><div class="t">日前火电谷值 vs 实际火电谷值(MW) 散点</div><div class="c" id="c4"></div></div>
<div class="panel full"><div class="t">谷时段电价 日前 vs 实时(元/MWh) + 峰时段电价 日前 vs 实时(元/MWh)</div><div class="c" id="c5"></div></div>
</div>
<div class="footer">润津储能 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} · 实际火电=竞价空间(实际)-地方公用电厂-日前独立储能/抽蓄/虚拟×4</div>
<script>
var D={mmdd_js};
var N={len(rows)};
var g={{left:55,right:90,top:20,bottom:50}};
var ec={{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var ec2={{axisLabel:{{color:'#e67e22',fontSize:10}},axisLine:{{lineStyle:{{color:'#e67e22'}}}},splitLine:{{show:false}}}};
var el={{textStyle:{{color:'#666',fontSize:10}},top:3}};

// Chart 1: 日前火电谷值/峰值 + 百分线
var c1=echarts.init(document.getElementById('c1'));
c1.setOption({{
grid:g,tooltip:{{trigger:'axis'}},
legend:Object.assign({{data:['日前谷值','日前峰值','谷/峰%']}},el),
dataZoom:[{{type:'slider',start:0,end:100,height:25,bottom:10}},{{type:'inside'}}],
xAxis:Object.assign({{type:'category',data:D,axisLabel:{{interval:Math.floor(N/20),fontSize:9,rotate:45}}}},ec),
yAxis:[
  Object.assign({{type:'value',name:'MW'}},ec),
  Object.assign({{type:'value',name:'%',min:0,max:100}},ec2)
],
series:[
  {{name:'日前谷值',type:'bar',data:{da_valley},barWidth:6,itemStyle:{{color:'#0078d4'}}}},
  {{name:'日前峰值',type:'bar',data:{da_peak},barWidth:6,itemStyle:{{color:'#d13438'}}}},
  {{name:'谷/峰%',type:'line',data:{da_vp},smooth:false,lineStyle:{{width:2,color:'#e67e22'}},itemStyle:{{color:'#e67e22'}},symbol:'none',yAxisIndex:1}}
]
}});

// Chart 2: 实际火电谷值/峰值 + 百分线
var c2=echarts.init(document.getElementById('c2'));
c2.setOption({{
grid:g,tooltip:{{trigger:'axis'}},
legend:Object.assign({{data:['实际谷值','实际峰值','实际谷/峰%']}},el),
dataZoom:[{{type:'slider',start:0,end:100,height:25,bottom:10}},{{type:'inside'}}],
xAxis:Object.assign({{type:'category',data:D,axisLabel:{{interval:Math.floor(N/20),fontSize:9,rotate:45}}}},ec),
yAxis:[
  Object.assign({{type:'value',name:'MW'}},ec),
  Object.assign({{type:'value',name:'%',min:0,max:100}},ec2)
],
series:[
  {{name:'实际谷值',type:'bar',data:{act_valley},barWidth:6,itemStyle:{{color:'#2c7be5'}}}},
  {{name:'实际峰值',type:'bar',data:{act_peak},barWidth:6,itemStyle:{{color:'#e74c3c'}}}},
  {{name:'实际谷/峰%',type:'line',data:{act_vp},smooth:false,lineStyle:{{width:2,color:'#e67e22'}},itemStyle:{{color:'#e67e22'}},symbol:'none',yAxisIndex:1}}
]
}});

// Chart 3: 日前 vs 实际 谷/峰% 对比
var c3=echarts.init(document.getElementById('c3'));
c3.setOption({{
grid:g,tooltip:{{trigger:'axis'}},
legend:Object.assign({{data:['日前谷/峰%','实际谷/峰%']}},el),
dataZoom:[{{type:'slider',start:0,end:100,height:25,bottom:10}},{{type:'inside'}}],
xAxis:Object.assign({{type:'category',data:D,axisLabel:{{interval:Math.floor(N/20),fontSize:9,rotate:45}}}},ec),
yAxis:Object.assign({{type:'value',name:'%',min:0,max:100}},ec),
series:[
  {{name:'日前谷/峰%',type:'line',data:{da_vp},smooth:true,lineStyle:{{width:2,color:'#0078d4'}},itemStyle:{{color:'#0078d4'}},symbol:'none'}},
  {{name:'实际谷/峰%',type:'line',data:{act_vp},smooth:true,lineStyle:{{width:2,color:'#2c7be5'}},itemStyle:{{color:'#2c7be5'}},symbol:'none'}}
]
}});

// Chart 4: 散点
var c4=echarts.init(document.getElementById('c4'));
var scatter_data=[];
for(var i=0;i<N;i++) scatter_data.push([{da_valley}[i],{act_valley}[i]]);
c4.setOption({{
grid:g,tooltip:{{trigger:'item',formatter:function(p){{return D[p.dataIndex]+'<br/>日前谷值:'+p.value[0].toFixed(0)+' MW<br/>实际谷值:'+p.value[1].toFixed(0)+' MW';}}}},
xAxis:Object.assign({{type:'value',name:'日前火电谷值(MW)'}},ec),
yAxis:Object.assign({{type:'value',name:'实际火电谷值(MW)'}},ec),
series:[
  {{type:'scatter',data:scatter_data,symbolSize:6,itemStyle:{{color:'#0078d4'}},
    markLine:{{silent:true,data:[{{type:'min',lineStyle:{{color:'#999',type:'dashed'}}}},{{type:'max',lineStyle:{{color:'#999',type:'dashed'}}}}],
    lineStyle:{{color:'#ccc'}},label:{{formatter:'y=x'}}}}}}
]
}});

// Chart 5: 电价 谷峰 日前vs实时
var c5=echarts.init(document.getElementById('c5'));
c5.setOption({{
grid:Object.assign({{}},g,{{bottom:60}}),tooltip:{{trigger:'axis'}},
legend:Object.assign({{data:['谷段日前电价','谷段实时电价','峰段日前电价','峰段实时电价']}},el),
dataZoom:[{{type:'slider',start:0,end:100,height:25,bottom:10}},{{type:'inside'}}],
xAxis:Object.assign({{type:'category',data:D,axisLabel:{{interval:Math.floor(N/20),fontSize:9,rotate:45}}}},ec),
yAxis:Object.assign({{type:'value',name:'元/MWh'}},ec),
series:[
  {{name:'谷段日前电价',type:'line',data:{da_pv},smooth:true,lineStyle:{{width:2,color:'#0078d4'}},itemStyle:{{color:'#0078d4'}},symbol:'none'}},
  {{name:'谷段实时电价',type:'line',data:{rt_pv},smooth:true,lineStyle:{{width:2,color:'#00bcd4'}},itemStyle:{{color:'#00bcd4'}},symbol:'none'}},
  {{name:'峰段日前电价',type:'line',data:{da_pp},smooth:true,lineStyle:{{width:2,color:'#d13438'}},itemStyle:{{color:'#d13438'}},symbol:'none'}},
  {{name:'峰段实时电价',type:'line',data:{rt_pp},smooth:true,lineStyle:{{width:2,color:'#e67e22'}},itemStyle:{{color:'#e67e22'}},symbol:'none'}}
]
}});

window.addEventListener('resize',function(){{[c1,c2,c3,c4,c5].forEach(function(c){{c.resize();}});}});
</script>
</body>
</html>'''

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved: {html_path} ({len(html.encode("utf-8")):,} bytes UTF-8)')
print(f'\nDone. {len(rows)} days, 5-7月.')