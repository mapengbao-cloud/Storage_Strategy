"""按连续时序模板格式生成 7月17日-8月6日（最近三周）版本。"""
import json, os
from datetime import datetime
import pymysql

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

cur.execute("""SELECT DISTINCT date FROM shandong_px_dayahead_clearing_quantity_number
    WHERE date BETWEEN '2026-07-17' AND '2026-08-06' ORDER BY date""")
DATES = [str(r[0]) for r in cur.fetchall()]
print(f'有数据日期: {len(DATES)} 天')
TIMES = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0, 15, 30, 45)]

TH = []; ES_DR_VI = []; TH_NUM = []; DA_P = []; T = []; BS_AM = []; BS_PM = []
MEMBER_ID = 'b9e64e64a713458eba94c9af05c0a757'
for d in DATES:
    mmdd = d[5:]
    cur.execute("""SELECT thermal_clearing, thermal_number, independent_clearing, draw_clearing, virtual_clearing
        FROM shandong_px_dayahead_clearing_quantity_number WHERE date=%s ORDER BY time_point""", (d,))
    rows = cur.fetchall()
    # 竞价空间上午：shandong_px_spot_dayahead_load_info
    cur.execute("""SELECT dispatched_load_forecast, tie_line_load_forecast, wind_power_forecast,
        photovoltaic_power_forecast, nuclear_power_forecast, self_power_forecast
        FROM shandong_px_spot_dayahead_load_info WHERE date=%s ORDER BY time_order""", (d,))
    lr = cur.fetchall()
    bs_am_map = {}
    nuclear_map = {}
    self_map = {}
    for i, l in enumerate(lr):
        bs = (float(l[0] or 0) - float(l[1] or 0) - float(l[2] or 0)
              - float(l[3] or 0) - float(l[4] or 0) - float(l[5] or 0))
        bs_am_map[i] = round(bs, 2)
        nuclear_map[i] = float(l[4] or 0)
        self_map[i] = float(l[5] or 0)
    # 竞价空间下午：shandong_px_disclosure_information_load（核电/自备用上午表数据）
    cur.execute("""SELECT direct_load, tie_line_load, wind_power, photovoltaic
        FROM shandong_px_disclosure_information_load WHERE date=%s ORDER BY time_order""", (d,))
    lr2 = cur.fetchall()
    bs_pm_map = {}
    for i, l in enumerate(lr2):
        bs = (float(l[0] or 0) - float(l[1] or 0) - float(l[2] or 0)
              - float(l[3] or 0) - nuclear_map.get(i, 0) - self_map.get(i, 0))
        bs_pm_map[i] = round(bs, 2)
    for i, r in enumerate(rows):
        T.append(f'{mmdd}\n{TIMES[i]}')
        TH.append(round(float(r[0] or 0)*4, 2))           # 火电 MW
        TH_NUM.append(float(r[1] or 0))                   # 台数
        es = (float(r[2] or 0) + float(r[3] or 0) + float(r[4] or 0))*4  # 储能+抽蓄+虚拟 MW
        ES_DR_VI.append(round(es, 2))
        BS_AM.append(bs_am_map.get(i, 0))
        BS_PM.append(bs_pm_map.get(i, 0))
    cur.execute("""SELECT price FROM shandong_px_reliable_clearing_unit_data
        WHERE date=%s AND member_id=%s AND unit_name NOT LIKE '%%发电%%' AND unit_name NOT LIKE '%%用电%%'
        ORDER BY time_point""", (d, MEMBER_ID))
    rows = cur.fetchall()
    dp = [float(r[0] or 0) for r in rows] if rows else [0]*96
    DA_P.extend(dp)
cur.close(); conn.close()

n = len(T)
print(f'总点数: {n}')

# 严格按6月模板格式输出（仅数据更新为7月，标题/信息文字改7月）
html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>火电出清 & 台数 & 电价 | 7-8月连续</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333}}
.header{{background:#fff;padding:14px 24px;border-bottom:1px solid #d9d9d9;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600;margin-bottom:4px}}
.header .info{{font-size:11px;color:#888}}
.charts{{padding:8px 24px}}
.panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.panel .t{{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.panel .c{{width:100%;height:550px}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
</style>
</head>
<body>
<div class="header">
<h1>火电日前出清 & 开机台数 & 日前电价 | 7月17日-8月6日 连续时序</h1>
<div class="info">数据来源：天机库 · 火电出清=thermal_clearing×4(MW) · 储能+抽蓄+虚拟=independent+draw+virtual×4(MW) · 竞价空间上午=日前直调-联络线-风光-核电-自备 · 竞价空间下午=披露直调-联络线-风光-(上午核电+自备) · {len(DATES)}天×96点={n}点 · 支持缩放拖拽 · 0717-0806</div>
</div>
<div class="charts">
<div class="panel"><div class="t">火电出清(MW) + 储能抽蓄虚拟(MW) + 台数 + 日前电价(元/MWh) + 竞价空间上午 + 竞价空间下午</div><div class="c" id="c1"></div></div>
</div>
<div class="footer">润津储能 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<script>
var T={json.dumps(T, ensure_ascii=False)};
var TH={json.dumps(TH)};
var ES_DR_VI={json.dumps(ES_DR_VI)};
var TH_NUM={json.dumps(TH_NUM)};
var DA_P={json.dumps(DA_P)};
var BS_AM={json.dumps(BS_AM)};
var BS_PM={json.dumps(BS_PM)};
var g={{left:55,right:90,top:20,bottom:60}};
var ec={{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var ec2={{axisLabel:{{color:'#2c7be5',fontSize:10}},axisLine:{{lineStyle:{{color:'#2c7be5'}}}},splitLine:{{show:false}}}};
var ec3={{axisLabel:{{color:'#e67e22',fontSize:10}},axisLine:{{lineStyle:{{color:'#e67e22'}}}},splitLine:{{show:false}}}};
var ec4={{axisLabel:{{color:'#2ca02c',fontSize:10}},axisLine:{{lineStyle:{{color:'#2ca02c'}}}},splitLine:{{show:false}}}};
var ec5={{axisLabel:{{color:'#9467bd',fontSize:10}},axisLine:{{lineStyle:{{color:'#9467bd'}}}},splitLine:{{show:false}}}};
var el={{textStyle:{{color:'#666',fontSize:10}},top:3}};
c1=echarts.init(document.getElementById('c1'));
c1.setOption({{
grid:g,tooltip:{{trigger:'axis'}},
legend:Object.assign({{data:['火电出清','储能+抽蓄+虚拟','开机台数','日前电价','竞价空间上午','竞价空间下午']}},el),
dataZoom:[
  {{type:'slider',start:0,end:15,height:25,bottom:10}},
  {{type:'inside',start:0,end:15}}
],
xAxis:Object.assign({{type:'category',data:T,axisLabel:{{interval:95,fontSize:9,rotate:0}},nameTextStyle:{{fontSize:10}}}},ec),
yAxis:[
  Object.assign({{type:'value',name:'MW'}},ec),
  Object.assign({{type:'value',name:'台',min:60,max:130}},ec2),
  Object.assign({{type:'value',name:'元/MWh'}},ec3),
  Object.assign({{type:'value',name:'MW'}},ec4),
  Object.assign({{type:'value',name:'MW'}},ec5)
],
series:[
  {{name:'火电出清',type:'bar',data:TH,barWidth:3,itemStyle:{{color:'#d13438'}}}},
  {{name:'储能+抽蓄+虚拟',type:'bar',data:ES_DR_VI,barWidth:3,itemStyle:{{color:'#0078d4'}}}},
  {{name:'开机台数',type:'line',data:TH_NUM,smooth:false,step:'end',lineStyle:{{width:2,color:'#2c7be5'}},itemStyle:{{color:'#2c7be5'}},symbol:'none',yAxisIndex:1}},
  {{name:'日前电价',type:'line',data:DA_P,smooth:true,lineStyle:{{width:2,color:'#e67e22'}},itemStyle:{{color:'#e67e22'}},symbol:'none',yAxisIndex:2}},
  {{name:'竞价空间上午',type:'line',data:BS_AM,smooth:true,lineStyle:{{width:2,color:'#2ca02c'}},itemStyle:{{color:'#2ca02c'}},symbol:'none',yAxisIndex:3}},
  {{name:'竞价空间下午',type:'line',data:BS_PM,smooth:true,lineStyle:{{width:2,color:'#9467bd'}},itemStyle:{{color:'#9467bd'}},symbol:'none',yAxisIndex:4}}
]
}});
window.addEventListener('resize',function(){{c1.resize();}});
</script>
</body>
</html>'''

OUT = r'E:\DataWork\Storage_Strategy\output\火电出清_台数_电价_0717-0806_连续时序.html'
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Saved: {OUT} ({os.path.getsize(OUT):,} bytes)')
