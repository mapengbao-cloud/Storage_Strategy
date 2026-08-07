"""地板价日调节机组统计
1. 从预调度表识别必开/调节机组（CV<5%=必开，其余=调节）
2. 计算调节机组谷段总容量和单台均值（从预调度）
3. 输出所有地板价日的调节机组统计到 Excel
4. 输出 3 天的火电分类数据到 HTML 供人工校核
"""
import pymysql, os, json, math
from collections import defaultdict
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

for line in open(r'E:\DataWork\Storage_Strategy\.env', encoding='utf-8'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

conn = pymysql.connect(host=os.getenv('DB_TIANJI_HOST'), port=int(os.getenv('DB_TIANJI_PORT', 3306)),
    user=os.getenv('DB_TIANJI_USER'), password=os.getenv('DB_TIANJI_PASSWORD'),
    database=os.getenv('DB_TIANJI_DATABASE'), charset='utf8mb4')
cur = conn.cursor()
MEMBER_ID = 'b9e64e64a713458eba94c9af05c0a757'

# ── 1. 获取所有地板价日（5-7月，有预调度数据） ──
print('=== 1. 获取地板价日 ===')
cur.execute("""SELECT DISTINCT date FROM shandong_px_realtime_clearing_results_query
    WHERE date >= '2026-05-01' AND date <= '2026-07-31' AND member_id = %s
    ORDER BY date""", (MEMBER_ID,))
price_dates = set(str(r[0]) for r in cur.fetchall())

cur.execute("""SELECT DISTINCT date FROM shandong_px_provincial_prescheduling_results
    WHERE date >= '2026-05-01' AND date <= '2026-07-31'
    ORDER BY date""")
presched_dates = set(str(r[0]) for r in cur.fetchall())

common_dates = sorted(price_dates & presched_dates)
print(f'共同日期: {len(common_dates)}')

# 获取实时电价，判断地板价
floor_dates = []
for d in common_dates:
    cur.execute("""SELECT time_point, price FROM shandong_px_realtime_clearing_results_query
        WHERE date=%s AND member_id=%s ORDER BY time_point""", (d, MEMBER_ID))
    rows = cur.fetchall()
    if len(rows) != 96:
        continue
    prices = [float(r[1] or 0) for r in rows]
    # 2h谷段窗口
    W = 8
    best_vs = float('inf')
    best_vi = 0
    for i in range(96 - W + 1):
        s = sum(prices[i:i+W])
        if s < best_vs:
            best_vs = s
            best_vi = i
    valley_mean = sum(prices[best_vi:best_vi+W]) / W
    valley_min = min(prices[best_vi:best_vi+W])
    is_floor = valley_mean <= 0 or valley_min <= -50
    if is_floor:
        floor_dates.append((d, best_vi, valley_mean, valley_min))

print(f'地板价日: {len(floor_dates)}')

# ── 2. 逐日分析调节机组 ──
print('\n=== 2. 逐日分析 ===')

all_results = []
for d, valley_idx, valley_mean, valley_min in floor_dates:
    # 获取该日所有火电机组（排除储能）
    # 注意: 某些日期所有机组 declaration_power 全为 0，需要特殊处理
    cur.execute("""SELECT generator_name, AVG(declaration_power), STDDEV(declaration_power),
        MIN(declaration_power), MAX(declaration_power)
        FROM shandong_px_provincial_prescheduling_results
        WHERE date=%s
        AND (generator_name LIKE '%%#%%' OR generator_name LIKE '%%机%%')
        AND generator_name NOT LIKE '%%储能%%'
        GROUP BY generator_name""", (d,))
    rows = cur.fetchall()

    # 检查是否所有机组出力都是0（数据异常）
    all_zero = all(float(r[1] or 0) == 0 for r in rows) if rows else True

    must_run = []
    regulating = []
    for r in rows:
        name, avg, std, min_p, max_p = r
        avg_f = float(avg) if avg else 0
        std_f = float(std) if std else 0
        min_f = float(min_p) if min_p else 0
        max_f = float(max_p) if max_p else 0
        cv = std_f / avg_f * 100 if avg_f > 0 else 0

        # 必开: CV<5% 或 min/avg > 0.9 (接近恒定)
        # 排除核电（核电也是必开，但这里我们关注火电）
        is_nuclear = '核' in name
        if is_nuclear:
            must_run.append((name, avg_f, min_f, max_f, cv, 'nuclear'))
        elif cv < 5 or (min_f / avg_f > 0.9 if avg_f > 0 else False):
            must_run.append((name, avg_f, min_f, max_f, cv, 'thermal'))
        else:
            regulating.append((name, avg_f, min_f, max_f, cv))

    if all_zero:
        print(f'{d}: [数据异常] 所有机组出力为0, 火电{len(rows)}台')
        all_results.append({
            'date': d,
            'valley_mean': valley_mean,
            'valley_min': valley_min,
            'must_run_count': 0,
            'must_run_total': 0,
            'regulating_count': 0,
            'regulating_total_avg': 0,
            'regulating_valley_total': 0,
            'regulating_valley_avg': 0,
            'regulating_units': [],
            'must_run_units': [],
            'data_quality': 'all_zero',
        })
        continue

    # 计算调节机组谷段出力（用谷段窗口的预调度功率）
    regulating_valley_total = 0
    regulating_valley_units = []
    for name, avg, min_p, max_p, cv in regulating:
        # 获取该机组谷段窗口的预调度功率
        cur.execute("""SELECT time_order, declaration_power FROM shandong_px_provincial_prescheduling_results
            WHERE date=%s AND generator_name=%s ORDER BY time_order""", (d, name))
        unit_rows = cur.fetchall()
        if len(unit_rows) == 96:
            unit_powers = [float(r[1]) for r in unit_rows]
            valley_power = sum(unit_powers[valley_idx:valley_idx+8]) / 8
            regulating_valley_total += valley_power
            regulating_valley_units.append((name, valley_power, avg, min_p, max_p, cv))

    n_reg = len(regulating_valley_units)
    avg_valley = regulating_valley_total / n_reg if n_reg > 0 else 0

    all_results.append({
        'date': d,
        'valley_mean': valley_mean,
        'valley_min': valley_min,
        'must_run_count': len(must_run),
        'must_run_total': sum(r[1] for r in must_run),
        'regulating_count': n_reg,
        'regulating_total_avg': sum(r[1] for r in regulating),
        'regulating_valley_total': regulating_valley_total,
        'regulating_valley_avg': avg_valley,
        'regulating_units': regulating_valley_units,
        'must_run_units': must_run,
    })

    print(f'{d}: 调节{n_reg}台, 谷段总容量{regulating_valley_total:.0f}MW, 单台均值{avg_valley:.0f}MW')

# ── 3. 输出 Excel ──
print('\n=== 3. 输出 Excel ===')
OUT_DIR = r'E:\DataWork\Storage_Strategy\output\竞价空间分析结果'
os.makedirs(OUT_DIR, exist_ok=True)
xlsx_path = os.path.join(OUT_DIR, '地板价日调节机组统计.xlsx')

wb = openpyxl.Workbook()

# Sheet 1: 每日汇总
ws1 = wb.active
ws1.title = '每日汇总'
headers = ['日期', '谷段实时均价', '谷段实时最低', '必开台数', '必开总容量(MW)',
           '调节台数', '调节总容量(MW)', '调节谷段总容量(MW)', '调节谷段单台均值(MW)']
for c, h in enumerate(headers, 1):
    cell = ws1.cell(row=1, column=c, value=h)
    cell.font = Font(bold=True, color='FFFFFF')
    cell.fill = PatternFill(start_color='0078D4', end_color='0078D4', fill_type='solid')
    cell.alignment = Alignment(horizontal='center', wrap_text=True)

for i, r in enumerate(all_results, 2):
    ws1.cell(row=i, column=1, value=r['date'])
    ws1.cell(row=i, column=2, value=round(r['valley_mean'], 1))
    ws1.cell(row=i, column=3, value=round(r['valley_min'], 1))
    ws1.cell(row=i, column=4, value=r['must_run_count'])
    ws1.cell(row=i, column=5, value=round(r['must_run_total'], 0))
    ws1.cell(row=i, column=6, value=r['regulating_count'])
    ws1.cell(row=i, column=7, value=round(r['regulating_total_avg'], 0))
    ws1.cell(row=i, column=8, value=round(r['regulating_valley_total'], 0))
    ws1.cell(row=i, column=9, value=round(r['regulating_valley_avg'], 0))

for c in range(1, 10):
    ws1.column_dimensions[openpyxl.utils.get_column_letter(c)].width = 16

# Sheet 2: 调节机组明细（3天示例）
ws2 = wb.create_sheet('调节机组明细')
sample_dates = ['2026-06-01', '2026-06-02', '2026-06-03']
row = 1
for d in sample_dates:
    r = next((x for x in all_results if x['date'] == d), None)
    if not r:
        continue
    ws2.cell(row=row, column=1, value=f'{d} 调节机组明细').font = Font(bold=True, size=12)
    row += 1
    headers2 = ['机组名称', '谷段出力(MW)', '全天平均(MW)', '最小出力(MW)', '最大出力(MW)', 'CV(%)']
    for c, h in enumerate(headers2, 1):
        cell = ws2.cell(row=row, column=c, value=h)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color='E0E0E0', end_color='E0E0E0', fill_type='solid')
    row += 1
    for name, valley_p, avg_p, min_p, max_p, cv in sorted(r['regulating_units'], key=lambda x: x[1], reverse=True):
        ws2.cell(row=row, column=1, value=name)
        ws2.cell(row=row, column=2, value=round(valley_p, 0))
        ws2.cell(row=row, column=3, value=round(avg_p, 0))
        ws2.cell(row=row, column=4, value=round(min_p, 0))
        ws2.cell(row=row, column=5, value=round(max_p, 0))
        ws2.cell(row=row, column=6, value=round(cv, 1))
        row += 1
    row += 2

ws2.column_dimensions['A'].width = 40
for c in range(2, 7):
    ws2.column_dimensions[openpyxl.utils.get_column_letter(c)].width = 14

wb.save(xlsx_path)
print(f'Saved: {xlsx_path}')

# ── 4. 输出 3 天 HTML ──
print('\n=== 4. 输出 HTML ===')

html_dates = ['2026-06-01', '2026-06-02', '2026-06-03']
html_data = {}

for d in html_dates:
    r = next((x for x in all_results if x['date'] == d), None)
    if not r:
        continue

    # 获取该日所有机组的96点曲线
    cur.execute("""SELECT generator_name, time_order, declaration_power
        FROM shandong_px_provincial_prescheduling_results
        WHERE date=%s AND declaration_power > 0
        AND (generator_name LIKE '%%#%%' OR generator_name LIKE '%%机%%')
        AND generator_name NOT LIKE '%%储能%%'
        ORDER BY generator_name, time_order""", (d,))
    rows = cur.fetchall()

    units = defaultdict(dict)
    for name, to, power in rows:
        units[name][int(to)] = float(power)

    # 分类
    unit_curves = {}
    for name, powers in units.items():
        if len(powers) != 96:
            continue
        arr = [powers.get(i, 0) for i in range(1, 97)]
        avg = sum(arr) / len(arr)
        std = math.sqrt(sum((x - avg)**2 for x in arr) / len(arr))
        cv = std / avg * 100 if avg > 0 else 0
        min_p = min(arr)
        max_p = max(arr)

        is_nuclear = '核' in name
        if is_nuclear:
            category = 'nuclear'
        elif cv < 5 or (min_p / avg > 0.9 if avg > 0 else False):
            category = 'must_run'
        else:
            category = 'regulating'

        unit_curves[name] = {
            'curve': arr,
            'avg': avg,
            'min': min_p,
            'max': max_p,
            'cv': cv,
            'category': category,
        }

    html_data[d] = {
        'date': d,
        'valley_mean': r['valley_mean'],
        'valley_min': r['valley_min'],
        'units': unit_curves,
    }

# 生成 HTML
html_path = os.path.join(OUT_DIR, '火电分类校核_3天.html')

# 准备 JS 数据
js_dates = json.dumps([d for d in html_dates if d in html_data], ensure_ascii=False)
js_units = {}
for d in html_dates:
    if d not in html_data:
        continue
    data = html_data[d]
    units_js = []
    for name, u in sorted(data['units'].items(), key=lambda x: x[1]['avg'], reverse=True):
        units_js.append({
            'name': name,
            'curve': u['curve'],
            'avg': round(u['avg'], 1),
            'min': round(u['min'], 1),
            'max': round(u['max'], 1),
            'cv': round(u['cv'], 1),
            'category': u['category'],
        })
    js_units[d] = units_js

js_units_json = json.dumps(js_units, ensure_ascii=False)

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>火电分类校核 | 3天示例</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}}
.header{{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600}}
.header .info{{font-size:11px;color:#888}}
.panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;margin:8px 24px;overflow:hidden}}
.panel .t{{padding:6px 14px;font-size:12px;font-weight:600;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.panel .c{{width:100%;height:500px}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
.date-selector{{padding:8px 24px;background:#fff;border-bottom:1px solid #e0e0e0}}
.date-btn{{display:inline-block;padding:6px 16px;margin-right:8px;border:1px solid #0078d4;background:#fff;color:#0078d4;cursor:pointer;border-radius:3px;font-size:12px}}
.date-btn.active{{background:#0078d4;color:#fff}}
.stats{{display:flex;gap:16px;padding:8px 24px;flex-wrap:wrap}}
.stat-card{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:12px 20px;min-width:140px}}
.stat-card .label{{font-size:11px;color:#888}}
.stat-card .value{{font-size:20px;font-weight:600;color:#2c7be5}}
.stat-card.must .value{{color:#107c10}}
.stat-card.reg .value{{color:#e67e22}}
.stat-card.nuc .value{{color:#d13438}}
</style>
</head>
<body>
<div class="header">
<h1>火电分类校核 | 3天示例</h1>
<div class="info">必开=CV&lt;5% 或 min/avg&gt;0.9 · 调节=其余火电 · 核电单独分类 · 点击日期切换</div>
</div>
<div class="date-selector" id="dateSelector"></div>
<div class="stats" id="statsPanel"></div>
<div class="panel"><div class="t">机组96点出力曲线（按类型着色）</div><div class="c" id="c1"></div></div>
<div class="panel"><div class="t">机组列表（按平均出力排序）</div><div class="c" id="c2" style="height:400px;overflow-y:auto"></div></div>
<div class="footer">润津储能 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} · 数据来源: 天机库预调度表</div>
<script>
var D={js_dates};
var U={js_units_json};
var currentDate=D[0];
var TIMES=[];for(var h=0;h<24;h++)for(var m=0;m<60;m+=15)TIMES.push((h<10?'0':'')+h+':'+(m<10?'0':'')+m);

function renderDateSelector(){{
  var el=document.getElementById('dateSelector');
  el.innerHTML='';
  D.forEach(function(d){{
    var btn=document.createElement('span');
    btn.className='date-btn'+(d===currentDate?' active':'');
    btn.textContent=d;
    btn.onclick=function(){{currentDate=d;render();}};
    el.appendChild(btn);
  }});
}}

function renderStats(){{
  var el=document.getElementById('statsPanel');
  var units=U[currentDate];
  var must=units.filter(function(u){{return u.category==='must_run'}});
  var reg=units.filter(function(u){{return u.category==='regulating'}});
  var nuc=units.filter(function(u){{return u.category==='nuclear'}});
  var mustTotal=must.reduce(function(s,u){{return s+u.avg}},0);
  var regTotal=reg.reduce(function(s,u){{return s+u.avg}},0);
  var nucTotal=nuc.reduce(function(s,u){{return s+u.avg}},0);
  el.innerHTML=
    '<div class="stat-card"><div class="label">日期</div><div class="value">'+currentDate+'</div></div>'+
    '<div class="stat-card must"><div class="label">必开机组</div><div class="value">'+must.length+'台</div></div>'+
    '<div class="stat-card must"><div class="label">必开总容量</div><div class="value">'+mustTotal.toFixed(0)+'MW</div></div>'+
    '<div class="stat-card reg"><div class="label">调节机组</div><div class="value">'+reg.length+'台</div></div>'+
    '<div class="stat-card reg"><div class="label">调节总容量</div><div class="value">'+regTotal.toFixed(0)+'MW</div></div>'+
    '<div class="stat-card nuc"><div class="label">核电</div><div class="value">'+nuc.length+'台</div></div>'+
    '<div class="stat-card nuc"><div class="label">核电总容量</div><div class="value">'+nucTotal.toFixed(0)+'MW</div></div>';
}}

function renderChart(){{
  var units=U[currentDate];
  var series=[];
  var colors={{'must_run':'#107c10','regulating':'#e67e22','nuclear':'#d13438'}};
  var legendData=[];
  units.forEach(function(u){{
    if(legendData.indexOf(u.category)===-1)legendData.push(u.category);
    series.push({{
      name:u.name,
      type:'line',
      data:u.curve,
      lineStyle:{{width:1,color:colors[u.category],opacity:0.7}},
      itemStyle:{{color:colors[u.category]}},
      symbol:'none',
      category:u.category
    }});
  }});
  var c1=echarts.init(document.getElementById('c1'));
  c1.setOption({{
    grid:{{left:55,right:90,top:40,bottom:50}},
    tooltip:{{trigger:'axis',formatter:function(ps){{
      var s=TIMES[ps[0].dataIndex]+'<br/>';
      ps.forEach(function(p){{s+=p.marker+p.seriesName+':'+p.value.toFixed(0)+'MW<br/>';}});
      return s;
    }}}}}},
    legend:{{data:legendData.map(function(c){{return {{name:c,itemStyle:{{color:colors[c]}}}}}}),textStyle:{{color:'#666',fontSize:10}},top:3}},
    xAxis:{{type:'category',data:TIMES,axisLabel:{{color:'#888',fontSize:10,interval:11}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}}}},
    yAxis:{{type:'value',name:'MW',axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}},
    series:series
  }});
}}

function renderTable(){{
  var units=U[currentDate];
  var el=document.getElementById('c2');
  var html='<table style="width:100%;border-collapse:collapse;font-size:11px">';
  html+='<tr style="background:#f5f5f5"><th style="padding:4px;border:1px solid #e0e0e0">机组名称</th><th style="padding:4px;border:1px solid #e0e0e0">类型</th><th style="padding:4px;border:1px solid #e0e0e0">平均(MW)</th><th style="padding:4px;border:1px solid #e0e0e0">最小(MW)</th><th style="padding:4px;border:1px solid #e0e0e0">最大(MW)</th><th style="padding:4px;border:1px solid #e0e0e0">CV(%)</th></tr>';
  units.forEach(function(u){{
    var color=u.category==='must_run'?'#107c10':(u.category==='regulating'?'#e67e22':'#d13438');
    html+='<tr>'+
      '<td style="padding:4px;border:1px solid #e0e0e0">'+u.name+'</td>'+
      '<td style="padding:4px;border:1px solid #e0e0e0;color:'+color+';font-weight:600">'+u.category+'</td>'+
      '<td style="padding:4px;border:1px solid #e0e0e0">'+u.avg+'</td>'+
      '<td style="padding:4px;border:1px solid #e0e0e0">'+u.min+'</td>'+
      '<td style="padding:4px;border:1px solid #e0e0e0">'+u.max+'</td>'+
      '<td style="padding:4px;border:1px solid #e0e0e0">'+u.cv+'</td>'+
    '</tr>';
  }});
  html+='</table>';
  el.innerHTML=html;
}}

function render(){{
  renderDateSelector();
  renderStats();
  renderChart();
  renderTable();
}}
render();
</script>
</body>
</html>'''

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved: {html_path} ({len(html.encode("utf-8")):,} bytes)')

print('\nDone.')
