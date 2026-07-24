"""Generate 0605 prescheduling analysis HTML for thermal + storage units."""
import json, math
from collections import defaultdict

TL = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]

with open("_tmp_prescheduling.json", encoding="utf-8") as f:
    data = json.load(f)

thermal = {n: v for n, v in data.items() if '机' in n or '#' in n}
storage = {n: v for n, v in data.items() if '储能' in n}

def classify(vals, name=""):
    """Classify a 96-point curve into a pattern type."""
    arr = [v for v in vals if v is not None]
    if len(arr) < 80:
        return "数据不足", 0
    mean_v = sum(arr) / len(arr)
    if mean_v == 0:
        return "零出力", 0
    std_v = math.sqrt(sum((x - mean_v)**2 for x in arr) / len(arr))
    cv = (std_v / abs(mean_v)) * 100 if mean_v != 0 else 0
    peak = max(arr)
    trough = min(arr)

    # Segments (0-indexed)
    night1 = arr[0:28]    # 00:00-07:00
    morning = arr[28:48]  # 07:00-12:00
    midday = arr[40:56]   # 10:00-14:00
    afternoon = arr[48:68]  # 12:00-17:00
    evening = arr[68:88]  # 17:00-22:00
    night2 = arr[88:96]   # 22:00-24:00

    def avg(seg):
        return sum(seg) / len(seg) if seg else 0

    avg_night1 = avg(night1)
    avg_morning = avg(morning)
    avg_midday = avg(midday)
    avg_afternoon = avg(afternoon)
    avg_evening = avg(evening)
    avg_night2 = avg(night2)

    # Check for negative values (charge/discharge cycle)
    has_negative = min(arr) < 0
    has_positive = max(arr) > 0

    if has_negative and has_positive:
        # 抽水蓄能: name contains '机' or '#'
        if '机' in name or '#' in name:
            return "一充一放型(抽蓄)", cv
        return "一充一放型", cv

    if has_negative and not has_positive:
        return "纯充电型", cv

    # 日内启机/停机检测（在 CV 检查之前，优先识别启停类）
    quarter = 24  # 6 hours
    first_q_avg = sum(arr[0:quarter]) / quarter
    last_q_avg = sum(arr[96-quarter:96]) / quarter

    # 日内启机：前1/4接近0，后3/4有显著出力（用3%宽松阈值以捕获过渡期短机组）
    if first_q_avg < peak * 0.03 and peak > 0:
        rest_avg = sum(arr[quarter:96]) / (96 - quarter)
        if rest_avg > peak * 0.03:
            return "日内启机", cv

    # 日内停机：后1/4接近0，前3/4有显著出力
    if last_q_avg < peak * 0.03 and peak > 0:
        rest_avg = sum(arr[0:96-quarter]) / (96 - quarter)
        if rest_avg > peak * 0.03:
            return "日内停机", cv

    # CV < 5% → 平稳/直线型（合并为一个分类）
    if cv < 5:
        return "平稳/直线型", cv

    # 其余所有非零出力火电 → 午间调峰机组（早晚负荷高、中午低，统称调峰）
    return "午间调峰机组", cv

# Classify all units
thermal_classified = []
for name, vals in thermal.items():
    pattern, cv = classify(vals, name)
    peak = max(vals)
    mean_v = sum(vals) / len(vals)
    trough = min(vals)
    thermal_classified.append({
        "name": name, "vals": vals, "pattern": pattern, "cv": cv,
        "peak": peak, "mean": mean_v, "trough": trough
    })

storage_classified = []
for name, vals in storage.items():
    pattern, cv = classify(vals, name)
    peak = max(vals)
    mean_v = sum(vals) / len(vals)
    trough = min(vals)
    # Charge/discharge stats: 15min = 0.25h
    charge_powers = [abs(v) for v in vals if v < 0]
    discharge_powers = [v for v in vals if v > 0]
    charge_avg = sum(charge_powers) / len(charge_powers) if charge_powers else 0
    discharge_avg = sum(discharge_powers) / len(discharge_powers) if discharge_powers else 0
    charge_energy = sum(abs(v) * 0.25 for v in vals if v < 0)
    discharge_energy = sum(v * 0.25 for v in vals if v > 0)
    efficiency = (discharge_energy / charge_energy * 100) if charge_energy > 0 else 0
    storage_classified.append({
        "name": name, "vals": vals, "pattern": pattern, "cv": cv,
        "peak": peak, "mean": mean_v, "trough": trough,
        "charge_avg": charge_avg, "discharge_avg": discharge_avg,
        "charge_energy": charge_energy, "discharge_energy": discharge_energy,
        "efficiency": efficiency
    })

thermal_classified.sort(key=lambda x: x["peak"], reverse=True)
storage_classified.sort(key=lambda x: x["discharge_energy"], reverse=True)

# Pattern stats
def pattern_stats(items):
    stats = defaultdict(list)
    for it in items:
        stats[it["pattern"]].append(it)
    return dict(sorted(stats.items(), key=lambda x: len(x[1]), reverse=True))

t_pat = pattern_stats(thermal_classified)
s_pat = pattern_stats(storage_classified)

# ===== Generate HTML =====
def js_arr(vals):
    """Convert values list to JS array string, limit decimals."""
    return "[" + ",".join(f"{v:.2f}" for v in vals) + "]"

def js_str(s):
    return json.dumps(s, ensure_ascii=False)

def gen_chart_div(cid, title, height=420):
    h4 = f"<h4>{title}</h4>" if title else ""
    return f'<div class="box"><h4>{title}</h4><div id="{cid}" class="chart" style="height:{height}px"></div></div>'

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>山东省级预调度分析 - 火电&储能 (2026-06-05)</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#fff;color:#333;padding:20px}}
h1{{text-align:center;font-size:20px;color:#222;margin-bottom:4px}}
.subtitle{{text-align:center;font-size:12px;color:#888;margin-bottom:16px;line-height:1.6}}
.sec{{font-size:15px;color:#222;margin:24px 0 10px;padding:8px 12px;background:#f0f4ff;border-left:3px solid #2c7be5}}
.stats{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}}
.card{{flex:1;min-width:130px;background:#fafafa;border-radius:6px;padding:14px;text-align:center;border:1px solid #e8e8e8}}
.card .v{{font-size:24px;font-weight:bold;color:#2c7be5}}
.card .l{{font-size:11px;color:#888;margin-top:4px}}
.grid{{display:flex;gap:12px;flex-wrap:wrap}}
.box{{flex:1 1 48%;min-width:500px;background:#fff;border-radius:8px;padding:8px;border:1px solid #e0e0e0;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.box h4{{font-size:12px;color:#666;text-align:center;margin-bottom:4px;font-weight:400}}
.chart{{width:100%;height:420px}}
table{{width:100%;border-collapse:collapse;font-size:11px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
th,td{{border:1px solid #e0e0e0;padding:6px 10px;text-align:right}}
th{{background:#f5f5f5;color:#333;font-weight:600;white-space:nowrap}}
td:first-child{{text-align:left}}
td.pat{{text-align:center;font-weight:bold;color:#2c7be5}}
tr:hover{{background:#fafafa}}
.notes{{font-size:11px;color:#666;line-height:1.7;margin-top:20px;padding:12px 16px;background:#fafafa;border-radius:6px;border:1px solid #e0e0e0}}
.notes b{{color:#333}}
</style>
</head>
<body>
<h1>山东省级预调度分析 — 火电 & 储能 (2026-06-05)</h1>
<p class="subtitle">数据源: shandong_px_provincial_prescheduling_results | 火电机组(含"机"/"#"): {len(thermal_classified)} 台 | 储能机组(含"储能"): {len(storage_classified)} 台</p>

<div class="stats">
<div class="card"><div class="v">{len(thermal_classified)}</div><div class="l">火电机组数</div></div>
<div class="card"><div class="v">{len(storage_classified)}</div><div class="l">储能机组数</div></div>
<div class="card"><div class="v">{thermal_classified[0]['peak']:.0f}</div><div class="l">火电最大峰值(MW)</div></div>
<div class="card"><div class="v">{sum(s["charge_energy"] for s in storage_classified):.0f}</div><div class="l">储能总充电量(MWh)</div></div>
<div class="card"><div class="v">{sum(s["discharge_energy"] for s in storage_classified):.0f}</div><div class="l">储能总放电量(MWh)</div></div>
<div class="card"><div class="v">{len(s_pat)}</div><div class="l">储能调度模式数</div></div>
</div>
'''

# ===== STORAGE CHARGE/DISCHARGE TABLE =====
html += f'<div class="sec">储能充放统计 — 全部机组 (共{len(storage_classified)}台)</div>\n'
html += '<div style="overflow-x:auto"><table>\n'
html += '<thead><tr><th>排名</th><th>机组名称</th><th>充电功率均值(MW)</th><th>充电电量(MWh)</th><th>放电功率均值(MW)</th><th>放电电量(MWh)</th><th>充放效率</th><th>调度模式</th></tr></thead><tbody>\n'
for i, s in enumerate(storage_classified):
    name_short = s["name"].replace("山东.", "")
    html += f'<tr><td>{i+1}</td><td>{name_short}</td><td>{s["charge_avg"]:.1f}</td><td>{s["charge_energy"]:.1f}</td><td>{s["discharge_avg"]:.1f}</td><td>{s["discharge_energy"]:.1f}</td><td>{s["efficiency"]:.1f}%</td><td class="pat">{s["pattern"]}</td></tr>\n'
html += '</tbody></table></div>\n'

# ===== PIE CHARTS =====
html += '<div class="sec">调度模式分布</div>\n<div class="grid">\n'

# Thermal pattern pie
t_pie_data = [{"name": k, "value": len(v)} for k, v in t_pat.items()]
html += f'<div class="box"><h4>火电调度模式分布 ({len(thermal_classified)}台)</h4><div id="c-tpie" class="chart"></div></div>\n'
# Storage pattern pie
s_pie_data = [{"name": k, "value": len(v)} for k, v in s_pat.items()]
html += f'<div class="box"><h4>储能调度模式分布 ({len(storage_classified)}台)</h4><div id="c-spie" class="chart"></div></div>\n'
html += '</div>\n'

# ===== TOP 50 BAR =====
html += '<div class="sec">火电 TOP 50 峰值出力 & 储能充放电量对比</div>\n<div class="grid">\n'
# Thermal top50 bar
t_top50_names = [t["name"].replace("山东.", "") for t in thermal_classified[:50]]
t_top50_peaks = [t["peak"] for t in thermal_classified[:50]]
t_top50_means = [t["mean"] for t in thermal_classified[:50]]
html += f'<div class="box"><h4>火电 TOP 50 峰值 vs 均值</h4><div id="c-tbar" class="chart" style="height:900px"></div></div>\n'

s_all_names = [s["name"].replace("山东.", "") for s in storage_classified]
s_all_charge_energy = [s["charge_energy"] for s in storage_classified]
s_all_discharge_energy = [s["discharge_energy"] for s in storage_classified]
html += f'<div class="box"><h4>储能全部 充放电量对比 (MWh)</h4><div id="c-sbar" class="chart" style="height:{max(500, len(storage_classified)*18)}px"></div></div>\n'
html += '</div>\n'

# ===== THERMAL PATTERN CURVES =====
html += '<div class="sec">火电 — 按调度模式分组 96点出力曲线</div>\n'
for pat, items in t_pat.items():
    cid = f"c-tpat-{abs(hash(pat))}"
    show_n = min(15, len(items))
    html += f'<div class="box"><h4>{pat} ({len(items)}台, 显示前{show_n}台)</h4><div id="{cid}" class="chart"></div></div>\n'

# ===== STORAGE PATTERN CURVES =====
html += '<div class="sec">储能 — 按调度模式分组 96点出力曲线</div>\n'
for pat, items in s_pat.items():
    cid = f"c-spat-{abs(hash(pat))}"
    show_n = len(items)
    html += f'<div class="box"><h4>{pat} ({len(items)}台, 全部显示)</h4><div id="{cid}" class="chart"></div></div>\n'

# ===== TOP 10 THERMAL CURVES OVERLAY =====
html += '<div class="sec">火电 TOP 10 & 储能全部 96点曲线叠加</div>\n<div class="grid">\n'
html += f'<div class="box"><h4>火电 TOP 10 出力曲线</h4><div id="c-ttop10" class="chart"></div></div>\n'
html += f'<div class="box"><h4>储能全部 出力曲线</h4><div id="c-stop30" class="chart"></div></div>\n'
html += '</div>\n'

html += '''
<div class="notes">
<b>表:</b> shandong_px_provincial_prescheduling_results — 山东省级日前预调度结果<br>
<b>字段:</b> date / generator_name / time_order(1-96) / declaration_power(MW)<br>
<b>日期:</b> 2026-06-05 | <b>火电:</b> ''' + str(len(thermal_classified)) + '''台(含"机"/"#") | <b>储能:</b> ''' + str(len(storage_classified)) + '''台(含"储能")<br>
<b>调度模式分类说明:</b><br>
  &bull; <b>全天直线型</b>: 恒定出力，CV=0% &bull; <b>基本平稳</b>: CV &lt; 5%<br>
  &bull; <b>早晚高峰型</b>: 早晨+晚间双峰，午间低谷 &bull; <b>夜间出力高</b>: 晚间/夜间出力最高<br>
  &bull; <b>早高峰型</b>: 7-12点出力最高 &bull; <b>中午启动型</b>: 午间启动，夜间低出力<br>
  &bull; <b>午间低谷型</b>: 午间(10-14点)明显低谷 &bull; <b>爬坡型</b>: 日间持续增长<br>
  &bull; <b>降坡型</b>: 日间持续减少 &bull; <b>一充一放型</b>: 储能充放电循环(含"机"/"#"为抽蓄)<br>
  &bull; <b>纯充电型</b>: 储能仅充电不放电<br>
</div>
'''

# ===== JAVASCRIPT =====
html += '''
<script>
var TL = ["00:00","00:15","00:30","00:45","01:00","01:15","01:30","01:45","02:00","02:15","02:30","02:45","03:00","03:15","03:30","03:45","04:00","04:15","04:30","04:45","05:00","05:15","05:30","05:45","06:00","06:15","06:30","06:45","07:00","07:15","07:30","07:45","08:00","08:15","08:30","08:45","09:00","09:15","09:30","09:45","10:00","10:15","10:30","10:45","11:00","11:15","11:30","11:45","12:00","12:15","12:30","12:45","13:00","13:15","13:30","13:45","14:00","14:15","14:30","14:45","15:00","15:15","15:30","15:45","16:00","16:15","16:30","16:45","17:00","17:15","17:30","17:45","18:00","18:15","18:30","18:45","19:00","19:15","19:30","19:45","20:00","20:15","20:30","20:45","21:00","21:15","21:30","21:45","22:00","22:15","22:30","22:45","23:00","23:15","23:30","23:45"];
function baseOpt() {
    return {
        tooltip: {
            trigger:"axis",
            textStyle:{fontSize:11},
            position: function(point, params, dom, rect, size) {
                // Position below the mouse cursor
                var x = point[0];
                var y = point[1];
                var w = size.contentSize[0];
                var h = size.contentSize[1];
                var vw = size.viewSize[0];
                var vh = size.viewSize[1];
                // Default: right of cursor, below cursor
                var posX = x + 15;
                var posY = y + 15;
                // Keep within viewport
                if (posX + w > vw) posX = x - w - 15;
                if (posY + h > vh) posY = y - h - 15;
                return [posX, posY];
            },
            extraCssText: 'max-height:400px;overflow-y:auto;'
        },
        grid: {left:70, right:30, top:16, bottom:40},
        xAxis: {type:"category", data:TL, axisLabel:{color:"#666", fontSize:9, interval:7}, axisLine:{lineStyle:{color:"#ccc"}}},
        yAxis: {type:"value", name:"MW", axisLabel:{color:"#666", fontSize:10}, splitLine:{lineStyle:{color:"#eee"}}}
    };
}

// Pattern Pies
'''
# Thermal pie
html += f'''
(function(){{
    var c = echarts.init(document.getElementById("c-tpie"));
    c.setOption({{
        tooltip: {{trigger:"item"}},
        legend: {{orient:"vertical", right:10, top:10, textStyle:{{fontSize:10}}, type:"scroll", height:300}},
        series: [{{type:"pie", radius:["35%","65%"], center:["35%","50%"], label:{{fontSize:9}}, data:{json.dumps(t_pie_data, ensure_ascii=False)}}}]
    }});
}})();
'''
# Storage pie
html += f'''
(function(){{
    var c = echarts.init(document.getElementById("c-spie"));
    c.setOption({{
        tooltip: {{trigger:"item"}},
        legend: {{orient:"vertical", right:10, top:10, textStyle:{{fontSize:10}}, type:"scroll", height:300}},
        series: [{{type:"pie", radius:["35%","65%"], center:["35%","50%"], label:{{fontSize:9}}, data:{json.dumps(s_pie_data, ensure_ascii=False)}}}]
    }});
}})();
'''

# Thermal TOP 20 bar
html += f'''
(function(){{
    var c = echarts.init(document.getElementById("c-tbar"));
    c.setOption({{
        tooltip: {{trigger:"axis", axisPointer:{{type:"shadow"}}}},
        grid: {{left:140, right:40, top:10, bottom:30}},
        xAxis: {{type:"value", axisLabel:{{color:"#666", fontSize:10}}, splitLine:{{lineStyle:{{color:"#eee"}}}}}},
        yAxis: {{type:"category", data:{json.dumps(t_top50_names, ensure_ascii=False)}.reverse(), axisLabel:{{color:"#666", fontSize:9}}, inverse:true}},
        series: [
            {{name:"峰值", type:"bar", data:{json.dumps(t_top50_peaks)}.reverse(), itemStyle:{{color:"#2c7be5"}}, barMaxWidth:16}},
            {{name:"均值", type:"bar", data:{json.dumps(t_top50_means)}.reverse(), itemStyle:{{color:"#a0c4f0"}}, barMaxWidth:16}}
        ],
        legend: {{data:["峰值","均值"], bottom:0}}
    }});
}})();
'''

# Storage charge/discharge bar
html += f'''
(function(){{
    var c = echarts.init(document.getElementById("c-sbar"));
    c.setOption({{
        tooltip: {{trigger:"axis", axisPointer:{{type:"shadow"}}}},
        grid: {{left:140, right:40, top:10, bottom:30}},
        xAxis: {{type:"value", name:"MWh", axisLabel:{{color:"#666", fontSize:10}}, splitLine:{{lineStyle:{{color:"#eee"}}}}}},
        yAxis: {{type:"category", data:{json.dumps(s_all_names, ensure_ascii=False)}.reverse(), axisLabel:{{color:"#666", fontSize:9}}, inverse:true}},
        series: [
            {{name:"充电电量", type:"bar", data:{json.dumps(s_all_charge_energy)}.reverse(), itemStyle:{{color:"#43a047"}}, barMaxWidth:16}},
            {{name:"放电电量", type:"bar", data:{json.dumps(s_all_discharge_energy)}.reverse(), itemStyle:{{color:"#e5731c"}}, barMaxWidth:16}}
        ],
        legend: {{data:["充电电量","放电电量"], bottom:0}}
    }});
}})();
'''

# Thermal pattern curves (each group)
for pat, items in t_pat.items():
    cid = f"c-tpat-{abs(hash(pat))}"
    show_n = min(15, len(items))
    series = []
    COLORS = ["#2c7be5","#e5731c","#43a047","#e53935","#8e24aa","#00acc1","#ff6f00","#5c6bc0",
              "#26a69a","#d81b60","#7cb342","#039be5","#c0ca33","#f4511e","#3949ab"]
    for j, it in enumerate(items[:show_n]):
        name_short = it["name"].replace("山东.", "")
        series.append({
            "name": name_short, "type": "line", "data": it["vals"],
            "lineStyle": {"width": 1.2}, "symbol": "none",
            "color": COLORS[j % len(COLORS)]
        })
    html += f'''
(function(){{
    var c = echarts.init(document.getElementById("{cid}"));
    var opt = baseOpt();
    opt.series = {json.dumps(series, ensure_ascii=False)};
    opt.legend = {{show:true, bottom:0, textStyle:{{fontSize:9}}, type:"scroll", height:40}};
    opt.yAxis.name = "MW";
    c.setOption(opt);
}})();
'''

# Storage pattern curves (each group)
for pat, items in s_pat.items():
    cid = f"c-spat-{abs(hash(pat))}"
    show_n = len(items)
    series = []
    COLORS = ["#e5731c","#2c7be5","#43a047","#e53935","#8e24aa","#00acc1","#ff6f00","#5c6bc0",
              "#26a69a","#d81b60","#7cb342","#039be5","#c0ca33","#f4511e","#3949ab",
              "#546e7a","#8d6e63","#ab47bc","#ef5350","#66bb6a","#ffa726","#42a5f5","#ec407a",
              "#9ccc65","#ff7043","#5c6bc0","#26c6da","#d4e157","#78909c","#f06292",
              "#4db6ac","#ba68c8","#fbc02d","#607d8b","#795548","#e91e63","#2196f3","#4caf50",
              "#ff9800","#9c27b0","#009688","#f44336","#3f51b5","#cddc39","#00bcd4","#ff5722",
              "#673ab7","#8bc34a","#03a9f4","#ffc107","#e040fb","#69f0ae","#448aff","#ff6e40",
              "#b388ff","#64ffda","#82b1ff","#ffd740","#ea80fc","#b9f6ca","#8c9eff","#ffab40"]
    for j, it in enumerate(items[:show_n]):
        name_short = it["name"].replace("山东.", "")
        series.append({
            "name": name_short, "type": "line", "data": it["vals"],
            "lineStyle": {"width": 1.2}, "symbol": "none",
            "color": COLORS[j % len(COLORS)]
        })
    html += f'''
(function(){{
    var c = echarts.init(document.getElementById("{cid}"));
    var opt = baseOpt();
    opt.series = {json.dumps(series, ensure_ascii=False)};
    opt.legend = {{show:true, bottom:0, textStyle:{{fontSize:9}}, type:"scroll", height:40}};
    opt.yAxis.name = "MW";
    c.setOption(opt);
}})();
'''

# Thermal TOP 10 overlay
t_top10 = thermal_classified[:10]
t10_series = []
for j, it in enumerate(t_top10):
    name_short = it["name"].replace("山东.", "")
    t10_series.append({
        "name": name_short, "type": "line", "data": it["vals"],
        "lineStyle": {"width": 1.5}, "symbol": "none"
    })
html += f'''
(function(){{
    var c = echarts.init(document.getElementById("c-ttop10"));
    var opt = baseOpt();
    opt.series = {json.dumps(t10_series, ensure_ascii=False)};
    opt.legend = {{show:true, bottom:0, textStyle:{{fontSize:9}}, type:"scroll", height:36}};
    opt.yAxis.name = "MW";
    c.setOption(opt);
}})();
'''

# Storage all overlay
s_all = storage_classified[:]
s_all_series = []
for j, it in enumerate(s_all):
    name_short = it["name"].replace("山东.", "")
    s_all_series.append({
        "name": name_short, "type": "line", "data": it["vals"],
        "lineStyle": {"width": 1.5}, "symbol": "none"
    })
html += f'''
(function(){{
    var c = echarts.init(document.getElementById("c-stop30"));
    var opt = baseOpt();
    opt.series = {json.dumps(s_all_series, ensure_ascii=False)};
    opt.legend = {{show:true, bottom:0, textStyle:{{fontSize:9}}, type:"scroll", height:36}};
    opt.yAxis.name = "MW";
    c.setOption(opt);
}})();
'''

html += '\n</script>\n</body>\n</html>'

out_path = "06 DataMining/output/省级预调度分析_火电储能_2026-06-05.html"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Saved: {out_path}")
print(f"Thermal: {len(thermal_classified)} units, {len(t_pat)} patterns")
print(f"Storage: {len(storage_classified)} units, {len(s_pat)} patterns")
for pat, items in t_pat.items():
    print(f"  Thermal [{pat}]: {len(items)} units")
for pat, items in s_pat.items():
    print(f"  Storage [{pat}]: {len(items)} units")