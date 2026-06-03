"""
可视化 shandong_px_intraday_clearing_plan_result 最近一周数据。
生成 ECharts HTML，每日可选，96点为横轴。
"""
import pymysql
import json
from decimal import Decimal
from pathlib import Path
from datetime import datetime

DB_CONFIG = {
    "host": "rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com",
    "port": 3306,
    "user": "pengyiqiang",
    "password": "pengyiqiang123",
    "database": "tianrun_new",
    "connect_timeout": 15,
    "cursorclass": pymysql.cursors.DictCursor,
}

OUTPUT = Path(__file__).resolve().parent / "日内出清计划_近一周.html"

TIMES = []
for i in range(96):
    h = i // 4
    m = (i % 4) * 15
    TIMES.append(f"{h:02d}:{m:02d}")


def fetch_data():
    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT date, time_point, cq_type, power
        FROM shandong_px_intraday_clearing_plan_result
        WHERE date >= '2026-05-23'
        ORDER BY date, time_point, cq_type
    """)
    rows = cur.fetchall()
    conn.close()

    # Organize: {date_str: {cq_type: [val_0, ..., val_95]}}
    data = {}
    for r in rows:
        d = str(r["date"])
        ct = r["cq_type"]
        tp = r["time_point"]  # "00:00"
        pwr = float(r["power"]) if r["power"] is not None else None

        if d not in data:
            data[d] = {"1": [None] * 96, "2": [None] * 96}
        idx = TIMES.index(tp) if tp in TIMES else -1
        if idx >= 0:
            data[d][ct][idx] = round(pwr, 2) if pwr is not None else None
    return data


def generate_html(data):
    dates = sorted(data.keys())
    date_labels = {
        dates[0]: "5月23日(周六)",
        dates[1]: "5月24日(周日)",
        dates[2]: "5月25日(周一)",
        dates[3]: "5月26日(周二)",
        dates[4]: "5月27日(周三)",
        dates[5]: "5月28日(周四)",
        dates[6]: "5月29日(周五)",
    }

    chart_data = {}
    for d in dates:
        chart_data[d] = {
            "cq1": data[d]["1"],
            "cq2": data[d]["2"],
        }

    dates_json = json.dumps(dates)
    labels_json = json.dumps(date_labels)
    chart_json = json.dumps(chart_data)
    times_json = json.dumps(TIMES)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>苏留润津 日内出清计划 近一周</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #f0f2f5; color: #333; }}
  .header {{ background: linear-gradient(135deg, #1565c0, #0277bd); color: #fff;
             padding: 20px 32px; }}
  .header h1 {{ font-size: 22px; font-weight: 600; }}
  .header p {{ font-size: 13px; opacity: .85; margin-top: 4px; }}
  .controls {{ display: flex; align-items: center; gap: 10px; padding: 16px 32px;
               background: #fff; border-bottom: 1px solid #e0e0e0; flex-wrap: wrap; }}
  .controls label {{ font-size: 14px; font-weight: 500; color: #555; }}
  .date-btn {{ padding: 7px 16px; border: 1.5px solid #1565c0; border-radius: 20px;
               background: #fff; color: #1565c0; font-size: 13px; cursor: pointer;
               transition: all .2s; }}
  .date-btn:hover {{ background: #e3f2fd; }}
  .date-btn.active {{ background: #1565c0; color: #fff; }}
  .toggle-group {{ margin-left: auto; display: flex; gap: 8px; }}
  .toggle-btn {{ padding: 6px 14px; border: 1.5px solid #ccc; border-radius: 16px;
                 background: #fff; font-size: 12px; cursor: pointer; transition: all .2s; }}
  .toggle-btn.cq1-active {{ border-color: #e53935; background: #ffebee; color: #e53935; }}
  .toggle-btn.cq2-active {{ border-color: #1e88e5; background: #e3f2fd; color: #1e88e5; }}
  #chart {{ width: 100%; height: calc(100vh - 160px); min-height: 480px; background: #fff; }}
  .stats-bar {{ display: flex; gap: 24px; padding: 10px 32px; background: #fff;
                border-bottom: 1px solid #eee; font-size: 13px; color: #666; flex-wrap: wrap; }}
  .stat-item span {{ font-weight: 600; }}
  .stat-cq1 {{ color: #e53935; }}
  .stat-cq2 {{ color: #1e88e5; }}
  .zero-line {{ color: #999; font-size: 11px; }}
</style>
</head>
<body>
<div class="header">
  <h1>苏留润津独立储能电站 — 日内出清计划</h1>
  <p>数据来源: shandong_px_intraday_clearing_plan_result · 2026年5月23日~29日 · 每日96点（15分钟间隔）</p>
</div>

<div class="controls">
  <label>选择日期：</label>
  <div id="dateButtons"></div>
  <div class="toggle-group">
    <button class="toggle-btn cq1-active" id="togCQ1" onclick="toggleSeries('cq1')">日内第一批(cq_type=1)</button>
    <button class="toggle-btn cq2-active" id="togCQ2" onclick="toggleSeries('cq2')">日内第二批(cq_type=2)</button>
  </div>
</div>

<div class="stats-bar" id="statsBar"></div>
<div id="chart"></div>

<script>
const DATES = {dates_json};
const LABELS = {labels_json};
const DATA = {chart_json};
const TIMES = {times_json};

let currentDate = DATES[0];
let showCQ1 = true, showCQ2 = true;
const chart = echarts.init(document.getElementById('chart'));

// Build date buttons
const btnContainer = document.getElementById('dateButtons');
DATES.forEach(d => {{
  const btn = document.createElement('button');
  btn.className = 'date-btn' + (d === currentDate ? ' active' : '');
  btn.textContent = LABELS[d];
  btn.onclick = () => selectDate(d);
  btnContainer.appendChild(btn);
}});

function selectDate(d) {{
  currentDate = d;
  document.querySelectorAll('.date-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  updateChart();
}}

function toggleSeries(s) {{
  if (s === 'cq1') {{ showCQ1 = !showCQ1; document.getElementById('togCQ1').classList.toggle('cq1-active'); }}
  if (s === 'cq2') {{ showCQ2 = !showCQ2; document.getElementById('togCQ2').classList.toggle('cq2-active'); }}
  updateChart();
}}

function computeStats(arr) {{
  const valid = arr.filter(v => v !== null);
  if (!valid.length) return {{ avg: '-', max: '-', min: '-', pos_count: 0, neg_count: 0 }};
  const pos = valid.filter(v => v > 0);
  const neg = valid.filter(v => v < 0);
  const avg = (valid.reduce((a, b) => a + b, 0) / valid.length).toFixed(2);
  const mx = Math.max(...valid).toFixed(2);
  const mn = Math.min(...valid).toFixed(2);
  return {{ avg, max: mx, min: mn, pos_count: pos.length, neg_count: neg.length }};
}}

function updateStats(cq1, cq2) {{
  const s1 = computeStats(cq1);
  const s2 = computeStats(cq2);
  let html = '';
  if (showCQ1) {{
    html += `<div class="stat-item">日内第一批 有效点数: <span class="stat-cq1">${{s1.pos_count + s1.neg_count}}</span></div>`;
    html += `<div class="stat-item">正(放电): <span class="stat-cq1">${{s1.pos_count}}</span>点</div>`;
    html += `<div class="stat-item">负(充电): <span class="stat-cq1">${{s1.neg_count}}</span>点</div>`;
    html += `<div class="stat-item">最大: <span class="stat-cq1">${{s1.max}}</span> MW</div>`;
    html += `<div class="stat-item">最小: <span class="stat-cq1">${{s1.min}}</span> MW</div>`;
  }}
  if (showCQ2) {{
    html += `<div class="stat-item" style="margin-left:16px">日内第二批 有效点数: <span class="stat-cq2">${{s2.pos_count + s2.neg_count}}</span></div>`;
    html += `<div class="stat-item">正(放电): <span class="stat-cq2">${{s2.pos_count}}</span>点</div>`;
    html += `<div class="stat-item">负(充电): <span class="stat-cq2">${{s2.neg_count}}</span>点</div>`;
    html += `<div class="stat-item">最大: <span class="stat-cq2">${{s2.max}}</span> MW</div>`;
    html += `<div class="stat-item">最小: <span class="stat-cq2">${{s2.min}}</span> MW</div>`;
  }}
  document.getElementById('statsBar').innerHTML = html;
}}

function updateChart() {{
  const d = DATA[currentDate];
  const cq1 = d.cq1;
  const cq2 = d.cq2;

  updateStats(cq1, cq2);

  const series = [];
  if (showCQ1) {{
    series.push({{
      name: '日内第一批',
      type: 'bar',
      data: cq1.map((v, i) => [i, v]),
      barMaxWidth: 9,
      itemStyle: {{
        color: function(params) {{
          if (params.value[1] === null) return 'transparent';
          return params.value[1] >= 0 ? 'rgba(229,57,53,0.75)' : 'rgba(244,67,54,0.35)';
        }}
      }},
      emphasis: {{ focus: 'series' }},
    }});
  }}
  if (showCQ2) {{
    series.push({{
      name: '日内第二批',
      type: 'bar',
      data: cq2.map((v, i) => [i, v]),
      barMaxWidth: 9,
      itemStyle: {{
        color: function(params) {{
          if (params.value[1] === null) return 'transparent';
          return params.value[1] >= 0 ? 'rgba(30,136,229,0.75)' : 'rgba(33,150,243,0.35)';
        }}
      }},
      emphasis: {{ focus: 'series' }},
    }});
  }}

  const option = {{
    tooltip: {{
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#ddd',
      textStyle: {{ color: '#333', fontSize: 12 }},
      formatter: function(params) {{
        const idx = params[0].axisValue;
        const time = TIMES[idx];
        let tip = '<b>' + time + '</b><br/>';
        params.forEach(p => {{
          if (p.value[1] !== null) {{
            tip += p.marker + ' ' + p.seriesName + ': <b>' + p.value[1].toFixed(2) + '</b> MW<br/>';
          }}
        }});
        if (params.every(p => p.value[1] === null)) {{
          tip += '<span style="color:#999">无计划数据</span>';
        }}
        return tip;
      }}
    }},
    legend: {{ show: false }},
    grid: {{ left: 60, right: 40, top: 30, bottom: 60 }},
    xAxis: {{
      type: 'category',
      data: TIMES,
      axisLabel: {{
        fontSize: 10,
        interval: 3,
        rotate: 45,
      }},
      axisTick: {{ alignWithLabel: true }},
    }},
    yAxis: {{
      type: 'value',
      name: '功率 (MW)',
      nameTextStyle: {{ fontSize: 12 }},
      axisLabel: {{ fontSize: 11 }},
      splitLine: {{ lineStyle: {{ type: 'dashed', color: '#eee' }} }},
    }},
    dataZoom: [
      {{ type: 'inside', start: 0, end: 100 }},
      {{ type: 'slider', start: 0, end: 100, height: 20, bottom: 8 }},
    ],
    series: series,
  }};

  chart.setOption(option, true);
}}

updateChart();
window.addEventListener('resize', () => chart.resize());
</script>
</body>
</html>"""

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"[OK] HTML generated: {OUTPUT}")


if __name__ == "__main__":
    print("=== Fetching intraday clearing plan data (2026-05-23 ~ 2026-05-29) ===\n")
    data = fetch_data()
    for d in sorted(data.keys()):
        cq1_valid = sum(1 for v in data[d]["1"] if v is not None)
        cq2_valid = sum(1 for v in data[d]["2"] if v is not None)
        print(f"  {d}: cq1={cq1_valid} valid pts, cq2={cq2_valid} valid pts")
    print()
    generate_html(data)