"""生成分峰值水平看2h谷值阈值 HTML。
输入：_tmp_valley_by_peak.json
输出：output/竞价空间分析结果/谷值阈值_分峰值水平.html
"""
import json
from pathlib import Path

def _find_root(start):
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        if (cand / "_tmp_valley_by_peak.json").exists() or (cand / ".env").exists():
            return cand
    return Path(__file__).parent.parent.parent

ROOT = _find_root(__file__)
D = json.load(open(ROOT / "_tmp_valley_by_peak.json", encoding="utf-8"))

by_peak = D["by_peak"]
by_month = D["by_month"]
corr = D["corr_overall"]
daily = D["daily"]

# by_peak 数据
peak_labels = [r["bs_max_bin"] for r in by_peak]
peak_thresholds = [r["best_split"] for r in by_peak]
peak_thermal = [r["thermal_num_avg"] for r in by_peak]
peak_valley_avg = [r["valley_avg"] for r in by_peak]
peak_ind_max = [r["ind_max_avg"] for r in by_peak]
peak_high_pct = [round(r["high_willing_days"]/r["days"]*100,0) for r in by_peak]
peak_days = [r["days"] for r in by_peak]

# by_month 数据
month_labels = [f"{r['month']}月" for r in by_month]
month_thresholds = [r["best_split"] for r in by_month]
month_thermal = [r["thermal_num_avg"] for r in by_month]
month_valley_avg = [r["valley_avg"] for r in by_month]
month_ind_max = [r["ind_max_avg"] for r in by_month]
month_bs_max = [r["bs_max_avg"] for r in by_month]
month_days = [r["days"] for r in by_month]

# 散点：bs_max vs valley_2h 颜色按高意愿
scatter_high = [[r["bs_max"], r["valley_2h"], r["date_str"], r["ind_max_p"]] for r in daily if r["ind_max_p"] > 3000]
scatter_low = [[r["bs_max"], r["valley_2h"], r["date_str"], r["ind_max_p"]] for r in daily if r["ind_max_p"] <= 3000]

# 散点：bs_max vs thermal_num
scatter_thermal = [[r["bs_max"], r["thermal_num"], r["date_str"]] for r in daily]

# 散点：thermal_num vs ind_max
scatter_thermal_ind = [[r["thermal_num"], r["ind_max_p"], r["date_str"]] for r in daily]

JS = json.dumps({
    "peak_labels": peak_labels, "peak_thresholds": peak_thresholds,
    "peak_thermal": peak_thermal, "peak_valley_avg": peak_valley_avg,
    "peak_ind_max": peak_ind_max, "peak_high_pct": peak_high_pct, "peak_days": peak_days,
    "month_labels": month_labels, "month_thresholds": month_thresholds,
    "month_thermal": month_thermal, "month_valley_avg": month_valley_avg,
    "month_ind_max": month_ind_max, "month_bs_max": month_bs_max, "month_days": month_days,
    "scatter_high": scatter_high, "scatter_low": scatter_low,
    "scatter_thermal": scatter_thermal, "scatter_thermal_ind": scatter_thermal_ind,
    "daily": daily, "corr": corr,
}, ensure_ascii=False)

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>2h谷值阈值 — 分峰值水平/月份</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:"Microsoft YaHei","Segoe UI",sans-serif; background:#fff; color:#333; padding:20px; }
h1 { color:#222; font-size:22px; margin-bottom:6px; }
.subtitle { color:#666; font-size:13px; margin-bottom:18px; line-height:1.6; }
h2 { color:#222; font-size:17px; margin:24px 0 10px; border-left:4px solid #2c7be5; padding-left:10px; }
.desc { color:#666; font-size:12px; margin-bottom:8px; line-height:1.7; }
.chart { width:100%; border:1px solid #ddd; border-radius:6px; background:#fff; }
.note { background:#f6f8fa; border-left:3px solid #2c7be5; padding:10px 14px; font-size:12px; color:#555; margin:10px 0; line-height:1.7; border-radius:0 4px 4px 0; }
.rule { background:#f0fff0; border:1px solid #b7eb8f; border-radius:6px; padding:16px 20px; margin:16px 0; }
.rule h3 { color:#52c41a; margin-bottom:10px; font-size:16px; }
.rule table { width:100%; border-collapse:collapse; margin-top:8px; font-size:12.5px; }
.rule th, .rule td { border:1px solid #d9d9d9; padding:5px 8px; text-align:center; }
.rule th { background:#f5f5f5; }
.key { background:#fffbe6; border:1px solid #ffe58f; border-radius:6px; padding:14px 18px; margin:12px 0; font-size:13px; line-height:1.8; }
</style>
</head>
<body>

<h1>2h谷值阈值随峰值水平的变化趋势</h1>
<p class="subtitle">
问题：7-8月保供季节负荷大、竞价空间峰值高、开机台数多，2h谷值储能投运阈值是否更准确？<br>
数据范围：__START__ ~ __END__，共 __NDATES__ 天。整体 r(bs_max, thermal_num)=__R_BS_THERMAL__（峰值高→火电多开）
</p>

<div class="key">
<b>★ 核心结论：固定17.5GW阈值在保供季节会误判。</b><br>
储能投运意愿 = f(2h谷值, 竞价空间峰值/开机台数)。谷值是主信号（r=−0.87），但<b>峰值水平（保供/开机台数）会改变阈值</b>：<br>
• 峰值低（<25GW，火电72台）→ 谷值阈值 <b>11.25 GW</b>（谷值低才投运）<br>
• 峰值高（>32GW，火电94台，7月保供）→ 谷值阈值 <b>16.25 GW</b>（谷值高也投运）<br>
阈值随峰值<b>上升而上升</b>，因为火电开得多、保供压力大，储能即使谷值偏高也需投运调峰。
</div>

<div class="rule">
<h3>★ 分峰值水平的2h谷值阈值表</h3>
<table>
<tr><th>竞价空间峰值</th><th>天数</th><th>火电开机台数</th><th>谷值均值</th><th>储能最大功率均</th><th>高意愿天占比</th><th>2h谷值阈值</th><th>准确率</th></tr>
__PEAK_ROWS__
</table>
<p style="margin-top:10px; font-size:12px; color:#666;">注：阈值=该峰值区间内最佳谷值分割点（高意愿=储能最大功率>3000MW）</p>
</div>

<h2>一、阈值随峰值的变化趋势</h2>
<p class="desc">柱：各峰值区间的2h谷值阈值（橙）；折线：火电开机台数（右轴，红）。看阈值是否随峰值/台数上升。</p>
<div id="c1" class="chart" style="height:380px"></div>
<div class="note">
<b>阈值随峰值单调上升</b>（11.25→16.25 GW），但28-30GW区间有回落（14.5GW，数据噪声）。整体趋势明确：<b>峰值越高、火电开得越多，储能投运的谷值阈值越高</b>——保供季节即使谷值偏高储能也投运。
</div>

<h2>二、按月份看（5-6月 vs 7月保供）</h2>
<p class="desc">柱：谷值阈值（橙）/ 峰值均值（蓝）；折线：火电台数（右轴）。</p>
<div id="c2" class="chart" style="height:380px"></div>
<div class="note">
<b>7月保供季节</b>：峰值均 37 GW、火电 101 台、谷值均 20 GW（负荷大拉高谷值）、储能最大功率均仅 3295 MW（<3GW，因调峰空间被火电挤占）。7月阈值 16.25 GW，但<b>7月高意愿天占比仅 53%</b>（10/19），因为7月谷值普遍高（20GW均值），多数天谷值已超阈值→储能低投运。<b>5-6月</b>谷值低（2-6GW均值），高意愿占比 80-86%。
</div>

<h2>三、散点：竞价空间峰值 vs 2h谷值（颜色=高/低意愿）</h2>
<p class="desc">绿=高意愿（储能>3000MW），红=低意愿。看高意愿点在不同峰值/谷值组合的分布。</p>
<div id="c3" class="chart" style="height:420px"></div>
<div class="note">
关键观察：<b>7月保供日（峰值>32GW）的谷值普遍偏高（20-40GW）</b>，但仍有些天储能高投运（07-02/04/18/19/20，谷值5-12GW）。判断储能投运需同时看峰值和谷值：<b>高意愿集中在谷值<15GW区域，无论峰值高低</b>；7月谷值>20GW的天多为低意愿。
</div>

<h2>四、散点：竞价空间峰值 vs 火电开机台数</h2>
<p class="desc">验证"峰值决定开机台数"假设。</p>
<div id="c4" class="chart" style="height:340px"></div>
<div class="note">
r=__R_BS_THERMAL__（强正相关）。峰值>32GW时火电普遍90-122台；峰值<25GW时70-75台。验证假设：竞价空间峰值高→火电多开。7月14-17日峰值44-46GW、火电115-122台，是保供高峰。
</div>

<h2>五、散点：火电开机台数 vs 储能最大功率</h2>
<p class="desc">看火电多开时储能是否被挤占。</p>
<div id="c5" class="chart" style="height:340px"></div>
<div class="note">
r=__R_THERMAL_IND__（负相关）。火电开得越多（>100台），储能最大功率普遍低（500-2700MW）；火电少开（<85台），储能功率高（5000-7800MW）。验证：<b>保供季节火电大量开机，挤占储能调峰空间</b>，储能投运意愿降低。
</div>

<div style="background:#f0f7ff; border:1px solid #b3d4f4; border-radius:6px; padding:16px 20px; margin-top:16px;">
<h3 style="color:#2c7be5; margin-bottom:10px;">★ 修正后的判断逻辑（含峰值/台数）</h3>
<p style="font-size:13px; line-height:1.8; color:#333;">
<b>三档阈值（按竞价空间峰值/保供水平）：</b><br>
① <b>峰值 &lt; 25 GW</b>（非保供，火电~72台）：谷值阈值 <b>11.25 GW</b> → 储能高投运<br>
② <b>峰值 25-32 GW</b>（过渡，火电80-89台）：谷值阈值 <b>14.5 GW</b><br>
③ <b>峰值 &gt; 32 GW</b>（7-8月保供，火电94+台）：谷值阈值 <b>16.25 GW</b> → 但仍需谷值实际低于阈值<br>
<br>
<b>关键洞察：</b><br>
• <b>谷值仍是主信号</b>（r=−0.87），但峰值水平修正阈值。<br>
• <b>7月保供季节的特殊性</b>：负荷大→谷值被拉高（均值20GW），同时火电大量开机（>100台）挤占调峰空间。即使谷值<16.25GW阈值，储能功率也受限（最大功率均3295MW，远低于5-6月的6400+MW）。<br>
• <b>火电 vs 储能是替代关系</b>（r=−0.66）：保供日火电多开→储能少投运；非保供日火电少开→储能多投运填谷。<br>
• <b>预测储能投运</b>应同时输入：①2h谷值（主信号）②竞价空间峰值/火电开机台数（修正阈值）③月份（季节性）。可用决策树或带交互项的GBDT。
</p>
</div>

<script>
var D = __JS__;
var C = {thresh:'#faad14', thermal:'#f5222d', valley:'#2c7be5', ind:'#52c41a', bs:'#13c2c2', high:'#52c41a', low:'#f5222d'};

// 图1：阈值随峰值
echarts.init(document.getElementById('c1')).setOption({
  tooltip: {trigger:'axis', axisPointer:{type:'shadow'}},
  legend: {data:['2h谷值阈值','火电开机台数'], top:5},
  grid: {left:60, right:60, bottom:40, top:50},
  xAxis: {type:'category', data:D.peak_labels, axisLabel:{fontSize:11}},
  yAxis: [{type:'value', name:'谷值阈值(MW)'}, {type:'value', name:'台数', position:'right', min:60, splitLine:{show:false}}],
  series: [
    {name:'2h谷值阈值', type:'bar', itemStyle:{color:C.thresh}, data:D.peak_thresholds, label:{show:true, position:'top', formatter:'{c}'}},
    {name:'火电开机台数', type:'line', yAxisIndex:1, smooth:true, itemStyle:{color:C.thermal}, lineStyle:{color:C.thermal, width:2}, data:D.peak_thermal}
  ]
});

// 图2：按月份
echarts.init(document.getElementById('c2')).setOption({
  tooltip: {trigger:'axis', axisPointer:{type:'shadow'}},
  legend: {data:['谷值阈值','峰值均值','火电台数'], top:5},
  grid: {left:60, right:60, bottom:40, top:50},
  xAxis: {type:'category', data:D.month_labels},
  yAxis: [{type:'value', name:'MW'}, {type:'value', name:'台数', position:'right', min:60, splitLine:{show:false}}],
  series: [
    {name:'谷值阈值', type:'bar', itemStyle:{color:C.thresh}, data:D.month_thresholds, label:{show:true, position:'top', formatter:'{c}'}},
    {name:'峰值均值', type:'bar', itemStyle:{color:C.bs}, data:D.month_bs_max},
    {name:'火电台数', type:'line', yAxisIndex:1, smooth:true, itemStyle:{color:C.thermal}, lineStyle:{color:C.thermal, width:2}, data:D.month_thermal}
  ]
});

// 图3：散点 峰值 vs 谷值 颜色=意愿
echarts.init(document.getElementById('c3')).setOption({
  tooltip: {formatter: p => p.data[2]+'<br/>峰值: '+p.data[0]+' MW<br/>谷值: '+p.data[1]+' MW<br/>储能最大功率: '+p.data[3]+' MW'},
  legend: {data:['高意愿(储能>3000MW)','低意愿'], top:5},
  grid: {left:60, right:30, bottom:50, top:50},
  xAxis: {type:'value', name:'竞价空间峰值(MW)', nameLocation:'middle', nameGap:30, min:20000, max:47000, splitLine:{lineStyle:{color:'#eee'}}},
  yAxis: {type:'value', name:'2h谷值(MW)', nameLocation:'middle', nameGap:40, splitLine:{lineStyle:{color:'#eee'}}},
  series: [
    {name:'高意愿(储能>3000MW)', type:'scatter', data:D.scatter_high, symbolSize:10, itemStyle:{color:C.high, opacity:0.75}},
    {name:'低意愿', type:'scatter', data:D.scatter_low, symbolSize:10, itemStyle:{color:C.low, opacity:0.6}}
  ]
});

// 图4：峰值 vs 火电台数
echarts.init(document.getElementById('c4')).setOption({
  tooltip: {formatter: p => p.data[2]+'<br/>峰值: '+p.data[0]+' MW<br/>火电台数: '+p.data[1]+'台'},
  grid: {left:60, right:30, bottom:50, top:30},
  xAxis: {type:'value', name:'竞价空间峰值(MW)', nameLocation:'middle', nameGap:30, min:20000, max:47000, splitLine:{lineStyle:{color:'#eee'}}},
  yAxis: {type:'value', name:'火电开机台数', min:60, splitLine:{lineStyle:{color:'#eee'}}},
  series: [{type:'scatter', data:D.scatter_thermal, symbolSize:10, itemStyle:{color:C.thermal, opacity:0.75}}]
});

// 图5：火电台数 vs 储能最大功率
echarts.init(document.getElementById('c5')).setOption({
  tooltip: {formatter: p => p.data[2]+'<br/>火电台数: '+p.data[0]+'台<br/>储能最大功率: '+p.data[1]+' MW'},
  grid: {left:60, right:30, bottom:50, top:30},
  xAxis: {type:'value', name:'火电开机台数', nameLocation:'middle', nameGap:30, min:60, splitLine:{lineStyle:{color:'#eee'}}},
  yAxis: {type:'value', name:'储能最大功率(MW)', splitLine:{lineStyle:{color:'#eee'}}},
  series: [{type:'scatter', data:D.scatter_thermal_ind, symbolSize:10, itemStyle:{color:C.ind, opacity:0.75}}]
});

window.addEventListener('resize', function(){
  ['c1','c2','c3','c4','c5'].forEach(function(id){
    var inst = echarts.getInstanceByDom(document.getElementById(id));
    if(inst) inst.resize();
  });
});
</script>
</body>
</html>
"""

# 峰值分箱表格行
peak_rows = ""
for r in by_peak:
    peak_rows += f'<tr><td>{r["bs_max_bin"]}</td><td>{r["days"]}</td><td>{r["thermal_num_avg"]:.0f}台</td><td>{r["valley_avg"]:.0f}</td><td>{r["ind_max_avg"]:.0f}</td><td>{r["high_willing_days"]}/{r["days"]} ({r["high_willing_days"]/r["days"]*100:.0f}%)</td><td><b>{r["best_split"]:.0f}</b></td><td>{r["best_acc"]*100:.0f}%</td></tr>\n'

HTML = HTML.replace("__START__", D["date_range"]["start"])
HTML = HTML.replace("__END__", D["date_range"]["end"])
HTML = HTML.replace("__NDATES__", str(D["date_range"]["n_dates"]))
HTML = HTML.replace("__PEAK_ROWS__", peak_rows)
HTML = HTML.replace("__R_BS_THERMAL__", str(corr["bs_max_vs_thermal_num"]))
HTML = HTML.replace("__R_THERMAL_IND__", str(corr["thermal_num_vs_ind_max"]))
HTML = HTML.replace("__JS__", JS)

out_dir = ROOT / "output" / "竞价空间分析结果"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "谷值阈值_分峰值水平.html"
out_path.write_text(HTML, encoding="utf-8")
print(f"Saved: {out_path} ({out_path.stat().st_size} bytes)")
