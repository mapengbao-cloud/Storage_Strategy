"""生成光伏阈值→储能投运意愿 HTML（简洁版，用于快速判断）。
输入：_tmp_pv_storage_willingness.json
输出：output/竞价空间分析结果/光伏阈值_储能投运意愿.html
"""
import json
from pathlib import Path

def _find_root(start):
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        if (cand / "_tmp_pv_storage_willingness.json").exists() or (cand / ".env").exists():
            return cand
    return Path(__file__).parent.parent.parent

ROOT = _find_root(__file__)
D = json.load(open(ROOT / "_tmp_pv_storage_willingness.json", encoding="utf-8"))

daily = D["daily"]
binned = D["binned"]
corr = D["corr"]

# 数据准备
dates = [d["date"] for d in daily]
pv_max = [round(d["pv_max"], 0) for d in daily]
ind_max = [round(d["ind_max_p"], 0) for d in daily]
ind_avg = [round(d["ind_avg_p"], 0) for d in daily]
draw_max = [round(d["draw_max_p"], 0) for d in daily]
draw_avg = [round(d["draw_avg_p"], 0) for d in daily]
ind_num = [d["ind_num"] for d in daily]
draw_num = [d["draw_num"] for d in daily]

# 散点：光伏最大 vs 储能最大功率
scatter_ind = [[round(d["pv_max"],0), round(d["ind_max_p"],0), d["date"]] for d in daily]
scatter_avg = [[round(d["pv_max"],0), round(d["ind_avg_p"],0), d["date"]] for d in daily]
scatter_draw = [[round(d["pv_max"],0), round(d["draw_max_p"],0), d["date"]] for d in daily]

# 分箱数据
bin_labels = [r["pv_bin"] for r in binned]
bin_days = [r["days"] for r in binned]
bin_ind_max = [round(r["ind_max_avg"],0) for r in binned]
bin_ind_avg = [round(r["ind_avg_avg"],0) for r in binned]
bin_draw_max = [round(r["draw_max_avg"],0) for r in binned]
bin_draw_avg = [round(r["draw_avg_avg"],0) for r in binned]
bin_ind_num = [round(r["ind_num_avg"],0) for r in binned]
bin_draw_num = [round(r["draw_num_avg"],0) for r in binned]

best_split = D["best_split"]
best_acc = D["best_split_acc"]

JS = json.dumps({
    "dates": dates, "pv_max": pv_max, "ind_max": ind_max, "ind_avg": ind_avg,
    "draw_max": draw_max, "draw_avg": draw_avg, "ind_num": ind_num, "draw_num": draw_num,
    "scatter_ind": scatter_ind, "scatter_avg": scatter_avg, "scatter_draw": scatter_draw,
    "bin_labels": bin_labels, "bin_days": bin_days, "bin_ind_max": bin_ind_max,
    "bin_ind_avg": bin_ind_avg, "bin_draw_max": bin_draw_max, "bin_draw_avg": bin_draw_avg,
    "bin_ind_num": bin_ind_num, "bin_draw_num": bin_draw_num,
    "corr": corr, "best_split": best_split, "best_acc": best_acc,
}, ensure_ascii=False)

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>光伏阈值 → 储能投运意愿规律</title>
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
.rule table { width:100%; border-collapse:collapse; margin-top:8px; font-size:13px; }
.rule th, .rule td { border:1px solid #d9d9d9; padding:6px 10px; text-align:center; }
.rule th { background:#f5f5f5; }
.rule .high { background:#f6ffed; color:#52c41a; font-weight:600; }
.rule .low { background:#fff1f0; color:#f5222d; }
</style>
</head>
<body>

<h1>光伏预测最大值 → 储能+抽蓄投运意愿规律</h1>
<p class="subtitle">
输入：日前预测光伏功率最大值（MW，天机库 shandong_px_spot_dayahead_load_info，10:15 发布）<br>
输出：次日独立储能+抽蓄的最大功率/平均功率、投运台数<br>
数据范围：__START__ ~ __END__，共 __NDATES__ 天
</p>

<div class="rule">
<h3>★ 快速判断规律（光伏最大值阈值）</h3>
<table>
<tr><th>光伏预测最大值</th><th>储能投运意愿</th><th>独立储能最大功率</th><th>独立储能平均功率</th><th>抽蓄最大功率</th><th>储能台数</th></tr>
<tr class="low"><td>&lt; 15 GW</td><td>低</td><td>1000-3700 MW</td><td>200-600 MW</td><td>0-1800 MW</td><td>39-66</td></tr>
<tr><td>15-18 GW</td><td>中</td><td>~2000 MW</td><td>~340 MW</td><td>~820 MW</td><td>~54</td></tr>
<tr class="high"><td>&ge; 18 GW</td><td>高（跃升）</td><td>5000-7500 MW</td><td>950-1270 MW</td><td>2250-3200 MW</td><td>60-66</td></tr>
</table>
<p style="margin-top:10px; font-size:13px; line-height:1.8;">
<b>关键阈值：光伏预测最大值 &ge; 18 GW</b> 时，储能投运意愿显著跃升（独立储能最大功率从 ~2000 MW 跳到 5000+ MW）。<br>
该阈值作为"高意愿"判断的准确率 <b>__ACC__%</b>。光伏 < 15 GW 时储能基本半运行或低强度运行。
</p>
</div>

<h2>一、散点：光伏最大值 vs 储能最大功率</h2>
<p class="desc">每点=1天。X=日前光伏预测最大值(MW)，Y=独立储能最大功率(MW)。红色虚线为 18GW 阈值。</p>
<div id="c1" class="chart" style="height:380px"></div>
<div class="note">
相关性：光伏最大值 vs 独立储能最大功率 r=<b>__R_IND_MAX__</b>（强正相关）；vs 独立储能平均功率 r=<b>__R_IND_AVG__</b>。<br>
18GW 是明显的<b>跃升点</b>：左侧（光伏低）储能最大功率多在 1000-3700 MW，右侧（光伏高）多在 5000-7500 MW。
</div>

<h2>二、散点：光伏最大值 vs 抽蓄最大功率</h2>
<p class="desc">抽蓄与光伏的相关性弱于独立储能，但 18GW 以上抽蓄功率也明显升高。</p>
<div id="c2" class="chart" style="height:340px"></div>
<div class="note">
光伏最大值 vs 抽蓄最大功率 r=<b>__R_DRAW_MAX__</b>（中等正相关）。抽蓄台数变化小（3-14台），但功率随光伏增大而升高。光伏>20GW 时抽蓄最大功率普遍 3000-4000 MW。
</div>

<h2>三、分箱统计：不同光伏区间下的投运指标</h2>
<p class="desc">柱：独立储能最大功率（绿）/ 抽蓄最大功率（橙）；折线：独立储能台数（右轴）。</p>
<div id="c3" class="chart" style="height:380px"></div>
<div class="note">
规律：光伏 < 15 GW 时储能最大功率 1600-2100 MW；光伏 15-18 GW 约 2000 MW；<b>光伏 &ge; 18 GW 跃升至 5300-7500 MW</b>。抽蓄在光伏 &ge; 18 GW 时也从 ~800 MW 升至 2900-3200 MW。台数变化不大（储能 50-66台、抽蓄 3-14台），说明投运意愿主要通过<b>功率强度</b>调节而非开停机台数。
</div>

<h2>四、每日明细：光伏最大值 vs 储能/抽蓄功率</h2>
<p class="desc">柱：光伏最大值（黄）/ 储能最大功率（绿）/ 抽蓄最大功率（橙）。</p>
<div id="c4" class="chart" style="height:380px"></div>
<div class="note">
注意异常日：05-18 光伏仅 3.3 GW 但储能最大功率 6233 MW（节假日后特殊调度）；05-19/05-20 节假日光伏 7-8 GW 但储能几乎不投运（负荷低无需调峰）。说明光伏阈值是主信号，但<b>节假日负荷</b>也是重要修正因子。
</div>

<div style="background:#f0f7ff; border:1px solid #b3d4f4; border-radius:6px; padding:16px 20px; margin-top:16px;">
<h3 style="color:#2c7be5; margin-bottom:10px;">★ 应用结论</h3>
<p style="font-size:13px; line-height:1.8; color:#333;">
<b>一句话规律：</b>日前光伏预测最大值 &ge; <b>18 GW</b> → 次日储能+抽蓄大规模投运（独立储能最大功率 5000-7500 MW、平均 950-1270 MW；抽蓄最大功率 2250-3200 MW）。<br>
<b>判断逻辑：</b>
① 光伏最大值 &ge; 18 GW → 高意愿，储能最大功率预期 6000±1500 MW；<br>
② 光伏最大值 15-18 GW → 中等意愿，储能最大功率预期 ~2000 MW；<br>
③ 光伏最大值 &lt; 15 GW → 低意愿（需结合节假日判断：节假日负荷低则几乎不投运）。<br>
<b>修正因子：</b>节假日（负荷低）即使光伏正常也投运意愿低；非节假日光伏低时储能仍可能小幅投运（调频/备用）。<br>
<b>台数特征：</b>储能台数 39-66 台、抽蓄 3-14 台，变化不大，主要通过功率强度调节意愿。
</p>
</div>

<script>
var D = __JS__;
var C = {pv:'#faad14', ind:'#52c41a', draw:'#ff7875', num:'#2c7be5'};

// 图1：散点 储能最大功率
(function(){
  var data = D.scatter_ind;
  var xmin=0, xmax=26000;
  echarts.init(document.getElementById('c1')).setOption({
    tooltip: {formatter: p => p.data[2]+'<br/>光伏最大: '+p.data[0]+' MW<br/>储能最大功率: '+p.data[1]+' MW'},
    grid: {left:60, right:30, bottom:50, top:30},
    xAxis: {type:'value', name:'光伏预测最大值(MW)', nameLocation:'middle', nameGap:30, min:0, max:26000, splitLine:{lineStyle:{color:'#eee'}}},
    yAxis: {type:'value', name:'独立储能最大功率(MW)', splitLine:{lineStyle:{color:'#eee'}}},
    series: [
      {type:'scatter', data:data, symbolSize:10, itemStyle:{color:C.ind, opacity:0.75}},
      {type:'line', showSymbol:false, markLine:{symbol:'none', data:[{xAxis:18000}], lineStyle:{color:'#f5222d', type:'dashed', width:2}, label:{formatter:'18GW阈值', color:'#f5222d'}}}
    ]
  });
})();

// 图2：散点 抽蓄最大功率
(function(){
  var data = D.scatter_draw;
  echarts.init(document.getElementById('c2')).setOption({
    tooltip: {formatter: p => p.data[2]+'<br/>光伏最大: '+p.data[0]+' MW<br/>抽蓄最大功率: '+p.data[1]+' MW'},
    grid: {left:60, right:30, bottom:50, top:30},
    xAxis: {type:'value', name:'光伏预测最大值(MW)', nameLocation:'middle', nameGap:30, min:0, max:26000, splitLine:{lineStyle:{color:'#eee'}}},
    yAxis: {type:'value', name:'抽蓄最大功率(MW)', splitLine:{lineStyle:{color:'#eee'}}},
    series: [
      {type:'scatter', data:data, symbolSize:10, itemStyle:{color:C.draw, opacity:0.75}},
      {type:'line', showSymbol:false, markLine:{symbol:'none', data:[{xAxis:18000}], lineStyle:{color:'#f5222d', type:'dashed', width:2}, label:{formatter:'18GW', color:'#f5222d'}}}
    ]
  });
})();

// 图3：分箱柱状
echarts.init(document.getElementById('c3')).setOption({
  tooltip: {trigger:'axis', axisPointer:{type:'shadow'}},
  legend: {data:['独立储能最大功率','抽蓄最大功率','储能台数'], top:5},
  grid: {left:60, right:60, bottom:40, top:50},
  xAxis: {type:'category', data:D.bin_labels, axisLabel:{fontSize:11}},
  yAxis: [{type:'value', name:'MW'}, {type:'value', name:'台数', position:'right', splitLine:{show:false}}],
  series: [
    {name:'独立储能最大功率', type:'bar', itemStyle:{color:C.ind}, data:D.bin_ind_max},
    {name:'抽蓄最大功率', type:'bar', itemStyle:{color:C.draw}, data:D.bin_draw_max},
    {name:'储能台数', type:'line', yAxisIndex:1, itemStyle:{color:C.num}, lineStyle:{color:C.num, width:2}, data:D.bin_ind_num}
  ]
});

// 图4：每日明细
echarts.init(document.getElementById('c4')).setOption({
  tooltip: {trigger:'axis', axisPointer:{type:'shadow'}},
  legend: {data:['光伏最大','储能最大','抽蓄最大'], top:5},
  grid: {left:60, right:30, bottom:60, top:50},
  xAxis: {type:'category', data:D.dates, axisLabel:{rotate:45, fontSize:10}},
  yAxis: {type:'value', name:'MW'},
  dataZoom: [{type:'inside'}, {type:'slider', height:18, bottom:5}],
  series: [
    {name:'光伏最大', type:'bar', itemStyle:{color:C.pv}, data:D.pv_max},
    {name:'储能最大', type:'bar', itemStyle:{color:C.ind}, data:D.ind_max},
    {name:'抽蓄最大', type:'bar', itemStyle:{color:C.draw}, data:D.draw_max}
  ]
});

window.addEventListener('resize', function(){
  ['c1','c2','c3','c4'].forEach(function(id){
    var inst = echarts.getInstanceByDom(document.getElementById(id));
    if(inst) inst.resize();
  });
});
</script>
</body>
</html>
"""

HTML = HTML.replace("__START__", D["date_range"]["start"])
HTML = HTML.replace("__END__", D["date_range"]["end"])
HTML = HTML.replace("__NDATES__", str(D["date_range"]["n_dates"]))
HTML = HTML.replace("__ACC__", str(round(best_acc*100,1)))
HTML = HTML.replace("__R_IND_MAX__", str(corr["pv_max_vs_ind_max"]))
HTML = HTML.replace("__R_IND_AVG__", str(corr["pv_max_vs_ind_avg"]))
HTML = HTML.replace("__R_DRAW_MAX__", str(corr["pv_max_vs_draw_max"]))
HTML = HTML.replace("__JS__", JS)

out_dir = ROOT / "output" / "竞价空间分析结果"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "光伏阈值_储能投运意愿.html"
out_path.write_text(HTML, encoding="utf-8")
print(f"Saved: {out_path} ({out_path.stat().st_size} bytes)")
