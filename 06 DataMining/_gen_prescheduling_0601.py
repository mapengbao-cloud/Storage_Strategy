"""Generate 0601 prescheduling analysis HTML."""
import json, math, os, pymysql
from collections import defaultdict
from datetime import datetime

conn = pymysql.connect(host='rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com', port=3306,
    user='pengyiqiang', password='pengyiqiang123', database='tianrun_new',
    charset='utf8mb4', connect_timeout=10, read_timeout=120)
cur = conn.cursor()

DATE = '2026-06-01'
cur.execute(f"""SELECT generator_name, time_order, declaration_power
    FROM shandong_px_provincial_prescheduling_results
    WHERE date='{DATE}'
    ORDER BY generator_name, CAST(time_order AS UNSIGNED)""")
rows = cur.fetchall()
cur.close(); conn.close()

data = defaultdict(lambda: [0.0]*96)
for gn, to, pw in rows:
    idx = int(to) - 1
    if 0 <= idx < 96:
        data[gn][idx] = float(pw or 0)

thermal = {n: v for n, v in data.items() if '#' in n}
storage = {n: v for n, v in data.items() if '储能' in n}
other = {n: v for n, v in data.items() if '#' not in n and '储能' not in n}
print(f'Thermal: {len(thermal)}, Storage: {len(storage)}, Other: {len(other)}')

def classify(vals, name=''):
    arr = [v for v in vals if v is not None]
    if len(arr) < 80: return '数据不足', 0
    mean_v = sum(arr)/len(arr)
    if mean_v == 0: return '零出力', 0
    std_v = math.sqrt(sum((x-mean_v)**2 for x in arr)/len(arr))
    cv = (std_v/abs(mean_v))*100 if mean_v != 0 else 0
    peak = max(arr); trough = min(arr)
    def avg(seg): return sum(seg)/len(seg) if seg else 0
    has_neg = min(arr) < 0; has_pos = max(arr) > 0
    if has_neg and has_pos:
        if '机' in name or '#' in name: return '一充一放型(抽蓄)', cv
        return '一充一放型', cv
    if has_neg and not has_pos: return '纯充电型', cv
    quarter = 24
    first_q = sum(arr[0:quarter])/quarter; last_q = sum(arr[96-quarter:96])/quarter
    if last_q < first_q * 0.3 and max(arr[0:quarter]) > 0: return '晚停机', cv
    if first_q < last_q * 0.3 and max(arr[96-quarter:96]) > 0: return '早启机', cv
    if trough >= peak * 0.85: return '稳定满发', cv
    midday = arr[40:56]; evening = arr[68:88]; night1 = arr[0:28]
    morning = arr[28:48]; afternoon = arr[48:68]
    if (avg(midday) < avg(night1) * 0.5) and avg(evening) > avg(night1) * 0.9: return '午低谷晚高峰', cv
    if avg(midday) < avg(night1) * 0.5: return '午低谷型', cv
    if avg(morning) > avg(night1) * 1.3 and avg(afternoon) < avg(night1) * 0.7: return '早高峰型', cv
    if cv < 15: return '平稳运行', cv
    return '波动型', cv

cat_thermal = defaultdict(list)
for n, v in thermal.items():
    cat, cv = classify(v, n)
    cat_thermal[cat].append((n, sum(v)/96, v))

cat_storage = defaultdict(list)
for n, v in storage.items():
    cat, cv = classify(v, n)
    cat_storage[cat].append((n, sum(v)/96, v))

for cat in cat_thermal: cat_thermal[cat].sort(key=lambda x: -x[1])
for cat in cat_storage: cat_storage[cat].sort(key=lambda x: -x[1])

TL = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0,15,30,45)]
COLORS = ['#0078d4','#d13438','#107c10','#f2a900','#9a60b4','#5470c6','#d83b01','#73c0de','#fc8452','#3ba272',
          '#e67e22','#8b5cf6','#00bcd4','#ff5722','#607d8b','#c51162','#aa00ff','#2962ff','#00c853','#ff6d00']

def build_table_rows(cat_units):
    rows = ''
    for cat, units in cat_units.items():
        rows += f'<tr class="cat-header"><td colspan="3">{cat}（{len(units)}台）</td></tr>'
        for i, (n, avg, vs) in enumerate(units):
            short = n.split('/')[-1] if '/' in n else n[-20:]
            rows += f'<tr><td>{i+1}</td><td class="uname" title="{n}">{short}</td><td>{avg:.0f}</td></tr>'
    return rows

# Build series
th_series = []
for cat in sorted(cat_thermal.keys()):
    for i, (n, avg, vals) in enumerate(cat_thermal[cat]):
        c = COLORS[i % len(COLORS)]
        th_series.append({'name': n.split('/')[-1] if '/' in n else n[-20:], 'data': [round(v,1) for v in vals], 'color': c})

overlay_th = []
for i, (n, vals) in enumerate(sorted(thermal.items(), key=lambda x: -sum(x[1])/96)):
    c = COLORS[i % len(COLORS)]
    overlay_th.append({'name': n.split('/')[-1] if '/' in n else n[-20:], 'data': [round(v,1) for v in vals], 'color': c})

overlay_st = []
for i, (n, vals) in enumerate(sorted(storage.items(), key=lambda x: -sum(x[1])/96)):
    c = COLORS[i % len(COLORS)]
    overlay_st.append({'name': n.split('/')[-1] if '/' in n else n[-20:], 'data': [round(v,1) for v in vals], 'color': c})

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>预调度分析 | 2026年6月1日</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}}
.header{{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600;margin-bottom:4px}}
.header .info{{font-size:11px;color:#888}}
.stats{{display:flex;gap:8px;padding:8px 24px;flex-wrap:wrap}}
.stat{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:10px 14px;min-width:120px;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.stat .l{{font-size:10px;color:#888}}
.stat .v{{font-size:18px;font-weight:600;color:#2c7be5}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:8px 24px}}
@media(max-width:1200px){{.charts{{grid-template-columns:1fr}}}}
.panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.panel .t{{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.panel .c{{width:100%;height:400px}}
.panel.full{{grid-column:1/-1}}
.panel.full .c{{height:450px}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
table th{{background:#f5f5f5;color:#333;padding:5px 8px;text-align:left;border-bottom:2px solid #e0e0e0;position:sticky;top:0}}
table td{{padding:4px 8px;border-bottom:1px solid #f0f0f0}}
.cat-header td{{background:#e8f4fd;font-weight:700;color:#0078d4;padding:6px 8px}}
</style>
</head>
<body>
<div class="header">
<h1>预调度分析 | 2026年6月1日</h1>
<div class="info">数据来源：天机库 shandong_px_provincial_prescheduling_results · 火电{len(thermal)}台 · 储能{len(storage)}台 · 其他{len(other)}台</div>
</div>
<div class="stats">
<div class="stat"><div class="l">火电机组</div><div class="v">{len(thermal)} 台</div></div>
<div class="stat"><div class="l">储能机组</div><div class="v">{len(storage)} 台</div></div>
<div class="stat"><div class="l">分类数</div><div class="v">{len(cat_thermal)} 类</div></div>
</div>
<div class="charts">
<div class="panel full"><div class="t">火电机组 — 堆叠面积图（{len(thermal)}台）</div><div class="c" id="thStacked"></div></div>
<div class="panel full"><div class="t">火电机组 — 叠加曲线（{len(thermal)}台）</div><div class="c" id="thOverlay"></div></div>
<div class="panel full"><div class="t">储能机组 — 叠加曲线（{len(storage)}台）</div><div class="c" id="stOverlay"></div></div>
<div class="panel"><div class="t">火电分类排名表</div><div class="c" style="overflow-y:auto;max-height:400px"><table><thead><tr><th>#</th><th>机组</th><th>均值(MW)</th></tr></thead><tbody>{build_table_rows(cat_thermal)}</tbody></table></div></div>
<div class="panel"><div class="t">储能分类排名表</div><div class="c" style="overflow-y:auto;max-height:400px"><table><thead><tr><th>#</th><th>机组</th><th>均值(MW)</th></tr></thead><tbody>{build_table_rows(cat_storage)}</tbody></table></div></div>
</div>
<div class="footer">润津储能 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<script>
var T={json.dumps(TL, ensure_ascii=False)};
var TS={json.dumps(th_series)};
var OT={json.dumps(overlay_th)};
var OS={json.dumps(overlay_st)};

var g={{left:55,right:20,top:20,bottom:35}};
var ec={{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var xA=Object.assign({{type:'category',data:T,axisLabel:{{interval:7}}}},ec);

var c1=echarts.init(document.getElementById('thStacked'));
c1.setOption({{grid:g,tooltip:{{trigger:'axis'}},xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:TS.map(function(s){{return {{name:s.name,type:'line',data:s.data,smooth:true,stack:'total',areaStyle:{{}},lineStyle:{{width:1,color:s.color}},itemStyle:{{color:s.color}},symbol:'none'}};}})}});

var c2=echarts.init(document.getElementById('thOverlay'));
c2.setOption({{grid:g,tooltip:{{trigger:'axis'}},xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:OT.map(function(s){{return {{name:s.name,type:'line',data:s.data,smooth:true,lineStyle:{{width:1,color:s.color,opacity:0.4}},itemStyle:{{color:s.color}},symbol:'none'}};}})}});

var c3=echarts.init(document.getElementById('stOverlay'));
c3.setOption({{grid:g,tooltip:{{trigger:'axis'}},xAxis:xA,yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:OS.map(function(s){{return {{name:s.name,type:'line',data:s.data,smooth:true,lineStyle:{{width:1,color:s.color,opacity:0.5}},itemStyle:{{color:s.color}},symbol:'none'}};}})}});

window.addEventListener('resize',function(){{c1.resize();c2.resize();c3.resize();}});
</script>
</body>
</html>'''

OUT = 'E:/DataWork/Storage_Strategy/output/预调度分析_0601.html'
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved: {OUT} ({os.path.getsize(OUT):,} bytes)')