"""生成 2h谷值 vs 储能投运意愿 HTML。
输入：_tmp_valley_willingness.json
输出：output/竞价空间分析结果/2h谷值_储能投运意愿.html
"""
import json
from pathlib import Path

def _find_root(start):
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        if (cand / "_tmp_valley_willingness.json").exists() or (cand / ".env").exists():
            return cand
    return Path(__file__).parent.parent.parent

ROOT = _find_root(__file__)
D = json.load(open(ROOT / "_tmp_valley_willingness.json", encoding="utf-8"))

daily = D["daily"]
binned = D["binned"]
corr = D["corr"]

dates = [d["date_str"] for d in daily]
valley = [round(d["valley_2h"],0) for d in daily]
pv_max = [round(d["pv_max"],0) for d in daily]
ind_max = [round(d["ind_max_p"],0) for d in daily]
ind_avg = [round(d["ind_avg_p"],0) for d in daily]
draw_max = [round(d["draw_max_p"],0) for d in daily]
ind_num = [d["ind_num"] for d in daily]

# 散点：2h谷值 vs 储能最大功率
scatter_valley_ind = [[round(d["valley_2h"],0), round(d["ind_max_p"],0), d["date_str"]] for d in daily]
scatter_valley_avg = [[round(d["valley_2h"],0), round(d["ind_avg_p"],0), d["date_str"]] for d in daily]
scatter_valley_draw = [[round(d["valley_2h"],0), round(d["draw_max_p"],0), d["date_str"]] for d in daily]
# 散点：2h谷值 vs 光伏最大（验证谷值与光伏的对应关系）
scatter_valley_pv = [[round(d["valley_2h"],0), round(d["pv_max"],0), d["date_str"]] for d in daily]

# 分箱
bin_labels = [r["valley_bin"] for r in binned]
bin_ind_max = [round(r["ind_max_avg"],0) for r in binned]
bin_ind_avg = [round(r["ind_avg_avg"],0) for r in binned]
bin_draw_max = [round(r["draw_max_avg"],0) for r in binned]
bin_ind_num = [round(r["ind_num_avg"],0) for r in binned]
bin_days = [r["days"] for r in binned]

best_split = D["best_split"]
best_acc = D["best_split_acc"]

JS = json.dumps({
    "dates": dates, "valley": valley, "pv_max": pv_max, "ind_max": ind_max,
    "ind_avg": ind_avg, "draw_max": draw_max, "ind_num": ind_num,
    "scatter_valley_ind": scatter_valley_ind, "scatter_valley_avg": scatter_valley_avg,
    "scatter_valley_draw": scatter_valley_draw, "scatter_valley_pv": scatter_valley_pv,
    "bin_labels": bin_labels, "bin_ind_max": bin_ind_max, "bin_ind_avg": bin_ind_avg,
    "bin_draw_max": bin_draw_max, "bin_ind_num": bin_ind_num, "bin_days": bin_days,
    "corr": corr, "best_split": best_split, "best_acc": best_acc,
}, ensure_ascii=False)

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>2h谷值 vs 储能投运意愿</title>
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
.compare { background:#fffbe6; border:1px solid #ffe58f; border-radius:6px; padding:14px 18px; margin:12px 0; font-size:13px; line-height:1.8; }
</style>
</head>
<body>

<h1>竞价空间2h谷值 vs 储能投运意愿</h1>
<p class="subtitle">
2h谷值 = 竞价空间曲线连续8个点(2小时)的最低均值窗口的MW值（来自相似日特征 valley）<br>
谷值越低（甚至为负）→ 光伏淹没负荷越深 → 储能填谷需求越强<br>
数据范围：__START__ ~ __END__，共 __NDATES__ 天
</p>

<div class="compare">
<b>★ 与光伏最大值阈值对比：</b>2h谷值是比光伏最大值更直接的信号。<br>
光伏最大值 vs 储能最大功率 r=+0.79（正相关，只看光伏多少）<br>
2h谷值 vs 储能最大功率 r=<b>__R_VALLEY_IND_MAX__</b>（<b>负相关，更强</b>），谷值越低储能投运越强<br>
2h谷值与光伏最大值本身 r=__R_VALLEY_PV__（强负相关，谷值由光伏决定）
</div>

<div class="rule">
<h3>★ 快速判断规律（2h谷值阈值）</h3>
<table>
<tr><th>2h谷值</th><th>储能投运意愿</th><th>独立储能最大功率</th><th>独立储能平均功率</th><th>抽蓄最大功率</th><th>储能台数</th></tr>
<tr class="high"><td>&lt; 0（负值）</td><td>极高</td><td>~7690 MW</td><td>~1261 MW</td><td>~2825 MW</td><td>~64</td></tr>
<tr class="high"><td>0-5 GW</td><td>高</td><td>~7434 MW</td><td>~1246 MW</td><td>~3191 MW</td><td>~63</td></tr>
<tr class="high"><td>5-10 GW</td><td>高</td><td>~6728 MW</td><td>~1278 MW</td><td>~2867 MW</td><td>~64</td></tr>
<tr><td>10-15 GW</td><td>中高</td><td>~5319 MW</td><td>~1002 MW</td><td>~2942 MW</td><td>~62</td></tr>
<tr><td>15-20 GW</td><td>中</td><td>~3218 MW</td><td>~551 MW</td><td>~1570 MW</td><td>~59</td></tr>
<tr class="low"><td>&gt; 20 GW</td><td>低</td><td>~2088 MW</td><td>~337 MW</td><td>~1064 MW</td><td>~55</td></tr>
</table>
<p style="margin-top:10px; font-size:13px; line-height:1.8;">
<b>关键阈值：2h谷值 &lt; 17.5 GW</b> 时储能投运意愿显著（独立储能最大功率 >3000 MW）。准确率 <b>__ACC__%</b>。<br>
谷值为负（光伏淹没负荷）时储能投运最强；谷值 >20 GW 时储能基本半运行。
</p>
</div>

<h2>一、散点：2h谷值 vs 独立储能最大功率</h2>
<p class="desc">每点=1天。X=2h谷值(MW)，Y=独立储能最大功率(MW)。红色虚线为17.5GW阈值。负相关——谷值越低储能越强。</p>
<div id="c1" class="chart" style="height:380px"></div>
<div class="note">
r=<b>__R_VALLEY_IND_MAX__</b>（强负相关）。谷值<0时储能最大功率普遍7000+ MW；谷值>20GW时降至2000 MW。比光伏最大值（r=0.79）解释力更强。<br>
逻辑：2h谷值直接刻画"光伏淹没负荷的深度"——谷值越负，午间过剩新能源越多，储能必须大规模充电填谷。
</div>

<h2>二、散点：2h谷值 vs 储能平均功率</h2>
<p class="desc">平均功率反映储能的持续工作强度。</p>
<div id="c2" class="chart" style="height:340px"></div>
<div class="note">
r=<b>__R_VALLEY_IND_AVG__</b>。谷值越低储能平均功率越高（~1260 MW），谷值高时仅 ~340 MW。
</div>

<h2>三、散点：2h谷值 vs 光伏最大值（验证谷值来源）</h2>
<p class="desc">验证2h谷值是否主要由光伏决定。</p>
<div id="c3" class="chart" style="height:340px"></div>
<div class="note">
r=<b>__R_VALLEY_PV__</b>（强负相关）。光伏越大→谷值越低（负）。2h谷值本质是光伏+负荷+风电的综合结果，但主要由光伏决定。2h谷值相比光伏最大值的优势：它<b>已经综合了负荷和风电</b>，是竞价空间的直接特征，而非单一光伏。
</div>

<h2>四、分箱统计：不同谷值区间的投运指标</h2>
<p class="desc">柱：独立储能最大功率（绿）/ 抽蓄最大功率（橙）；折线：储能台数（右轴）。</p>
<div id="c4" class="chart" style="height:380px"></div>
<div class="note">
<b>单调下降</b>规律：谷值从负→20GW，储能最大功率从7690→2088 MW，平滑递减。抽蓄最大功率也从2825→1064 MW。台数变化小（55-64台），仍是功率强度调节。
</div>

<h2>五、每日明细：2h谷值 vs 储能/光伏最大功率</h2>
<p class="desc">柱：2h谷值（蓝，负值向下）/ 光伏最大（黄）/ 储能最大（绿）。</p>
<div id="c5" class="chart" style="height:380px"></div>
<div class="note">
观察：谷值为负的日子（05-01~05-05、6月多数工作日）储能最强；谷值>20GW的日子（07-12~17负荷高、光伏相对低）储能最弱。节假日（05-19）谷值高但储能仍弱。
</div>

<div style="background:#f0f7ff; border:1px solid #b3d4f4; border-radius:6px; padding:16px 20px; margin-top:16px;">
<h3 style="color:#2c7be5; margin-bottom:10px;">★ 应用结论（2h谷值优于光伏最大值）</h3>
<p style="font-size:13px; line-height:1.8; color:#333;">
<b>一句话规律：</b>竞价空间2h谷值 &lt; <b>17.5 GW</b>（尤其 &lt; 10 GW 或为负）→ 次日储能大规模投运。<br>
<b>判断逻辑：</b>
① 谷值 &lt; 0（光伏淹没负荷）→ 极高意愿，储能最大功率预期 6700-7700 MW；<br>
② 谷值 0-10 GW → 高意愿，储能最大功率预期 6700-7400 MW；<br>
③ 谷值 10-15 GW → 中高意愿，~5300 MW；<br>
④ 谷值 15-17.5 GW → 中等意愿，~3200 MW；<br>
⑤ 谷值 &gt; 17.5 GW → 低意愿，~2000 MW。<br>
<b>对比光伏最大值法：</b>2h谷值准确率 __ACC__%（vs 光伏18GW法 93.8%），略优；且谷值是<b>竞价空间直接特征</b>（综合了光伏+负荷+风电），比单一光伏更贴近调度本质。<br>
<b>实施：</b>次日上午天机库发布日前预测后，计算竞价空间96点→找2h最低均值窗口→对照阈值判断。可复用 similar_day_analysis.py 的特征提取逻辑。
</p>
</div>

<script>
var D = __JS__;
var C = {valley:'#2c7be5', pv:'#faad14', ind:'#52c41a', draw:'#ff7875', num:'#9b6bd9'};

// 图1：散点 谷值 vs 储能最大
function scatter(domId, data, xName, yName, color, splitVal, splitLabel) {
  var opt = {
    tooltip: {formatter: p => p.data[2]+'<br/>'+xName+': '+p.data[0]+' MW<br/>'+yName+': '+p.data[1]+' MW'},
    grid: {left:60, right:30, bottom:50, top:30},
    xAxis: {type:'value', name:xName, nameLocation:'middle', nameGap:30, splitLine:{lineStyle:{color:'#eee'}}},
    yAxis: {type:'value', name:yName, splitLine:{lineStyle:{color:'#eee'}}},
    series: [{type:'scatter', data:data, symbolSize:10, itemStyle:{color:color, opacity:0.75}}]
  };
  if (splitVal !== undefined) {
    opt.series.push({type:'line', showSymbol:false, markLine:{symbol:'none', data:[{xAxis:splitVal}], lineStyle:{color:'#f5222d', type:'dashed', width:2}, label:{formatter:splitLabel, color:'#f5222d'}}});
  }
  echarts.init(document.getElementById(domId)).setOption(opt);
}
scatter('c1', D.scatter_valley_ind, '2h谷值(MW)', '独立储能最大功率(MW)', C.ind, 17500, '17.5GW');
scatter('c2', D.scatter_valley_avg, '2h谷值(MW)', '独立储能平均功率(MW)', C.ind, 17500, '17.5GW');
scatter('c3', D.scatter_valley_pv, '2h谷值(MW)', '光伏最大值(MW)', C.pv);

// 图4：分箱
echarts.init(document.getElementById('c4')).setOption({
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

// 图5：每日
echarts.init(document.getElementById('c5')).setOption({
  tooltip: {trigger:'axis', axisPointer:{type:'shadow'}},
  legend: {data:['2h谷值','光伏最大','储能最大'], top:5},
  grid: {left:60, right:30, bottom:60, top:50},
  xAxis: {type:'category', data:D.dates, axisLabel:{rotate:45, fontSize:10}},
  yAxis: {type:'value', name:'MW'},
  dataZoom: [{type:'inside'}, {type:'slider', height:18, bottom:5}],
  series: [
    {name:'2h谷值', type:'bar', itemStyle:{color:C.valley}, data:D.valley},
    {name:'光伏最大', type:'bar', itemStyle:{color:C.pv}, data:D.pv_max},
    {name:'储能最大', type:'bar', itemStyle:{color:C.ind}, data:D.ind_max}
  ]
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

HTML = HTML.replace("__START__", D["date_range"]["start"])
HTML = HTML.replace("__END__", D["date_range"]["end"])
HTML = HTML.replace("__NDATES__", str(D["date_range"]["n_dates"]))
HTML = HTML.replace("__R_VALLEY_IND_MAX__", str(corr["valley_vs_ind_max"]))
HTML = HTML.replace("__R_VALLEY_IND_AVG__", str(corr["valley_vs_ind_avg"]))
HTML = HTML.replace("__R_VALLEY_PV__", str(corr["valley_vs_pv_max"]))
HTML = HTML.replace("__ACC__", str(round(best_acc*100,1)))
HTML = HTML.replace("__JS__", JS)

out_dir = ROOT / "output" / "竞价空间分析结果"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "2h谷值_储能投运意愿.html"
out_path.write_text(HTML, encoding="utf-8")
print(f"Saved: {out_path} ({out_path.stat().st_size} bytes)")
