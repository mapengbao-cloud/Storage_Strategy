"""
提取 5月18-6月3日 日前/实时 电价数据，生成交互式 ECharts HTML。
用法: python extract_prices.py
"""

import json
import openpyxl
from pathlib import Path

DATES = ["0518", "0519", "0520", "0521", "0522", "0523", "0524",
        "0525", "0526", "0527", "0528", "0529", "0530", "0531",
        "0601", "0602", "0603"]
DATE_LABELS = {
    "0518": "5月18日(周一)",
    "0519": "5月19日(周二)",
    "0520": "5月20日(周三)",
    "0521": "5月21日(周四)",
    "0522": "5月22日(周五)",
    "0523": "5月23日(周六)",
    "0524": "5月24日(周日)",
    "0525": "5月25日(周一)",
    "0526": "5月26日(周二)",
    "0527": "5月27日(周三)",
    "0528": "5月28日(周四)",
    "0529": "5月29日(周五)",
    "0530": "5月30日(周六)",
    "0531": "5月31日(周日)",
    "0601": "6月1日(周一)",
    "0602": "6月2日(周二)",
    "0603": "6月3日(周三)",
}

BASE = Path(__file__).resolve().parent.parent  # project root
DA_DIR = BASE / "02 Dayahead_Trading_Review" / "output"
RT_DIR = BASE / "03 Real-time_Trading_Review" / "output"
BS_DIR = BASE / "01 biddingSpace_analysis" / "output"
OUTPUT = BASE / "06 DataMining" / "电价对比_0518-0603.html"

SHEET_NAME = "报价及预中标"
PRICE_COL = 10  # column J (1-indexed)
TIME_COL = 8    # column H
DATA_ROW_START = 2
DATA_ROW_END = 97  # inclusive → 96 rows

# Bidding space: Sheet1, rows 3-6, columns B(2)~CS(97)
BS_SHEET = "Sheet1"
BS_ROWS = (3, 4, 5, 6)  # 直调负荷, 联络线受电, 风电总加, 光伏总加


def read_prices(filepath: Path) -> dict:
    """Read price data from a single file. Returns {time_labels, prices}."""
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
    ws = wb[SHEET_NAME]

    times = []
    prices = []
    for row in range(DATA_ROW_START, DATA_ROW_END + 1):
        cell_t = ws.cell(row=row, column=TIME_COL)
        cell_p = ws.cell(row=row, column=PRICE_COL)
        t_val = cell_t.value
        p_val = cell_p.value
        # format time label: "20250518 0015" → "00:15"
        if t_val and isinstance(t_val, str) and len(t_val) >= 13:
            hm = t_val.strip()[-4:]
            time_label = f"{hm[:2]}:{hm[2:]}"
        else:
            time_label = f"{row - 1:02d}"
        times.append(time_label)
        prices.append(round(float(p_val), 2) if p_val is not None else None)

    wb.close()
    return {"times": times, "prices": prices}


def read_bidding_space(filepath: Path) -> list:
    """Read bidding space from Sheet1 rows 3-6, compute R3-R4-R5-R6 for 96 cols."""
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
    ws = wb[BS_SHEET]
    values = []
    for col in range(2, 98):  # B=2 to CS=97
        r3 = float(ws.cell(row=3, column=col).value or 0)
        r4 = float(ws.cell(row=4, column=col).value or 0)
        r5 = float(ws.cell(row=5, column=col).value or 0)
        r6 = float(ws.cell(row=6, column=col).value or 0)
        values.append(round(r3 - r4 - r5 - r6, 1))
    wb.close()
    return values


def collect_all():
    """Collect day-ahead and real-time prices for all dates."""
    data = {}
    for d in DATES:
        da_file = DA_DIR / f"{d}-日前机组组合收益复盘.xlsx"
        rt_file = RT_DIR / f"{d}-实时机组组合收益复盘.xlsx"

        entry = {"times": None, "da": None, "rt": None, "bs": None, "bsa": None}

        if da_file.exists():
            da = read_prices(da_file)
            entry["times"] = da["times"]
            entry["da"] = da["prices"]
            print(f"  [DA] {da_file.name} OK ({len([p for p in da['prices'] if p])} pts)")
        else:
            print(f"  [DA] {da_file.name} MISSING")

        if rt_file.exists():
            rt = read_prices(rt_file)
            if entry["times"] is None:
                entry["times"] = rt["times"]
            entry["rt"] = rt["prices"]
            print(f"  [RT] {rt_file.name} OK ({len([p for p in rt['prices'] if p])} pts)")
        else:
            print(f"  [RT] {rt_file.name} MISSING")

        # Try (预测) suffix first, then fallback to no suffix (for locked files)
        bs_file = BS_DIR / f"{d}-竞价空间分析(预测).xlsx"
        if not bs_file.exists():
            bs_file = BS_DIR / f"{d}-竞价空间分析.xlsx"
        if bs_file.exists():
            entry["bs"] = read_bidding_space(bs_file)
            print(f"  [BS] {bs_file.name} OK (96 pts)")
        else:
            print(f"  [BS] {d}-竞价空间分析(预测).xlsx MISSING")

        # Actual bidding space
        bsa_file = BS_DIR / f"{d}-竞价空间分析(实际).xlsx"
        if bsa_file.exists():
            entry["bsa"] = read_bidding_space(bsa_file)
            print(f"  [BSA] {bsa_file.name} OK (96 pts)")
        else:
            print(f"  [BSA] {d}-竞价空间分析(实际).xlsx MISSING")

        data[d] = entry

    return data


def generate_html(data: dict):
    """Generate interactive HTML with ECharts."""
    # Prepare JSON data for JS
    dates_json = json.dumps(DATES)
    labels_json = json.dumps(DATE_LABELS)
    chart_data = {}
    for d in DATES:
        chart_data[d] = {
            "times": data[d]["times"] or [],
            "da": data[d]["da"] or [],
            "rt": data[d]["rt"] or [],
            "bs": data[d]["bs"] or [],
            "bsa": data[d]["bsa"] or [],
        }
    chart_json = json.dumps(chart_data, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>电价对比 5月18日-6月3日 (96点)</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #f0f2f5; color: #333; }}
  .header {{ background: linear-gradient(135deg, #1a73e8, #0d47a1); color: #fff;
             padding: 20px 32px; }}
  .header h1 {{ font-size: 22px; font-weight: 600; }}
  .header p {{ font-size: 13px; opacity: .85; margin-top: 4px; }}
  .controls {{ display: flex; align-items: center; gap: 10px; padding: 16px 32px;
               background: #fff; border-bottom: 1px solid #e0e0e0; flex-wrap: wrap; }}
  .controls label {{ font-size: 14px; font-weight: 500; color: #555; }}
  .date-btn {{ padding: 7px 16px; border: 1.5px solid #1a73e8; border-radius: 20px;
               background: #fff; color: #1a73e8; font-size: 13px; cursor: pointer;
               transition: all .2s; }}
  .date-btn:hover {{ background: #e8f0fe; }}
  .date-btn.active {{ background: #1a73e8; color: #fff; }}
  .toggle-group {{ margin-left: auto; display: flex; gap: 8px; }}
  .toggle-btn {{ padding: 6px 14px; border: 1.5px solid #ccc; border-radius: 16px;
                 background: #fff; font-size: 12px; cursor: pointer; transition: all .2s; }}
  .toggle-btn.da-active {{ border-color: #e53935; background: #ffebee; color: #e53935; }}
  .toggle-btn.rt-active {{ border-color: #1e88e5; background: #e3f2fd; color: #1e88e5; }}
  .toggle-btn.diff-active {{ border-color: #43a047; background: #e8f5e9; color: #43a047; }}
  .toggle-btn.bs-active {{ border-color: #ff9800; background: #fff3e0; color: #ff9800; }}
  .toggle-btn.bsa-active {{ border-color: #f57c00; background: #ffe0b2; color: #f57c00; }}
  #chart {{ width: 100%; height: calc(100vh - 160px); min-height: 480px; background: #fff; }}
  .stats-bar {{ display: flex; gap: 24px; padding: 10px 32px; background: #fff;
                border-bottom: 1px solid #eee; font-size: 13px; color: #666; flex-wrap: wrap; }}
  .stat-item span {{ font-weight: 600; }}
  .stat-da {{ color: #e53935; }}
  .stat-rt {{ color: #1e88e5; }}
  .stat-diff {{ color: #43a047; }}
  .stat-bs {{ color: #ff9800; }}
  .stat-bsa {{ color: #f57c00; }}
</style>
</head>
<body>
<div class="header">
  <h1>⚡ 储能电站电价对比 — 5月18日 ~ 6月3日</h1>
  <p>德州润津储能科技有限公司 · 日前 vs 实时 · 每日96点（15分钟间隔）</p>
</div>

<div class="controls">
  <label>选择日期：</label>
  <div id="dateButtons"></div>
  <div class="toggle-group">
    <button class="toggle-btn da-active" id="togDA" onclick="toggleSeries('da')">日前电价</button>
    <button class="toggle-btn rt-active" id="togRT" onclick="toggleSeries('rt')">实时电价</button>
    <button class="toggle-btn diff-active" id="togDiff" onclick="toggleSeries('diff')">价差(实时-日前)</button>
    <button class="toggle-btn bs-active" id="togBS" onclick="toggleSeries('bs')">竞价空间(预测)</button>
    <button class="toggle-btn bsa-active" id="togBSA" onclick="toggleSeries('bsa')">竞价空间(实际)</button>
  </div>
</div>

<div class="stats-bar" id="statsBar"></div>
<div id="chart"></div>

<script>
const DATES = {dates_json};
const LABELS = {labels_json};
const DATA = {chart_json};

let currentDate = DATES[0];
let showDA = true, showRT = true, showDiff = true, showBS = true, showBSA = true;
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
  if (s === 'da') {{ showDA = !showDA; document.getElementById('togDA').classList.toggle('da-active'); }}
  if (s === 'rt') {{ showRT = !showRT; document.getElementById('togRT').classList.toggle('rt-active'); }}
  if (s === 'diff') {{ showDiff = !showDiff; document.getElementById('togDiff').classList.toggle('diff-active'); }}
  if (s === 'bs') {{ showBS = !showBS; document.getElementById('togBS').classList.toggle('bs-active'); }}
  if (s === 'bsa') {{ showBSA = !showBSA; document.getElementById('togBSA').classList.toggle('bsa-active'); }}
  updateChart();
}}

function computeStats(arr) {{
  const valid = arr.filter(v => v !== null && v !== undefined);
  if (!valid.length) return {{ avg: '-', max: '-', min: '-' }};
  const avg = (valid.reduce((a, b) => a + b, 0) / valid.length).toFixed(2);
  return {{ avg, max: Math.max(...valid).toFixed(2), min: Math.min(...valid).toFixed(2) }};
}}

function computeBSStats(bs) {{
  const valid = bs.filter(v => v !== null && v !== undefined);
  if (!valid.length) return {{ avg: '-', max: '-', min: '-', diff: '-' }};
  const avg = (valid.reduce((a, b) => a + b, 0) / valid.length).toFixed(0);
  // 2-hour (8 pts) sliding window
  let maxAvg = -Infinity, minAvg = Infinity;
  for (let i = 0; i <= valid.length - 8; i++) {{
    const w = valid.slice(i, i + 8);
    const a = w.reduce((s, x) => s + x, 0) / 8;
    if (a > maxAvg) maxAvg = a;
    if (a < minAvg) minAvg = a;
  }}
  return {{ avg, max: Math.round(maxAvg), min: Math.round(minAvg), diff: Math.round(maxAvg - minAvg) }};
}}

function updateStats(da, rt, bs) {{
  const daS = computeStats(da);
  const rtS = computeStats(rt);
  const diffArr = da.map((v, i) => (v !== null && rt[i] !== null) ? +(rt[i] - v).toFixed(2) : null);
  const diffS = computeStats(diffArr);
  const bsS = computeBSStats(bs || []);
  document.getElementById('statsBar').innerHTML =
    `<div class="stat-item">日前均价: <span class="stat-da">${{daS.avg}}</span> 元/MWh</div>` +
    `<div class="stat-item">日前最高: <span class="stat-da">${{daS.max}}</span></div>` +
    `<div class="stat-item">日前最低: <span class="stat-da">${{daS.min}}</span></div>` +
    `<div class="stat-item" style="margin-left:16px">实时均价: <span class="stat-rt">${{rtS.avg}}</span> 元/MWh</div>` +
    `<div class="stat-item">实时最高: <span class="stat-rt">${{rtS.max}}</span></div>` +
    `<div class="stat-item">实时最低: <span class="stat-rt">${{rtS.min}}</span></div>` +
    `<div class="stat-item" style="margin-left:16px">价差均值: <span class="stat-diff">${{diffS.avg}}</span></div>` +
    `<div class="stat-item">最大正偏差: <span class="stat-diff">${{diffS.max}}</span></div>` +
    `<div class="stat-item">最大负偏差: <span class="stat-diff">${{diffS.min}}</span></div>` +
    `<div class="stat-item" style="margin-left:16px">竞价空间2h峰: <span class="stat-bs">${{bsS.max}}</span> MW</div>` +
    `<div class="stat-item">2h谷: <span class="stat-bs">${{bsS.min}}</span> MW</div>` +
    `<div class="stat-item">峰谷差: <span class="stat-bs">${{bsS.diff}}</span> MW</div>`;
}}

function updateChart() {{
  const d = DATA[currentDate];
  const times = d.times;
  const da = d.da;
  const rt = d.rt;
  const bs = d.bs;
  const bsa = d.bsa;

  // Compute diff
  const diff = da.map((v, i) =>
    (v !== null && rt && rt[i] !== null) ? +(rt[i] - v).toFixed(2) : null
  );

  updateStats(da, rt || [], bs || []);

  const series = [];
  if (showDA) {{
    series.push({{
      name: '日前电价',
      type: 'line',
      data: da,
      smooth: true,
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: {{ width: 2.5, color: '#e53935' }},
      itemStyle: {{ color: '#e53935' }},
      emphasis: {{ focus: 'series' }},
    }});
  }}
  if (showRT) {{
    series.push({{
      name: '实时电价',
      type: 'line',
      data: rt,
      smooth: true,
      symbol: 'diamond',
      symbolSize: 4,
      lineStyle: {{ width: 2.5, color: '#1e88e5' }},
      itemStyle: {{ color: '#1e88e5' }},
      emphasis: {{ focus: 'series' }},
    }});
  }}
  if (showDiff) {{
    series.push({{
      name: '价差(实时-日前)',
      type: 'bar',
      data: diff,
      yAxisIndex: 1,
      barMaxWidth: 8,
      itemStyle: {{
        color: function(params) {{
          return params.value >= 0 ? 'rgba(67,160,71,0.6)' : 'rgba(255,152,0,0.6)';
        }}
      }},
      emphasis: {{ focus: 'series' }},
    }});
  }}
  if (showBS && bs && bs.length) {{
    series.push({{
      name: '竞价空间(预测)',
      type: 'line',
      data: bs,
      yAxisIndex: 2,
      smooth: true,
      symbol: 'none',
      lineStyle: {{ width: 2, color: '#ff9800', type: 'dashed' }},
      itemStyle: {{ color: '#ff9800' }},
      emphasis: {{ focus: 'series' }},
    }});
  }}
  if (showBSA && bsa && bsa.length) {{
    series.push({{
      name: '竞价空间(实际)',
      type: 'line',
      data: bsa,
      yAxisIndex: 2,
      smooth: true,
      symbol: 'none',
      lineStyle: {{ width: 2, color: '#f57c00' }},
      itemStyle: {{ color: '#f57c00' }},
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
        let tip = '<b>' + params[0].axisValue + '</b><br/>';
        params.forEach(p => {{
          if (p.value !== null && p.value !== undefined) {{
            let unit = ' 元/MWh';
            if (p.seriesName.includes('价差')) unit = '';
            if (p.seriesName.includes('竞价空间')) unit = ' MW';
            tip += p.marker + ' ' + p.seriesName + ': <b>' + p.value + '</b>' + unit + '<br/>';
          }}
        }});
        return tip;
      }}
    }},
    legend: {{
      top: 8,
      textStyle: {{ fontSize: 12 }},
    }},
    grid: {{
      left: 60, right: 80, top: 50, bottom: 60,
    }},
    xAxis: {{
      type: 'category',
      data: times,
      axisLabel: {{
        fontSize: 10,
        interval: function(index) {{
          // Show every 4th label (hourly)
          return index % 4 === 0;
        }},
        rotate: 45,
      }},
      axisTick: {{ alignWithLabel: true }},
      splitLine: {{ show: false }},
    }},
    yAxis: [
      {{
        type: 'value',
        name: '电价 (元/MWh)',
        nameTextStyle: {{ fontSize: 12 }},
        axisLabel: {{ fontSize: 11 }},
        splitLine: {{ lineStyle: {{ type: 'dashed', color: '#eee' }} }},
      }},
      {{
        type: 'value',
        name: '价差 (元/MWh)',
        nameTextStyle: {{ fontSize: 12 }},
        axisLabel: {{ fontSize: 11 }},
        splitLine: {{ show: false }},
      }},
      {{
        type: 'value',
        name: '竞价空间 (MW)',
        nameTextStyle: {{ fontSize: 12, color: '#ff9800' }},
        axisLabel: {{ fontSize: 11, color: '#ff9800' }},
        splitLine: {{ show: false }},
        position: 'right',
        offset: 0,
      }},
    ],
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
    OUTPUT.write_text(html, encoding='utf-8')
    print(f"\n[OK] HTML generated: {OUTPUT}")


if __name__ == "__main__":
    print("=== 提取电价数据 (5月18-6月3日) ===\n")
    data = collect_all()
    print("\n=== 生成 HTML ===")
    generate_html(data)
