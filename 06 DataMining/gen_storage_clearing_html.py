"""生成储能+抽蓄+虚拟电厂出清分析 HTML（自包含，ECharts CDN）。

输入：_tmp_storage_clearing.json
输出：output/竞价空间分析结果/储能出清功率分析.html
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = json.load(open(ROOT / "_tmp_storage_clearing.json", encoding="utf-8"))

daily = DATA["daily"]
corr = DATA["corr"]
corr_cols = DATA["corr_cols"]
hourly = DATA["hourly"]
time_labels = DATA["time_labels"]

# ---------- 数据准备 ----------
dates = [d["date"] for d in daily]
discharge_mwh = [round(d["discharge_mwh"], 1) for d in daily]
charge_mwh = [round(d["charge_mwh"], 1) for d in daily]
net_mwh = [round(d["net_mwh"], 1) for d in daily]
bs_mean = [round(d["bs_mean"], 0) for d in daily]
wind_pv_sum = [round(d["wind_pv_sum"] * 0.25, 0) for d in daily]  # 平均功率

# 96点平均
h_storage = [round(h["storage_total"], 1) for h in hourly]
h_indep = [round(h["independent"], 1) for h in hourly]
h_draw = [round(h["draw"], 1) for h in hourly]
h_virt = [round(h["virtual"], 1) for h in hourly]
h_bs = [round(h["bidding_space"], 0) for h in hourly]
h_wind = [round(h["wind"], 0) for h in hourly]
h_pv = [round(h["pv"], 0) for h in hourly]

# 散点数据：每日储能日均功率 vs 各变量
scatter_bs = []
scatter_pv = []
scatter_wind = []
for d in daily:
    avg_store_p = round(d["storage_net_sum"] / 96, 1)  # 日均功率 MW
    scatter_bs.append([round(d["bs_mean"], 0), avg_store_p, d["date"]])
    scatter_pv.append([round(d["pv_sum"] / 96, 0), avg_store_p, d["date"]])
    scatter_wind.append([round(d["wind_sum"] / 96, 0), avg_store_p, d["date"]])

# 相关性热力图数据
corr_labels = ["储能总功率", "竞价空间", "风电", "光伏", "风光合计", "直调负荷", "独立储能", "抽蓄", "虚拟电厂"]
corr_data = []
n = len(corr_cols)
for i in range(n):
    for j in range(n):
        ci = corr_cols[i]
        cj = corr_cols[j]
        corr_data.append([j, i, round(corr[ci][cj], 4)])

# 代表日曲线（选6个有代表性的）
sample_dates_all = DATA["sample_dates"]
pick_idx = [0, len(sample_dates_all)//4, len(sample_dates_all)//2, len(sample_dates_all)*3//4, len(sample_dates_all)-2, len(sample_dates_all)-1]
pick_dates = []
seen = set()
for i in pick_idx:
    if 0 <= i < len(sample_dates_all):
        d = sample_dates_all[i]
        if d not in seen:
            seen.add(d); pick_dates.append(d)
pick_dates = pick_dates[:6]

# 颜色
COLORS = {
    "storage": "#2c7be5", "indep": "#36b37e", "draw": "#ff7875", "virt": "#9b6bd9",
    "bs": "#f5a623", "wind": "#13c2c2", "pv": "#faad14",
    "discharge": "#52c41a", "charge": "#f5222d", "net": "#2c7be5",
}

# JS 数据块
JS_DATA = json.dumps({
    "dates": dates, "discharge": discharge_mwh, "charge": charge_mwh, "net": net_mwh, "bsmean": bs_mean,
    "timeLabels": time_labels, "hStorage": h_storage, "hIndep": h_indep, "hDraw": h_draw,
    "hVirt": h_virt, "hBS": h_bs, "hWind": h_wind, "hPv": h_pv,
    "scatterBS": scatter_bs, "scatterPV": scatter_pv, "scatterWind": scatter_wind,
    "corrData": corr_data, "corrLabels": corr_labels, "pickDates": pick_dates,
    "curves": DATA["curves"], "C": COLORS,
}, ensure_ascii=False)

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>山东储能+抽蓄+虚拟电厂出清功率分析</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:"Microsoft YaHei","Segoe UI",sans-serif; background:#fff; color:#333; padding:20px; }
h1 { color:#222; font-size:22px; margin-bottom:6px; }
.subtitle { color:#666; font-size:13px; margin-bottom:18px; line-height:1.6; }
h2 { color:#222; font-size:17px; margin:24px 0 10px; border-left:4px solid #2c7be5; padding-left:10px; }
.desc { color:#666; font-size:12px; margin-bottom:8px; line-height:1.7; }
.card-row { display:flex; flex-wrap:wrap; gap:12px; margin-bottom:8px; }
.card { background:#fafafa; border:1px solid #e0e0e0; border-radius:6px; padding:14px 18px; min-width:170px; flex:1; }
.card .v { font-size:24px; font-weight:600; color:#2c7be5; }
.card .l { font-size:12px; color:#666; margin-top:4px; }
.card .s { font-size:11px; color:#999; margin-top:2px; }
.chart { width:100%; border:1px solid #ddd; border-radius:6px; background:#fff; }
.note { background:#f6f8fa; border-left:3px solid #2c7be5; padding:10px 14px; font-size:12px; color:#555; margin:10px 0; line-height:1.7; border-radius:0 4px 4px 0; }
.recommend { background:#f0f7ff; border:1px solid #b3d4f4; border-radius:6px; padding:16px 20px; margin-top:10px; }
.recommend h3 { color:#2c7be5; margin-bottom:8px; font-size:15px; }
.recommend p, .recommend li { font-size:13px; color:#333; line-height:1.8; }
.recommend ul { margin:6px 0 6px 22px; }
.recommend code { background:#eef; padding:1px 5px; border-radius:3px; font-size:12px; color:#c7254e; }
.tag { display:inline-block; background:#2c7be5; color:#fff; font-size:11px; padding:2px 8px; border-radius:10px; margin-right:6px; }
</style>
</head>
<body>

<h1>山东储能+抽蓄+虚拟电厂日出清功率分析</h1>
<p class="subtitle">
数据源：shandong_px_dayahead_clearing_quantity_number（电量×4→功率MW） + shandong_px_spot_dayahead_load_info（日前预测）<br>
范围：__START__ ~ __END__，共 __NDATES__ 天，96 点/天<br>
竞价空间 = 直调负荷 − (联络线受电 + 风电 + 光伏 + 核电 + 自备机组)
</p>

<div class="card-row">
  <div class="card"><div class="v">__R_BS__</div><div class="l">储能总功率 ↔ 竞价空间</div><div class="s">96点级 Pearson 相关</div></div>
  <div class="card"><div class="v" style="color:#f5222d">__R_PV__</div><div class="l">储能总功率 ↔ 光伏</div><div class="s">负相关：光伏大发→充电</div></div>
  <div class="card"><div class="v" style="color:#13c2c2">__R_WIND__</div><div class="l">储能总功率 ↔ 风电</div><div class="s">弱正相关</div></div>
  <div class="card"><div class="v">__R_LOAD__</div><div class="l">储能总功率 ↔ 直调负荷</div><div class="s">负荷高→放电</div></div>
  <div class="card"><div class="v" style="color:#36b37e">__R_INDEP__</div><div class="l">总量 ↔ 独立储能</div><div class="s">主导项（贡献最大）</div></div>
  <div class="card"><div class="v" style="color:#ff7875">__R_DRAW__</div><div class="l">总量 ↔ 抽蓄</div><div class="s">第二贡献项</div></div>
</div>

<h2>一、每日储能能量与竞价空间</h2>
<p class="desc">柱状：放电能量（正）/ 充电能量（取绝对值，负向），单位 MWh；折线：竞价空间日均功率（MW，右轴）。净出清为正表示当日净放电。</p>
<div id="c1" class="chart" style="height:420px"></div>
<div class="note">规律：5–6 月典型工作日放电 30–35 GWh、充电 39–41 GWh，净充电 5–7 GWh（夜间+午间充电）；7 月中旬（07-12~17）负荷飙升、竞价空间>30 GW，储能转为净放电。节假日（如 05-19）充放电均骤降至 1 GWh 以内。</div>

<h2>二、96 点平均曲线：储能出力 vs 竞价空间 vs 新能源</h2>
<p class="desc">柱：储能总功率（正放电/负充电，左轴 MW）；折线：竞价空间、光伏、风电（右轴 MW）。各日 96 点取均值。</p>
<div id="c2" class="chart" style="height:420px"></div>
<div class="note">规律：①凌晨 00–06 竞价空间低谷（22–24 GW），储能小幅充电（独立储能+抽蓄负出力）；②11–14 光伏峰值 3.5+ GW 拉低竞价空间，储能深度充电；③18–21 晚高峰竞价空间回升，储能放电。储能总功率曲线与竞价空间呈明显同向波动。</div>

<h2>三、储能总功率 vs 竞价空间（日级散点）</h2>
<p class="desc">每点 = 1 天，X = 竞价空间日均(MW)，Y = 储能日均功率(MW，负=净充电)。悬停查看日期。</p>
<div id="c3" class="chart" style="height:380px"></div>

<h2>四、储能总功率 vs 光伏 / 风电（日级散点）</h2>
<p class="desc">左：光伏日均 vs 储能日均功率；右：风电日均 vs 储能日均功率。</p>
<div style="display:flex; gap:12px;">
  <div id="c4a" class="chart" style="height:340px; flex:1"></div>
  <div id="c4b" class="chart" style="height:340px; flex:1"></div>
</div>
<div class="note">光伏与储能日均功率呈负相关（-0.70）：光伏越大，储能净充电越深；风电相关性弱（0.17）。</div>

<h2>五、相关性热力图（96 点级）</h2>
<p class="desc">基于 7680 条 96 点记录的 Pearson 相关系数。深蓝=强正相关，深红=强负相关。</p>
<div id="c5" class="chart" style="height:460px"></div>

<h2>六、代表日 96 点曲线（储能功率 + 竞价空间）</h2>
<p class="desc">实线左轴：储能总功率(MW)；虚线右轴：竞价空间(MW)。可点击图例切换。</p>
<div id="c6" class="chart" style="height:440px"></div>

<div class="recommend">
<h3>★ 预测方法推荐</h3>
<p><span class="tag">推荐</span><b>分时段梯度提升树（GBDT/LightGBM）回归，日前多元特征</b>，以日前 10:15 即发布的预测量为输入，逐 96 点预测储能总功率。</p>

<p><b>1. 输入特征（日前可得，无需预测）</b></p>
<ul>
<li><code>bs_t</code>：竞价空间 96 点序列（直调−联络−风−光−核−地方−自备），最强信号，相关 0.69</li>
<li><code>pv_t</code>：光伏预测 96 点（强负相关 -0.70，主导午间充电深度）</li>
<li><code>wind_t</code>：风电预测 96 点（弱相关，但影响凌晨谷段）</li>
<li><code>load_t</code>：直调负荷 96 点（相关 0.57，刻画峰谷）</li>
<li><code>weekday / holiday</code>：节假日充放电骤降（如 05-19 仅 0.7 GWh），必选特征</li>
<li><code>month / temperature</code>：季节性（7 月负荷高峰转净放电）</li>
</ul>

<p><b>2. 模型选择（由简到繁，可逐级验证）</b></p>
<ul>
<li><b>基线：分时段线性回归</b> — 对每个 96 点单独拟合 <code>storage_t = a·bs_t + b·pv_t + c·wind_t + d·load_t + e</code>。可解释、快、可直接看系数，但难捕捉非线性（如光伏>3 GW 后充电饱和）。</li>
<li><b>推荐：LightGBM / XGBoost 分时段回归</b> — 同样按 96 点分桶训练，用上述特征。能捕捉午间光伏饱和、晚高峰非线性放电，MAE 通常比线性低 20–35%。输出逐点功率 + 置信区间。</li>
<li><b>进阶：序列模型（LSTM / Transformer）</b> — 用前 N 日 96 点序列 + 当日特征预测当日 96 点。适合捕捉时序连续性，但样本量小（80 天）易过拟合，建议积累半年后再上。</li>
</ul>

<p><b>3. 分项预测</b></p>
<p>总量中独立储能贡献相关 0.93、抽蓄 0.89、虚拟电厂 0.24。可分别建模：<b>独立储能 + 抽蓄</b>用 GBDT（与竞价空间、光伏强相关），<b>虚拟电厂</b>单独用简单线性（主要与负荷线性相关 0.54，量级小）。</p>

<p><b>4. 落地建议</b></p>
<ul>
<li><b>训练集</b>：2026-05-01 ~ 2026-07-13（73 天），<b>验证集</b>：07-14 ~ 07-20（7 天）滚动验证。</li>
<li><b>关键约束</b>：储能充放电受装机容量+SOC 限制，预测值应做上下限截断（如独立储能±200 MW、抽蓄±500 MW 量级）。</li>
<li><b>特征工程重点</b>：构造 <code>pv_peak</code>（午间峰值）、<code>bs_valley_hour</code>（谷值时段）、<code>load_peak</code> 三个衍生特征，可显著提升解释力。</li>
<li><b>工程实现</b>：复用项目已有 <code>local_db.py</code> 同步机制，<code>shandong_px_spot_dayahead_load_info</code> 天机库约 10:15 更新次日预测，预测脚本可在 10:30 自动触发输出 96 点预测。</li>
</ul>

<p style="margin-top:10px; color:#888; font-size:12px;">结论：储能总功率的日前预测 <b>不需要预测电价</b>，竞价空间+新能源预测已提供 0.69/0.70 的解释力，推荐直接用日前预测量训练 GBDT 分时段回归，是当前样本量下性价比最高的方案。</p>
</div>

<script>
var D = __JS_DATA__;

// 图1：每日能量
echarts.init(document.getElementById('c1')).setOption({
  tooltip: { trigger:'axis', axisPointer:{type:'shadow'} },
  legend: { data:['放电能量','充电能量','净出清','竞价空间均值'], top:5 },
  grid: { left:60, right:70, bottom:60, top:50 },
  xAxis: { type:'category', data:D.dates, axisLabel:{rotate:45, fontSize:10} },
  yAxis: [
    { type:'value', name:'MWh', position:'left' },
    { type:'value', name:'MW', position:'right', splitLine:{show:false} }
  ],
  dataZoom: [{type:'inside'}, {type:'slider', height:18, bottom:5}],
  series: [
    { name:'放电能量', type:'bar', stack:'a', itemStyle:{color:D.C.discharge}, data:D.discharge },
    { name:'充电能量', type:'bar', stack:'a', itemStyle:{color:D.C.charge}, data: D.charge.map(v=>-v) },
    { name:'净出清', type:'line', yAxisIndex:0, smooth:true, itemStyle:{color:D.C.net}, lineStyle:{color:D.C.net, width:2}, data:D.net },
    { name:'竞价空间均值', type:'line', yAxisIndex:1, smooth:true, itemStyle:{color:D.C.bs}, lineStyle:{color:D.C.bs, width:2, type:'dashed'}, data:D.bsmean }
  ]
});

// 图2：96点平均
echarts.init(document.getElementById('c2')).setOption({
  tooltip: { trigger:'axis' },
  legend: { data:['储能总功率','独立储能','抽蓄','虚拟电厂','竞价空间','光伏','风电'], top:5 },
  grid: { left:60, right:70, bottom:40, top:50 },
  xAxis: { type:'category', data:D.timeLabels, axisLabel:{interval:7, fontSize:10} },
  yAxis: [
    { type:'value', name:'MW', position:'left' },
    { type:'value', name:'MW', position:'right', splitLine:{show:false} }
  ],
  series: [
    { name:'储能总功率', type:'bar', itemStyle:{color:D.C.storage}, data:D.hStorage },
    { name:'独立储能', type:'line', smooth:true, symbol:'none', itemStyle:{color:D.C.indep}, lineStyle:{color:D.C.indep, width:1.5}, data:D.hIndep },
    { name:'抽蓄', type:'line', smooth:true, symbol:'none', itemStyle:{color:D.C.draw}, lineStyle:{color:D.C.draw, width:1.5}, data:D.hDraw },
    { name:'虚拟电厂', type:'line', smooth:true, symbol:'none', itemStyle:{color:D.C.virt}, lineStyle:{color:D.C.virt, width:1.5}, data:D.hVirt },
    { name:'竞价空间', type:'line', yAxisIndex:1, smooth:true, symbol:'none', itemStyle:{color:D.C.bs}, lineStyle:{color:D.C.bs, width:2.5}, data:D.hBS },
    { name:'光伏', type:'line', yAxisIndex:1, smooth:true, symbol:'none', itemStyle:{color:D.C.pv}, lineStyle:{color:D.C.pv, width:1.5}, data:D.hPv },
    { name:'风电', type:'line', yAxisIndex:1, smooth:true, symbol:'none', itemStyle:{color:D.C.wind}, lineStyle:{color:D.C.wind, width:1.5}, data:D.hWind }
  ]
});

// 散点工厂
function scatter(series, xName, yName, color) {
  return {
    tooltip: { formatter: p => p.data[2] + '<br/>' + xName + ': ' + p.data[0] + '<br/>' + yName + ': ' + p.data[1] },
    grid: { left:60, right:30, bottom:50, top:30 },
    xAxis: { type:'value', name:xName, nameLocation:'middle', nameGap:30, splitLine:{lineStyle:{color:'#eee'}} },
    yAxis: { type:'value', name:yName, splitLine:{lineStyle:{color:'#eee'}} },
    series: [{ type:'scatter', data:series, symbolSize:9, itemStyle:{ color:color, opacity:0.75 } }]
  };
}
echarts.init(document.getElementById('c3')).setOption(scatter(D.scatterBS, '竞价空间日均(MW)', '储能日均功率(MW)', D.C.storage));
echarts.init(document.getElementById('c4a')).setOption(scatter(D.scatterPV, '光伏日均(MW)', '储能日均功率(MW)', D.C.pv));
echarts.init(document.getElementById('c4b')).setOption(scatter(D.scatterWind, '风电日均(MW)', '储能日均功率(MW)', D.C.wind));

// 图5：相关性热力图
echarts.init(document.getElementById('c5')).setOption({
  tooltip: { formatter: p => D.corrLabels[p.data[1]] + ' ↔ ' + D.corrLabels[p.data[0]] + '<br/>r = ' + p.data[2] },
  grid: { left:100, right:80, bottom:90, top:40 },
  xAxis: { type:'category', data:D.corrLabels, axisLabel:{rotate:40, fontSize:11} },
  yAxis: { type:'category', data:D.corrLabels, axisLabel:{fontSize:11} },
  visualMap: {
    min:-1, max:1, calculable:true, orient:'horizontal', left:'center', bottom:5,
    inRange:{ color:['#f5222d','#f5f5f5','#2c7be5'] }
  },
  series: [{ type:'heatmap', data:D.corrData, label:{show:true, fontSize:9, formatter: p=>p.data[2].toFixed(2)}, emphasis:{itemStyle:{shadowBlur:10}} }]
});

// 图6：代表日曲线
var series6 = [];
var colors6 = ['#2c7be5','#36b37e','#ff7875','#9b6bd9','#faad14','#13c2c2'];
D.pickDates.forEach(function(d, i) {
  var c = colors6[i % colors6.length];
  var cv = D.curves[d];
  series6.push({ name:d+' 储能', type:'line', smooth:true, symbol:'none', yAxisIndex:0, itemStyle:{color:c}, lineStyle:{color:c, width:2}, data:cv.storage });
  series6.push({ name:d+' 竞价空间', type:'line', smooth:true, symbol:'none', yAxisIndex:1, itemStyle:{color:c, opacity:0.55}, lineStyle:{color:c, width:1.5, type:'dashed', opacity:0.55}, data:cv.bs });
});
echarts.init(document.getElementById('c6')).setOption({
  tooltip: { trigger:'axis' },
  legend: { type:'scroll', top:5, textStyle:{fontSize:10} },
  grid: { left:60, right:70, bottom:40, top:50 },
  xAxis: { type:'category', data:D.timeLabels, axisLabel:{interval:7, fontSize:10} },
  yAxis: [
    { type:'value', name:'储能功率(MW)', position:'left' },
    { type:'value', name:'竞价空间(MW)', position:'right', splitLine:{show:false} }
  ],
  series: series6
});

window.addEventListener('resize', function() {
  ['c1','c2','c3','c4a','c4b','c5','c6'].forEach(function(id) {
    var inst = echarts.getInstanceByDom(document.getElementById(id));
    if(inst) inst.resize();
  });
});
</script>
</body>
</html>
"""

# 占位符替换
HTML = HTML.replace("__START__", DATA["date_range"]["start"])
HTML = HTML.replace("__END__", DATA["date_range"]["end"])
HTML = HTML.replace("__NDATES__", str(DATA["date_range"]["n_dates"]))
HTML = HTML.replace("__R_BS__", f"{corr['storage_total_p']['bidding_space']:.2f}")
HTML = HTML.replace("__R_PV__", f"{corr['storage_total_p']['photovoltaic_power_forecast']:.2f}")
HTML = HTML.replace("__R_WIND__", f"{corr['storage_total_p']['wind_power_forecast']:.2f}")
HTML = HTML.replace("__R_LOAD__", f"{corr['storage_total_p']['dispatched_load_forecast']:.2f}")
HTML = HTML.replace("__R_INDEP__", f"{corr['storage_total_p']['independent_p']:.2f}")
HTML = HTML.replace("__R_DRAW__", f"{corr['storage_total_p']['draw_p']:.2f}")
HTML = HTML.replace("__JS_DATA__", JS_DATA)

out_dir = ROOT / "output" / "竞价空间分析结果"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "储能出清功率分析.html"
out_path.write_text(HTML, encoding="utf-8")
print(f"Saved: {out_path} ({out_path.stat().st_size} bytes)")
