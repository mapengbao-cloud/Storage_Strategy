"""Generate self-contained prescheduling HTML with all dates embedded.

Layout: Thermal section first (rank table + pattern pie + TOP50 bar + pattern curves,
zero-output as table), then Storage section (stat table + pie + bar + pattern curves,
zero-output as list).
"""
import json

TL = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]


def generate_page(all_results_path, out_path):
    with open(all_results_path, encoding='utf-8') as f:
        all_data = json.load(f)
    dates_list = all_data["dates"]
    all_results = all_data["data"]

    init_date = '2026-06-05'
    if init_date not in all_results:
        init_date = sorted(all_results.keys())[-1]
    init = all_results[init_date]

    st = init["storage"]
    th = init["thermal"]
    init_tpat = {}
    for it in th:
        init_tpat.setdefault(it["pattern"], []).append(it)
    init_tpat = dict(sorted(init_tpat.items(), key=lambda x: len(x[1]), reverse=True))
    init_spat = {}
    for it in st:
        init_spat.setdefault(it["pattern"], []).append(it)
    init_spat = dict(sorted(init_spat.items(), key=lambda x: len(x[1]), reverse=True))

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>山东省级预调度分析 — 火电 & 储能</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#fff;color:#333;padding:20px}}
h1{{text-align:center;font-size:20px;color:#222;margin-bottom:4px}}
h2{{font-size:17px;color:#222;margin:28px 0 6px;padding:8px 14px;background:#e8edf5;border-left:4px solid #2c7be5}}
.subtitle{{text-align:center;font-size:12px;color:#888;margin-bottom:8px;line-height:1.6}}
.sec{{font-size:14px;color:#222;margin:18px 0 8px;padding:6px 12px;background:#f0f4ff;border-left:3px solid #2c7be5}}
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
td.name{{text-align:left;font-family:monospace;font-size:10px}}
tr:hover{{background:#fafafa}}
.notes{{font-size:11px;color:#666;line-height:1.7;margin-top:20px;padding:12px 16px;background:#fafafa;border-radius:6px;border:1px solid #e0e0e0}}
.notes b{{color:#333}}
.date-picker{{display:flex;align-items:center;justify-content:center;gap:12px;margin:10px 0 16px}}
.date-picker label{{font-size:13px;color:#555}}
.date-picker select{{padding:6px 12px;font-size:13px;border:1px solid #ccc;border-radius:4px;background:#fff;min-width:200px}}
.date-picker button{{padding:6px 16px;font-size:13px;background:#2c7be5;color:#fff;border:none;border-radius:4px;cursor:pointer}}
.date-picker button:hover{{background:#1a5db0}}
.date-picker .loading{{font-size:12px;color:#e5731c;display:none}}
</style>
</head>
<body>
<h1>山东省级预调度分析 — 火电 & 储能</h1>
<p class="subtitle" id="subtitle">数据源: shandong_px_provincial_prescheduling_results | 日期: {init_date} | 火电机组: {len(th)} 台 | 储能机组: {len(st)} 台</p>

<div class="date-picker">
<label>选择日期:</label>
<select id="dateSelect"></select>
<button onclick="loadDate()">加载数据</button>
<span class="loading" id="loading">加载中...</span>
</div>

<!-- ====== THERMAL SECTION ====== -->
<h2>一、火电机组</h2>

<div class="stats">
<div class="card"><div class="v" id="v-thermal">{len(th)}</div><div class="l">火电机组数</div></div>
<div class="card"><div class="v" id="v-peak">{th[0]['peak']:.0f}</div><div class="l">火电最大峰值(MW)</div></div>
<div class="card"><div class="v" id="v-tpat">{len(init_tpat)}</div><div class="l">火电调度模式数</div></div>
</div>

<div class="sec">火电调度模式分布</div>
<div class="grid">
<div class="box"><h4>火电调度模式分布</h4><div id="c-tpie" class="chart"></div></div>
<div class="box"><h4>火电 TOP 50 峰值 vs 均值</h4><div id="c-tbar" class="chart" style="height:900px"></div></div>
</div>

<div class="sec">火电 — 按调度模式分组 96点出力曲线</div>
<div id="thermal-patterns"></div>

<div class="sec">火电全列表 — 按峰值降序</div>
<div style="overflow-x:auto"><table><thead><tr><th>排名</th><th>机组名称</th><th>峰值(MW)</th><th>均值(MW)</th><th>谷值(MW)</th><th>CV(%)</th><th>分型</th></tr></thead><tbody id="thermalTable"></tbody></table></div>

<!-- ====== STORAGE SECTION ====== -->
<h2>二、储能机组</h2>

<div class="stats">
<div class="card"><div class="v" id="v-storage">{len(st)}</div><div class="l">储能机组数</div></div>
<div class="card"><div class="v" id="v-charge">{init['total_charge']:.0f}</div><div class="l">储能总充电量(MWh)</div></div>
<div class="card"><div class="v" id="v-discharge">{init['total_discharge']:.0f}</div><div class="l">储能总放电量(MWh)</div></div>
<div class="card"><div class="v" id="v-spat">{len(init_spat)}</div><div class="l">储能调度模式数</div></div>
</div>

<div class="sec">储能调度模式分布 & 充放电量对比</div>
<div class="grid">
<div class="box"><h4>储能调度模式分布</h4><div id="c-spie" class="chart"></div></div>
<div class="box"><h4>储能全部 充放电量对比 (MWh)</h4><div id="c-sbar" class="chart" style="height:{max(500, len(st)*18)}px"></div></div>
</div>

<div class="sec">储能 — 按调度模式分组 96点出力曲线</div>
<div id="storage-patterns"></div>

<div class="sec">储能充放统计 — 全部机组</div>
<div style="overflow-x:auto"><table><thead><tr><th>排名</th><th>机组名称</th><th>充电功率均值(MW)</th><th>充电电量(MWh)</th><th>放电功率均值(MW)</th><th>放电电量(MWh)</th><th>充放效率</th><th>调度模式</th></tr></thead><tbody id="storageTable"></tbody></table></div>

<div class="notes">
<b>表:</b> shandong_px_provincial_prescheduling_results — 山东省级日前预调度结果<br>
<b>字段:</b> date / generator_name / time_order(1-96) / declaration_power(MW)<br>
<b>火电分型说明:</b><br>
  &bull; <b>一充一放型(抽蓄)</b>: 含负值出力，名称含"机"/"#"的抽水蓄能 &bull; <b>纯充电型</b>: 仅负值出力<br>
  &bull; <b>日内启机</b>: 前6h接近零出力→后续启动 &bull; <b>日内停机</b>: 前中段出力→后6h降至零<br>
  &bull; <b>平稳/直线型</b>: CV &lt; 5%（含恒定出力全天直线型）<br>
  &bull; <b>午间调峰机组</b>: 早晚负荷高、中午负荷低的调峰火电（其余非零出力火电均归此类）<br>
  &bull; <b>零出力</b>: 全天96点出力均为0
</div>
'''

    # JavaScript
    html += f'''
<script>
var TL = ["00:00","00:15","00:30","00:45","01:00","01:15","01:30","01:45","02:00","02:15","02:30","02:45","03:00","03:15","03:30","03:45","04:00","04:15","04:30","04:45","05:00","05:15","05:30","05:45","06:00","06:15","06:30","06:45","07:00","07:15","07:30","07:45","08:00","08:15","08:30","08:45","09:00","09:15","09:30","09:45","10:00","10:15","10:30","10:45","11:00","11:15","11:30","11:45","12:00","12:15","12:30","12:45","13:00","13:15","13:30","13:45","14:00","14:15","14:30","14:45","15:00","15:15","15:30","15:45","16:00","16:15","16:30","16:45","17:00","17:15","17:30","17:45","18:00","18:15","18:30","18:45","19:00","19:15","19:30","19:45","20:00","20:15","20:30","20:45","21:00","21:15","21:30","21:45","22:00","22:15","22:30","22:45","23:00","23:15","23:30","23:45"];
var ALL_CHARTS = [];
var currentDate = '{init_date}';

var ALL_DATES = {json.dumps(dates_list, ensure_ascii=False)};
var ALL_RESULTS = {json.dumps(all_results, ensure_ascii=False)};

var COLORS_64 = ["#e5731c","#2c7be5","#43a047","#e53935","#8e24aa","#00acc1","#ff6f00","#5c6bc0",
    "#26a69a","#d81b60","#7cb342","#039be5","#c0ca33","#f4511e","#3949ab",
    "#546e7a","#8d6e63","#ab47bc","#ef5350","#66bb6a","#ffa726","#42a5f5","#ec407a",
    "#9ccc65","#ff7043","#5c6bc0","#26c6da","#d4e157","#78909c","#f06292",
    "#4db6ac","#ba68c8","#fbc02d","#607d8b","#795548","#e91e63","#2196f3","#4caf50",
    "#ff9800","#9c27b0","#009688","#f44336","#3f51b5","#cddc39","#00bcd4","#ff5722",
    "#673ab7","#8bc34a","#03a9f4","#ffc107","#e040fb","#69f0ae","#448aff","#ff6e40",
    "#b388ff","#64ffda","#82b1ff","#ffd740","#ea80fc","#b9f6ca","#8c9eff","#ffab40"];

function shortName(n) {{ return n.replace("山东.",""); }}

function baseOpt() {{
    return {{
        tooltip: {{trigger:"axis", textStyle:{{fontSize:11}},
            position: function(pt,params,dom,rect,size) {{
                var x=pt[0],y=pt[1],w=size.contentSize[0],h=size.contentSize[1];
                var vw=size.viewSize[0],vh=size.viewSize[1];
                var px=x+15,py=y+15;
                if(px+w>vw) px=x-w-15; if(py+h>vh) py=y-h-15;
                return [px,py];
            }},
            extraCssText:'max-height:400px;overflow-y:auto;'
        }},
        grid: {{left:70,right:30,top:16,bottom:40}},
        xAxis: {{type:"category",data:TL,axisLabel:{{color:"#666",fontSize:9,interval:7}},axisLine:{{lineStyle:{{color:"#ccc"}}}}}},
        yAxis: {{type:"value",name:"MW",axisLabel:{{color:"#666",fontSize:10}},splitLine:{{lineStyle:{{color:"#eee"}}}}}}
    }};
}}

function makePie(id, data) {{
    var c = echarts.init(document.getElementById(id)); ALL_CHARTS.push(c);
    c.setOption({{tooltip:{{trigger:"item"}},
        legend:{{orient:"vertical",right:10,top:10,textStyle:{{fontSize:10}},type:"scroll",height:300}},
        series:[{{type:"pie",radius:["35%","65%"],center:["35%","50%"],label:{{fontSize:9}},data:data}}]
    }});
}}

function makeBar(id, names, d1, d2, n1, n2, unit) {{
    var c = echarts.init(document.getElementById(id)); ALL_CHARTS.push(c);
    c.setOption({{tooltip:{{trigger:"axis",axisPointer:{{type:"shadow"}}}},
        grid:{{left:140,right:40,top:10,bottom:30}},
        xAxis:{{type:"value",name:unit,axisLabel:{{color:"#666",fontSize:10}},splitLine:{{lineStyle:{{color:"#eee"}}}}}},
        yAxis:{{type:"category",data:names,axisLabel:{{color:"#666",fontSize:9}},inverse:true}},
        series:[
            {{name:n1,type:"bar",data:d1,itemStyle:{{color:"#2c7be5"}},barMaxWidth:16}},
            {{name:n2,type:"bar",data:d2,itemStyle:{{color:"#a0c4f0"}},barMaxWidth:16}}],
        legend:{{data:[n1,n2],bottom:0}}
    }});
}}

function makeBar2(id, names, d1, d2, n1, n2, unit) {{
    var c = echarts.init(document.getElementById(id)); ALL_CHARTS.push(c);
    c.setOption({{tooltip:{{trigger:"axis",axisPointer:{{type:"shadow"}}}},
        grid:{{left:140,right:40,top:10,bottom:30}},
        xAxis:{{type:"value",name:unit,axisLabel:{{color:"#666",fontSize:10}},splitLine:{{lineStyle:{{color:"#eee"}}}}}},
        yAxis:{{type:"category",data:names,axisLabel:{{color:"#666",fontSize:9}},inverse:true}},
        series:[
            {{name:n1,type:"bar",data:d1,itemStyle:{{color:"#43a047"}},barMaxWidth:16}},
            {{name:n2,type:"bar",data:d2,itemStyle:{{color:"#e5731c"}},barMaxWidth:16}}],
        legend:{{data:[n1,n2],bottom:0}}
    }});
}}

function makeLine(id, series, lh) {{
    var c = echarts.init(document.getElementById(id)); ALL_CHARTS.push(c);
    var opt = baseOpt(); opt.series = series;
    opt.legend = {{show:true,bottom:0,textStyle:{{fontSize:9}},type:"scroll",height:lh}};
    c.setOption(opt);
}}

function hash(s) {{ var h=0; for(var i=0;i<s.length;i++){{h=((h<<5)-h)+s.charCodeAt(i);h|=0;}} return h; }}

function renderAll(d) {{
    var th=d.thermal, st=d.storage;
    ALL_CHARTS.forEach(function(c){{try{{c.dispose();}}catch(e){{}}}});
    ALL_CHARTS=[];

    // Build pattern groups
    var tpat={{}}, spat={{}};
    th.forEach(function(t){{ if(!tpat[t.pattern]) tpat[t.pattern]=[]; tpat[t.pattern].push(t); }});
    st.forEach(function(s){{ if(!spat[s.pattern]) spat[s.pattern]=[]; spat[s.pattern].push(s); }});
    var THERMAL_ORDER = ['午间调峰机组','平稳/直线型','日内启机','日内停机','一充一放型(抽蓄)','纯充电型','零出力'];
    var tpatKeys = Object.keys(tpat).sort(function(a,b){{
        var ai=THERMAL_ORDER.indexOf(a), bi=THERMAL_ORDER.indexOf(b);
        if(ai>=0 && bi>=0) return ai-bi; if(ai>=0) return -1; if(bi>=0) return 1;
        return a.localeCompare(b);
    }});
    var spatKeys=Object.keys(spat).sort(function(a,b){{return spat[b].length-spat[a].length;}});

    document.getElementById('subtitle').textContent='数据源: shandong_px_provincial_prescheduling_results | 日期: '+d.date+' | 火电机组: '+th.length+' 台 | 储能机组: '+st.length+' 台';
    document.getElementById('v-thermal').textContent=th.length;
    document.getElementById('v-storage').textContent=st.length;
    if(th.length>0) document.getElementById('v-peak').textContent=Math.round(th[0].peak);
    document.getElementById('v-tpat').textContent=tpatKeys.length;
    document.getElementById('v-charge').textContent=Math.round(d.total_charge);
    document.getElementById('v-discharge').textContent=Math.round(d.total_discharge);
    document.getElementById('v-spat').textContent=spatKeys.length;

    // Thermal full table
    var ttb=document.getElementById('thermalTable'); ttb.innerHTML='';
    th.forEach(function(t,i){{
        ttb.innerHTML+='<tr><td>'+(i+1)+'</td><td class="name">'+shortName(t.name)+'</td><td>'+t.peak.toFixed(1)+'</td><td>'+t.mean.toFixed(1)+'</td><td>'+t.trough.toFixed(1)+'</td><td>'+t.cv.toFixed(1)+'</td><td class="pat">'+t.pattern+'</td></tr>';
    }});

    // Storage table
    var stb=document.getElementById('storageTable'); stb.innerHTML='';
    st.forEach(function(s,i){{
        stb.innerHTML+='<tr><td>'+(i+1)+'</td><td class="name">'+shortName(s.name)+'</td><td>'+s.charge_avg.toFixed(1)+'</td><td>'+s.charge_energy.toFixed(1)+'</td><td>'+s.discharge_avg.toFixed(1)+'</td><td>'+s.discharge_energy.toFixed(1)+'</td><td>'+s.efficiency.toFixed(1)+'%</td><td class="pat">'+s.pattern+'</td></tr>';
    }});

    // Thermal pie
    var tp=[], sp=[];
    tpatKeys.forEach(function(k){{tp.push({{name:k,value:tpat[k].length}});}});
    spatKeys.forEach(function(k){{sp.push({{name:k,value:spat[k].length}});}});
    makePie('c-tpie',tp); makePie('c-spie',sp);

    // Thermal TOP50 bar
    var t50n=th.slice(0,50).map(function(t){{return shortName(t.name);}}).reverse();
    var t50p=th.slice(0,50).map(function(t){{return t.peak;}}).reverse();
    var t50m=th.slice(0,50).map(function(t){{return t.mean;}}).reverse();
    makeBar('c-tbar',t50n,t50p,t50m,'峰值','均值','MW');

    // Storage charge/discharge bar
    var sn=st.map(function(s){{return shortName(s.name);}}).reverse();
    var sc=st.map(function(s){{return s.charge_energy;}}).reverse();
    var sd=st.map(function(s){{return s.discharge_energy;}}).reverse();
    makeBar2('c-sbar',sn,sc,sd,'充电电量','放电电量','MWh');

    // Thermal pattern divs & curves (zero-output → table)
    var tpDiv=document.getElementById('thermal-patterns');
    tpDiv.innerHTML='';
    var zeroThermal=null;
    tpatKeys.forEach(function(k){{
        if(k==='零出力'){{ zeroThermal=tpat[k]; return; }}
        var items=tpat[k], showN=Math.min(15,items.length);
        var cid='c-tpat-'+Math.abs(hash(k));
        var series=[];
        for(var j=0;j<showN;j++) series.push({{name:shortName(items[j].name),type:'line',data:items[j].vals,lineStyle:{{width:1.2}},symbol:'none',color:COLORS_64[j%64]}});
        tpDiv.innerHTML+='<div class="box"><h4>'+k+' ('+items.length+'台, 显示前'+showN+'台)</h4><div id="'+cid+'" class="chart"></div></div>';
        // Build chart after DOM is ready
        setTimeout(function(){{ makeLine(cid,series,40); }}, 10);
    }});
    // Zero-output thermal → table instead of chart
    if(zeroThermal && zeroThermal.length>0){{
        var zh='<div class="box"><h4>零出力 ('+zeroThermal.length+'台)</h4><div style="overflow-x:auto"><table><thead><tr><th>#</th><th>机组名称</th><th>峰值(MW)</th><th>均值(MW)</th></tr></thead><tbody>';
        zeroThermal.forEach(function(t,i){{ zh+='<tr><td>'+(i+1)+'</td><td class="name">'+shortName(t.name)+'</td><td>'+t.peak.toFixed(1)+'</td><td>'+t.mean.toFixed(1)+'</td></tr>'; }});
        zh+='</tbody></table></div></div>';
        tpDiv.innerHTML+=zh;
    }}

    // Storage pattern divs & curves (zero-output → list)
    var spDiv=document.getElementById('storage-patterns');
    spDiv.innerHTML='';
    var zeroStorage=null;
    spatKeys.forEach(function(k){{
        if(k==='零出力'){{ zeroStorage=spat[k]; return; }}
        var items=spat[k];
        var cid='c-spat-'+Math.abs(hash(k));
        var series=[];
        for(var j=0;j<items.length;j++) series.push({{name:shortName(items[j].name),type:'line',data:items[j].vals,lineStyle:{{width:1.2}},symbol:'none',color:COLORS_64[j%64]}});
        spDiv.innerHTML+='<div class="box"><h4>'+k+' ('+items.length+'台, 全部显示)</h4><div id="'+cid+'" class="chart"></div></div>';
        setTimeout(function(){{ makeLine(cid,series,40); }}, 10);
    }});
    // Zero-output storage → table instead of chart
    if(zeroStorage && zeroStorage.length>0){{
        var zs='<div class="box"><h4>零出力 ('+zeroStorage.length+'台)</h4><div style="overflow-x:auto"><table><thead><tr><th>#</th><th>机组名称</th></tr></thead><tbody>';
        zeroStorage.forEach(function(s,i){{ zs+='<tr><td>'+(i+1)+'</td><td class="name">'+shortName(s.name)+'</td></tr>'; }});
        zs+='</tbody></table></div></div>';
        spDiv.innerHTML+=zs;
    }}
}}

function loadDates() {{
    var sel=document.getElementById('dateSelect'); sel.innerHTML='';
    ALL_DATES.forEach(function(d){{
        var opt=document.createElement('option');
        opt.value=d.date;
        opt.textContent=d.date+' ('+d.units+'台)';
        if(d.date===currentDate) opt.selected=true;
        sel.appendChild(opt);
    }});
}}

function loadDate() {{
    var date=document.getElementById('dateSelect').value;
    if(!date||date===currentDate) return;
    currentDate=date;
    document.getElementById('loading').style.display='inline';
    var data=ALL_RESULTS[date];
    if(data) {{ renderAll(data); }}
    else {{ alert('日期 '+date+' 无数据'); }}
    document.getElementById('loading').style.display='none';
}}

loadDates();
renderAll(ALL_RESULTS[currentDate]);
</script>
</body>
</html>'''

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    import os
    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"Saved: {out_path} ({size_mb:.1f} MB)")


if __name__ == '__main__':
    import sys
    all_results_path = sys.argv[1] if len(sys.argv) > 1 else '_tmp_all_results.json'
    out_path = sys.argv[2] if len(sys.argv) > 2 else '06 DataMining/prescheduling_page.html'
    generate_page(all_results_path, out_path)