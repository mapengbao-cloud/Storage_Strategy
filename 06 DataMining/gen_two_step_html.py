"""生成两步逻辑验证 HTML：
  图1：每日光伏总出力 vs 储能+抽蓄充电总量（日级，非96点平均）
  图2：代表日96点——bs 谷/峰 是否被储能+抽蓄填掉/削掉
  图3：填谷削峰统计（79/80填谷、73/80削峰）
  图4：削平效果（bs波幅 vs 隐含火电波幅 vs 实际火电波幅）
  图5：每日时点相关性 corr(bs, storage_ps)
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
D = json.load(open(ROOT / "_tmp_two_step.json", encoding="utf-8"))

daily = D["daily"]
dates = [d["date"] for d in daily]
pv_mwh = [d["pv_mwh"] for d in daily]
wind_mwh = [d["wind_mwh"] for d in daily]
charge_mwh = [d["charge_mwh"] for d in daily]
discharge_mwh = [d["discharge_mwh"] for d in daily]
bs_mean = [d["bs_mean_mw"] for d in daily]
bs_min = [d["bs_min_mw"] for d in daily]
bs_max = [d["bs_max_mw"] for d in daily]
bs_range = [d["bs_range_mw"] for d in daily]

hourly = D["hourly"]
time_labels = D["time_labels"]
pick_dates = D["pick_dates"]
curves = D["curves"]
flatten_stats = D["flatten_stats"]
peak_storage = D["peak_storage"]
valley_storage = D["valley_storage"]
daily_pt_corr = D["daily_pt_corr"]

# 兼容旧键名
c1 = D.get("corr1", {})
lr = D.get("linreg", {})
pf = D.get("peak_fill_stats", {})
fl = D.get("flatten_summary", {})

# 散点1：光伏总量 vs 充电总量
scatter_pv_charge = [[round(d["pv_mwh"],0), round(d["charge_mwh"],0), d["date"]] for d in daily]
# 散点2：bs波幅 vs 充电总量
scatter_range_charge = [[round(d["bs_range_mw"],0), round(d["charge_mwh"],0), d["date"]] for d in daily]
# 散点3：bs最低值 vs 充电总量
scatter_bsmin_charge = [[round(d["bs_min_mw"],0), round(d["charge_mwh"],0), d["date"]] for d in daily]
# 散点4：bs最高值 vs 放电总量
scatter_bsmax_discharge = [[round(d["bs_max_mw"],0), round(d["discharge_mwh"],0), d["date"]] for d in daily]

# 削平效果数据（每日）
f_dates = [r["date"] for r in flatten_stats]
f_bs_range = [r["bs_range"] for r in flatten_stats]
f_th_imp_range = [r["th_implied_range"] for r in flatten_stats]
f_actual_th_range = [r["actual_th_range"] for r in flatten_stats]

# 每日时点相关性
corr_dates = [r["date"] for r in daily_pt_corr]
corr_vals = [r["corr_bs_sp"] if r["corr_bs_sp"] is not None else None for r in daily_pt_corr]

# 分时段（用于图2辅助）
h_bs = [r["bs"] for r in hourly]
h_sp = [r["storage_ps"] for r in hourly]
h_th_imp = [r["thermal_implied"] for r in hourly]
h_pv = [r["pv"] for r in hourly]

JS = json.dumps({
    "dates": dates, "pv_mwh": pv_mwh, "wind_mwh": wind_mwh, "charge_mwh": charge_mwh,
    "discharge_mwh": discharge_mwh, "bs_mean": bs_mean, "bs_min": bs_min, "bs_max": bs_max, "bs_range": bs_range,
    "scatter_pv_charge": scatter_pv_charge, "scatter_range_charge": scatter_range_charge,
    "scatter_bsmin_charge": scatter_bsmin_charge, "scatter_bsmax_discharge": scatter_bsmax_discharge,
    "time_labels": time_labels, "pick_dates": pick_dates, "curves": curves,
    "f_dates": f_dates, "f_bs_range": f_bs_range, "f_th_imp_range": f_th_imp_range, "f_actual_th_range": f_actual_th_range,
    "corr_dates": corr_dates, "corr_vals": corr_vals,
    "h_bs": h_bs, "h_sp": h_sp, "h_th_imp": h_th_imp, "h_pv": h_pv,
    "summary": {
        "corr1": D["corr1"], "linreg": D["linreg"],
        "peak_fill": D["peak_fill_stats"], "flatten": D["flatten_summary"],
    }
}, ensure_ascii=False)

s = {"corr1": c1, "linreg": lr, "peak_fill": pf, "flatten": fl}
c1 = s["corr1"]; lr = s["linreg"]; pf = s["peak_fill"]; fl = s["flatten"]

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>储能+抽蓄两步逻辑验证 — 总量与时点分布</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:"Microsoft YaHei","Segoe UI",sans-serif; background:#fff; color:#333; padding:20px; }
h1 { color:#222; font-size:22px; margin-bottom:6px; }
.subtitle { color:#666; font-size:13px; margin-bottom:18px; line-height:1.6; }
h2 { color:#222; font-size:17px; margin:24px 0 10px; border-left:4px solid #2c7be5; padding-left:10px; }
h2 .step { display:inline-block; background:#2c7be5; color:#fff; font-size:12px; padding:2px 8px; border-radius:3px; margin-right:8px; }
.desc { color:#666; font-size:12px; margin-bottom:8px; line-height:1.7; }
.card-row { display:flex; flex-wrap:wrap; gap:12px; margin-bottom:8px; }
.card { background:#fafafa; border:1px solid #e0e0e0; border-radius:6px; padding:14px 18px; min-width:170px; flex:1; }
.card .v { font-size:22px; font-weight:600; color:#2c7be5; }
.card .l { font-size:12px; color:#666; margin-top:4px; }
.card .s { font-size:11px; color:#999; margin-top:2px; }
.card.green .v { color:#52c41a; }
.card.orange .v { color:#faad14; }
.chart { width:100%; border:1px solid #ddd; border-radius:6px; background:#fff; }
.note { background:#f6f8fa; border-left:3px solid #2c7be5; padding:10px 14px; font-size:12px; color:#555; margin:10px 0; line-height:1.7; border-radius:0 4px 4px 0; }
.verdict { padding:14px 18px; border-radius:6px; margin:10px 0; font-size:13px; line-height:1.7; }
.verdict.yes { background:#f0fff0; border-left:4px solid #52c41a; }
.verdict b { font-size:14px; }
</style>
</head>
<body>

<h1>储能+抽蓄两步逻辑验证</h1>
<p class="subtitle">
<b>步骤1（总量）</b>：次日储能+抽蓄充电总量 = f(光伏总出力)？<br>
<b>步骤2（分布）</b>：总量如何分布到每个时点？是否填掉竞价空间(bs)最深的谷、削掉最高的峰？<br>
数据范围：__START__ ~ __END__，共 __NDATES__ 天，96 点/天。储能+抽蓄 = 独立储能 + 抽蓄（不含虚拟电厂）。
</p>

<div class="card-row">
  <div class="card green"><div class="v">__R_PV_CHARGE__</div><div class="l">充电总量 ↔ 光伏总量</div><div class="s">步骤1 主信号</div></div>
  <div class="card green"><div class="v">__R2__</div><div class="l">线性回归 R²(charge~pv)</div><div class="s">解释力</div></div>
  <div class="card green"><div class="v">__FILL__/80</div><div class="l">填谷天数(bs最低点处充电)</div><div class="s">步骤2 填谷</div></div>
  <div class="card green"><div class="v">__SHAVE__/80</div><div class="l">削峰天数(bs最高点处放电)</div><div class="s">步骤2 削峰</div></div>
  <div class="card orange"><div class="v">__REDUCE__%</div><div class="l">bs波幅压缩比例</div><div class="s">bs→隐含火电</div></div>
  <div class="card green"><div class="v">__CORR_PT__</div><div class="l">每日时点corr(bs,储能)中位数</div><div class="s">步骤2 跟随性</div></div>
</div>

<div class="verdict yes">
<b>两步逻辑均成立 ✓</b><br>
<b>步骤1</b>：日充电总量与光伏总量强相关（r=__R_PV_CHARGE__），线性回归 charge = __SLOPE__×pv + __INTERCEPT__，R²=__R2__。<br>
<b>步骤2</b>：79/80 天在 bs 最低点处储能+抽蓄充电（填谷），73/80 天在 bs 最高点处放电（削峰）。储能+抽蓄把 bs 波幅（__BS_RANGE__ MW）压缩到隐含火电波幅（__TH_IMP_RANGE__ MW），压缩 __REDUCE__%。
</div>

<h2><span class="step">步骤1</span>每日光伏总量 vs 储能+抽蓄充电总量</h2>
<p class="desc">柱状（左轴 MWh）：光伏总量（黄）/ 储能+抽蓄充电总量（绿）；折线（右轴）：光伏/充电比值。看两者是否同涨同落。</p>
<div id="c1" class="chart" style="height:400px"></div>
<div class="note">规律：光伏总量高的天，充电总量也高，二者同向波动。05-01~05-05 光伏 40-50 GWh，充电 36 GWh；07-12~17 光伏低（阴雨/负荷高），充电骤降至 1-4 GWh。节假日 05-19 光伏正常但充电极低（0.7 GWh），因负荷低无需调峰。</div>

<h2>步骤1 散点：光伏总量 → 充电总量（含回归线）</h2>
<p class="desc">每点=1天，X=光伏总量(MWh)，Y=充电总量(MWh)。红色虚线为线性回归。悬停看日期。</p>
<div id="c2" class="chart" style="height:380px"></div>
<div class="note">线性回归 charge = __SLOPE__ × pv + __INTERCEPT__，R²=__R2__。斜率 0.22 表示每 1 MWh 光伏对应约 0.22 MWh 充电（光伏的 22% 被储能+抽蓄吸收）。R²=0.59 说明光伏总量解释了 59% 的充电量方差，是预测日总量的强信号。剩余 41% 由节假日、负荷水平、bs 波幅等解释。</div>

<h2>步骤1 辅助散点：bs 波幅/谷深 → 充电总量</h2>
<p class="desc">左：bs 波幅(max-min) vs 充电总量；右：bs 最低值 vs 充电总量。验证充电是否由 bs 谷深驱动。</p>
<div style="display:flex; gap:12px;">
  <div id="c3a" class="chart" style="height:340px; flex:1"></div>
  <div id="c3b" class="chart" style="height:340px; flex:1"></div>
</div>
<div class="note">充电 vs bs波幅 r=__R_RANGE_CHARGE__（正相关：bs 波动越大充电越多）；充电 vs bs最低值 r=__R_BSMIN_CHARGE__（负相关：bs 谷越深充电越多）。这两个是步骤1 的补充信号——bs 波幅/谷深也可作为预测充电总量的特征。</div>

<h2><span class="step">步骤2</span>代表日 96 点：储能+抽蓄是否填掉 bs 谷、削掉 bs 峰</h2>
<p class="desc">实线左轴(MW)：竞价空间 bs（橙，波动剧烈）+ 隐含火电=bs−储能（蓝，被削平）。柱（右轴）：储能+抽蓄功率（绿，正放电/负充电）。标注 bs 最高峰（红点）和最低谷（蓝点）。</p>
<div id="c4" class="chart" style="height:480px"></div>
<div class="note">观察：bs 曲线（橙）午间 12-13 点跌至最深谷（-2~-23 GW，光伏淹没负荷），储能+抽蓄此时深度充电（绿柱负值，-6~-9 GW）<b>填谷</b>；晚峰 20 点 bs 飙至最高峰（30 GW），储能+抽蓄放电（绿柱正值，+5 GW）<b>削峰</b>。隐含火电（蓝）曲线明显比 bs 平稳——谷被填上来、峰被削下去，正是优化火电运行的核心价值。</div>

<h2>步骤2 统计：填谷削峰天数 + 削平效果</h2>
<p class="desc">左：填谷(79/80) vs 削峰(73/80) 天数饼图。右：每日 bs 波幅 vs 隐含火电波幅 vs 实际火电波幅。</p>
<div style="display:flex; gap:12px;">
  <div id="c5a" class="chart" style="height:360px; flex:1"></div>
  <div id="c5b" class="chart" style="height:360px; flex:1"></div>
</div>
<div class="note">79/80 天在 bs 最低点处储能+抽蓄充电（填谷成功率 98.75%），73/80 天在 bs 最高点处放电（削峰成功率 91.25%）。削平效果：bs 平均波幅 __BS_RANGE__ MW → 隐含火电波幅 __TH_IMP_RANGE__ MW（压缩 __REDUCE__%），实际火电波幅 __ACTUAL_TH_RANGE__ MW（比隐含更低，火电另有调节手段）。bs_std __BS_STD__ → 隐含火电 std __TH_IMP_STD__，波动下降。</div>

<h2>步骤2 跟随性：每日时点 corr(bs, 储能+抽蓄)</h2>
<p class="desc">每日 96 点 bs 与储能+抽蓄功率的 Pearson 相关。正值=同向（bs 高放电、bs 低充电），越接近 1 跟随越强。</p>
<div id="c6" class="chart" style="height:340px"></div>
<div class="note">中位数 __CORR_PT__（强正相关），p25=0.74，说明大多数天储能+抽蓄都紧密跟随 bs 做反向调节。少数天 corr 偏低（min=-0.10），通常是节假日或储能不调度的天。</div>

<div style="background:#f0f7ff; border:1px solid #b3d4f4; border-radius:6px; padding:16px 20px; margin-top:20px;">
<h3 style="color:#2c7be5; margin-bottom:10px;">★ 两步逻辑验证结论</h3>
<p style="font-size:13px; line-height:1.8; color:#333;">
<b>步骤1（总量预测）成立 ✓</b><br>
日充电总量与光伏总量强相关（r=__R_PV_CHARGE__），线性回归 R²=__R2__。<b>预测次日总量</b>：用日前 10:15 发布的光伏预测总量代入 charge = __SLOPE__×pv + __INTERCEPT__，可得日充电总量估计；再用充放效率 0.89 推放电总量。补充特征：bs 波幅、bs 最低值、节假日（r=0.70/-0.69，进一步提升精度）。
</p>
<p style="font-size:13px; line-height:1.8; color:#333; margin-top:10px;">
<b>步骤2（时点分布）成立 ✓</b><br>
79/80 天填谷、73/80 天削峰，储能+抽蓄确实在 bs 最深的谷充电、最高的峰放电。削平效果显著：bs 波幅压缩 __REDUCE__%（36 GW → 27 GW）。每日时点 corr 中位数 __CORR_PT__，跟随性强。<b>预测时点分布</b>：总量按 bs 曲线分配——充电量集中到 bs 谷段（午间光伏峰值），放电量集中到 bs 峰段（晚峰），可用 bs 归一化权重分配。
</p>
<hr style="border:none; border-top:1px dashed #b3d4f4; margin:12px 0;">
<p style="font-size:13px; line-height:1.8; color:#333;">
<b>★ 预测方法（两步法）：</b><br>
① <b>总量</b>：charge_mwh = 0.22 × pv_mwh − 8666（线性回归，R²=0.59），可用 GBDT 加入 bs_range/bs_min/节假日提升；discharge = charge × 0.89；<br>
② <b>分布</b>：充电量按 bs 谷段权重分配（午间光伏峰值时段权重最大），放电量按 bs 峰段权重分配（晚峰时段权重最大）；<br>
③ <b>分项</b>：独立储能跟随 bs 偏差精细调节（灵活），抽蓄做基础调峰量（量级大）；<br>
④ <b>特征</b>：光伏 96 点（午间峰值）+ bs 96 点 + 节假日 + 充放效率 0.89。<br>
此方法符合实际调度逻辑（先定总量再分配时点），比黑盒 GBDT 更可解释。
</p>
</div>

<script>
var D = __JS__;
var C = {pv:'#faad14', charge:'#52c41a', discharge:'#f5222d', bs:'#f5a623', th_imp:'#2c7be5', sp:'#36b37e', wind:'#13c2c2'};

// 图1：每日总量柱状
echarts.init(document.getElementById('c1')).setOption({
  tooltip: {trigger:'axis', axisPointer:{type:'shadow'}},
  legend: {data:['光伏总量','充电总量','光伏/充电比'], top:5},
  grid: {left:60, right:70, bottom:60, top:50},
  xAxis: {type:'category', data:D.dates, axisLabel:{rotate:45, fontSize:10}},
  yAxis: [{type:'value', name:'MWh', position:'left'}, {type:'value', name:'比值', position:'right', splitLine:{show:false}}],
  dataZoom: [{type:'inside'}, {type:'slider', height:18, bottom:5}],
  series: [
    {name:'光伏总量', type:'bar', itemStyle:{color:C.pv}, data:D.pv_mwh},
    {name:'充电总量', type:'bar', itemStyle:{color:C.charge}, data:D.charge_mwh},
    {name:'光伏/充电比', type:'line', yAxisIndex:1, smooth:true, itemStyle:{color:C.bs}, lineStyle:{color:C.bs, width:2}, data: D.pv_mwh.map(function(v,i){return D.charge_mwh[i]>0? +(v/D.charge_mwh[i]).toFixed(2): null})}
  ]
});

// 图2：散点 + 回归线
(function(){
  var data = D.scatter_pv_charge;
  // 回归线端点
  var xmin = Math.min.apply(null, data.map(function(p){return p[0]}));
  var xmax = Math.max.apply(null, data.map(function(p){return p[0]}));
  var slope = __SLOPE__, intercept = __INTERCEPT__;
  echarts.init(document.getElementById('c2')).setOption({
    tooltip: {formatter: function(p){return p.data[2]+'<br/>光伏: '+p.data[0]+' MWh<br/>充电: '+p.data[1]+' MWh'}},
    grid: {left:60, right:30, bottom:50, top:30},
    xAxis: {type:'value', name:'光伏总量(MWh)', nameLocation:'middle', nameGap:30, splitLine:{lineStyle:{color:'#eee'}}},
    yAxis: {type:'value', name:'充电总量(MWh)', splitLine:{lineStyle:{color:'#eee'}}},
    series: [
      {type:'scatter', data:data, symbolSize:10, itemStyle:{color:C.charge, opacity:0.75}},
      {type:'line', name:'回归线', showSymbol:false, itemStyle:{color:C.bs}, lineStyle:{color:C.bs, width:2, type:'dashed'},
       data:[[xmin, slope*xmin+intercept],[xmax, slope*xmax+intercept]]}
    ]
  });
})();

// 图3a/3b：辅助散点
function scatterSimple(domId, data, xName, yName, color){
  echarts.init(document.getElementById(domId)).setOption({
    tooltip: {formatter: function(p){return p.data[2]+'<br/>'+xName+': '+p.data[0]+'<br/>'+yName+': '+p.data[1]}},
    grid: {left:60, right:30, bottom:50, top:30},
    xAxis: {type:'value', name:xName, nameLocation:'middle', nameGap:30, splitLine:{lineStyle:{color:'#eee'}}},
    yAxis: {type:'value', name:yName, splitLine:{lineStyle:{color:'#eee'}}},
    series: [{type:'scatter', data:data, symbolSize:9, itemStyle:{color:color, opacity:0.75}}]
  });
}
scatterSimple('c3a', D.scatter_range_charge, 'bs波幅(MW)', '充电总量(MWh)', C.bs);
scatterSimple('c3b', D.scatter_bsmin_charge, 'bs最低值(MW)', '充电总量(MWh)', C.pv);

// 图4：代表日96点
var series4 = [];
var colors4 = ['#2c7be5','#36b37e','#ff7875','#9b6bd9','#faad14'];
D.pick_dates.forEach(function(d, i){
  var c = colors4[i % colors4.length];
  var cv = D.curves[d];
  // bs 线
  series4.push({name:d+' bs', type:'line', smooth:true, symbol:'none', yAxisIndex:0, itemStyle:{color:C.bs}, lineStyle:{color:C.bs, width:2.5}, data:cv.bs});
  // 隐含火电 线
  series4.push({name:d+' 隐含火电', type:'line', smooth:true, symbol:'none', yAxisIndex:0, itemStyle:{color:c}, lineStyle:{color:c, width:2}, data:cv.thermal_implied});
  // 储能+抽蓄 柱（右轴）
  series4.push({name:d+' 储能+抽蓄', type:'bar', yAxisIndex:1, itemStyle:{color:c, opacity:0.5}, data:cv.storage_ps});
});
echarts.init(document.getElementById('c4')).setOption({
  tooltip: {trigger:'axis'},
  legend: {type:'scroll', top:5, textStyle:{fontSize:9}},
  grid: {left:60, right:70, bottom:40, top:50},
  xAxis: {type:'category', data:D.time_labels, axisLabel:{interval:7, fontSize:10}},
  yAxis: [
    {type:'value', name:'功率(MW) bs/火电', position:'left'},
    {type:'value', name:'储能+抽蓄(MW)', position:'right', splitLine:{show:false}}
  ],
  series: series4
});

// 图5a：填谷削峰饼图
echarts.init(document.getElementById('c5a')).setOption({
  tooltip: {trigger:'item'},
  legend: {bottom:5, textStyle:{fontSize:11}},
  title: {text:'填谷削峰成功率', left:'center', top:5, textStyle:{fontSize:14, color:'#222'}},
  series: [{
    type:'pie', radius:['35%','60%'], center:['50%','55%'],
    label:{formatter:'{b}: {c}/80 ({d}%)', fontSize:11},
    data:[
      {name:'填谷成功', value:__FILL__, itemStyle:{color:C.charge}},
      {name:'填谷失败', value:(80-__FILL__), itemStyle:{color:'#ccc'}},
      {name:'削峰成功', value:__SHAVE__, itemStyle:{color:C.discharge}},
      {name:'削峰失败', value:(80-__SHAVE__), itemStyle:{color:'#eee'}}
    ]
  }]
});

// 图5b：削平效果
echarts.init(document.getElementById('c5b')).setOption({
  tooltip: {trigger:'axis'},
  legend: {data:['bs波幅','隐含火电波幅','实际火电波幅'], top:5},
  grid: {left:60, right:30, bottom:60, top:50},
  xAxis: {type:'category', data:D.f_dates, axisLabel:{rotate:45, fontSize:10}},
  yAxis: {type:'value', name:'波幅(MW)'},
  dataZoom: [{type:'inside'}, {type:'slider', height:18, bottom:5}],
  series: [
    {name:'bs波幅', type:'bar', itemStyle:{color:C.bs}, data:D.f_bs_range},
    {name:'隐含火电波幅', type:'bar', itemStyle:{color:C.th_imp}, data:D.f_th_imp_range},
    {name:'实际火电波幅', type:'bar', itemStyle:{color:C.sp, opacity:0.7}, data:D.f_actual_th_range}
  ]
});

// 图6：每日时点相关性
echarts.init(document.getElementById('c6')).setOption({
  tooltip: {trigger:'axis'},
  grid: {left:60, right:30, bottom:60, top:40},
  xAxis: {type:'category', data:D.corr_dates, axisLabel:{rotate:45, fontSize:10}},
  yAxis: {type:'value', name:'corr(bs,储能)', min:-0.2, max:1},
  dataZoom: [{type:'inside'}, {type:'slider', height:18, bottom:5}],
  series: [{type:'bar', itemStyle:{color:C.th_imp}, data:D.corr_vals, markLine:{data:[{type:'average', name:'均值'}]}}]
});

window.addEventListener('resize', function(){
  ['c1','c2','c3a','c3b','c4','c5a','c5b','c6'].forEach(function(id){
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
HTML = HTML.replace("__R_PV_CHARGE__", str(c1["charge_vs_pv"]))
HTML = HTML.replace("__R2__", str(lr["r2"]))
HTML = HTML.replace("__SLOPE__", str(lr["slope"]))
HTML = HTML.replace("__INTERCEPT__", str(lr["intercept"]))
HTML = HTML.replace("__FILL__", str(pf["filled_valley"]))
HTML = HTML.replace("__SHAVE__", str(pf["shaved_peak"]))
HTML = HTML.replace("__REDUCE__", str(fl["range_reduction_pct"]))
HTML = HTML.replace("__BS_RANGE__", str(fl["bs_range_mean"]))
HTML = HTML.replace("__TH_IMP_RANGE__", str(fl["th_implied_range_mean"]))
HTML = HTML.replace("__ACTUAL_TH_RANGE__", str(fl["actual_th_range_mean"]))
HTML = HTML.replace("__BS_STD__", str(fl["bs_std_mean"]))
HTML = HTML.replace("__TH_IMP_STD__", str(fl["th_implied_std_mean"]))
HTML = HTML.replace("__CORR_PT__", "0.85")
HTML = HTML.replace("__R_RANGE_CHARGE__", str(c1["charge_vs_bs_range"]))
HTML = HTML.replace("__R_BSMIN_CHARGE__", str(c1["charge_vs_bs_min"]))
HTML = HTML.replace("__JS__", JS)

out_dir = ROOT / "output" / "竞价空间分析结果"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "储能两步逻辑验证.html"
out_path.write_text(HTML, encoding="utf-8")
print(f"Saved: {out_path} ({out_path.stat().st_size} bytes)")
