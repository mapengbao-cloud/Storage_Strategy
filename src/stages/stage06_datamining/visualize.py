"""Unified ECharts HTML template engine.

Extracts the HTML generation pattern repeated across all Stage 06 scripts
(db_viewer.py, extract_prices.py, generate_analysis_html.py,
gen_reserve_html.py, gen_powerflow_html.py, gen_sysbackup_html.py,
gen_thermal_backup_html.py, gen_prescheduling_html.py, gen_prescheduling_page.py).

Provides a single generate_echarts_html() function that all visualization
scripts can call instead of inline templating.

Style: White-background Windows-style (matching project convention).
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

# Color palette (from db_viewer.py)
DEFAULT_COLORS = [
    "#5470C6", "#91CC75", "#FAC858", "#EE6666", "#73C0DE",
    "#3BA272", "#FC8452", "#9A60B4", "#EA7CCC", "#48B9C7",
    "#E69D87", "#52A88C", "#D4626B", "#7F88E0", "#DDA93A",
]

# CSS template (white-background Windows style)
CSS_STYLE = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    background: #f5f6f8; color: #333;
}
.header {
    background: linear-gradient(135deg, #1a3a5c 0%, #2d6aa6 100%);
    color: #fff; padding: 16px 24px;
    display: flex; align-items: center; justify-content: space-between;
    box-shadow: 0 2px 8px rgba(0,0,0,.15);
}
.header h1 { font-size: 18px; font-weight: 500; }
.header .info { font-size: 12px; opacity: .75; }
.controls {
    background: #fff; margin: 12px 20px; padding: 14px 20px;
    border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.08);
    display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
}
.controls label {
    display: flex; align-items: center; gap: 6px;
    font-size: 13px; cursor: pointer; padding: 4px 12px;
    border-radius: 4px; background: #f0f2f5; transition: background .2s;
}
.controls label:hover { background: #e4e7ed; }
.controls label input[type="checkbox"] { accent-color: #5470C6; }
.chart-container {
    background: #fff; margin: 12px 20px; padding: 16px;
    border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.08);
}
.chart-box { width: 100%; height: 500px; }
.stats-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px; margin: 12px 20px;
}
.stat-card {
    background: #fafafa; border: 1px solid #e0e0e0;
    border-radius: 8px; padding: 16px; text-align: center;
}
.stat-card .label { font-size: 12px; color: #666; margin-bottom: 4px; }
.stat-card .value { font-size: 24px; font-weight: 600; color: #2c7be5; }
.stat-card .unit { font-size: 12px; color: #999; }
table {
    width: 100%; border-collapse: collapse; font-size: 13px;
}
th {
    background: #f5f5f5; color: #333; padding: 10px 12px;
    text-align: left; border-bottom: 2px solid #e0e0e0; font-weight: 500;
}
td {
    padding: 8px 12px; border-bottom: 1px solid #e0e0e0; color: #333;
}
tr:hover td { background: #f8f9fb; }
"""


# HTML page template
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
{css}
</style>
</head>
<body>
<div class="header">
    <h1>{title}</h1>
    <div class="info">Generated: {timestamp}</div>
</div>
{controls_html}
{stats_html}
{charts_html}
{table_html}
{scripts}
</body>
</html>
"""


def generate_echarts_html(
    output_path: str | Path,
    title: str,
    x_data: list[str],
    series: list[dict[str, Any]],
    stats: dict[str, str] | None = None,
    table_data: dict | None = None,
    controls: list[dict] | None = None,
    y_axis_name: str = "",
    extra_js: str = "",
) -> Path:
    """Generate a self-contained interactive ECharts HTML page.

    This is the unified entry point for ALL Stage 06 visualization.
    Replaces the inline HTML generation in 9 different scripts.

    Args:
        output_path: Where to write the HTML file.
        title: Page title and header text.
        x_data: X-axis labels (typically 96 time labels).
        series: List of series dicts, each with:
            - name: str (legend name)
            - data: list[float]
            - color: str (optional, hex color)
            - yAxisIndex: int (optional, 0 or 1 for dual-axis)
        stats: Optional {label: value} dict for stat cards.
        table_data: Optional {headers: [...], rows: [[...], ...]} for a data table.
        controls: Optional list of {name, color, checked} for series toggles.
        y_axis_name: Y-axis label.
        extra_js: Raw JavaScript injected after chart init (for custom behavior).

    Returns:
        Path to the generated HTML file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Build controls HTML ──
    controls_html = ""
    if controls and len(controls) > 1:
        items = []
        for i, ctrl in enumerate(controls):
            color = ctrl.get("color", DEFAULT_COLORS[i % len(DEFAULT_COLORS)])
            checked = "checked" if ctrl.get("checked", True) else ""
            items.append(
                f'<label style="color:{color}">'
                f'<input type="checkbox" data-series="{i}" {checked} '
                f'onchange="toggleSeries({i}, this.checked)">'
                f'<span style="display:inline-block;width:10px;height:10px;'
                f'border-radius:50%;background:{color};margin-right:4px"></span>'
                f'{ctrl["name"]}</label>'
            )
        controls_html = f'<div class="controls">{"".join(items)}</div>'

    # ── Build stats HTML ──
    stats_html = ""
    if stats:
        cards = []
        for label, value in stats.items():
            cards.append(
                f'<div class="stat-card">'
                f'<div class="label">{label}</div>'
                f'<div class="value">{value}</div>'
                f'</div>'
            )
        stats_html = f'<div class="stats-grid">{"".join(cards)}</div>'

    # ── Build chart HTML ──
    chart_id = "mainChart"
    charts_html = (
        f'<div class="chart-container">'
        f'<div class="chart-box" id="{chart_id}"></div>'
        f'</div>'
    )

    # ── Build table HTML ──
    table_html = ""
    if table_data:
        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])
        th_html = "".join(f"<th>{h}</th>" for h in headers)
        tr_html = ""
        for row in rows:
            tr_html += "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
        table_html = (
            f'<div class="chart-container">'
            f'<table><thead><tr>{th_html}</tr></thead>'
            f'<tbody>{tr_html}</tbody></table>'
            f'</div>'
        )

    # ── Build chart config ──
    chart_config = _build_chart_config(
        chart_id, x_data, series, controls, y_axis_name
    )

    # ── Scripts ──
    scripts = f"""
<script>
var chart = echarts.init(document.getElementById('{chart_id}'));
var option = {json.dumps(chart_config, ensure_ascii=False)};
chart.setOption(option);
window.addEventListener('resize', function() {{ chart.resize(); }});
function toggleSeries(idx, visible) {{
    if (idx < option.series.length) {{
        chart.setOption({{ series: [{{ id: idx, name: option.series[idx].name, showSymbol: visible }}] }});
    }}
}}
{extra_js}
</script>
"""

    # ── Assemble page ──
    html = PAGE_TEMPLATE.format(
        title=title,
        css=CSS_STYLE,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        controls_html=controls_html,
        stats_html=stats_html,
        charts_html=charts_html,
        table_html=table_html,
        scripts=scripts,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Saved: {output_path}")
    return output_path


def _build_chart_config(
    chart_id: str,
    x_data: list[str],
    series: list[dict],
    controls: list[dict] | None,
    y_axis_name: str,
) -> dict:
    """Build ECharts option dict from series configs."""

    has_dual_axis = any(s.get("yAxisIndex", 0) == 1 for s in series)

    y_axes = [
        {
            "type": "value",
            "name": y_axis_name or series[0].get("name", ""),
            "nameTextStyle": {"color": "#666"},
            "axisLabel": {"color": "#666", "formatter": "{value}"},
            "splitLine": {"lineStyle": {"color": "#eee"}},
        }
    ]
    if has_dual_axis:
        y_axes.append({
            "type": "value",
            "name": series[-1].get("name", "") if series else "",
            "nameTextStyle": {"color": "#666"},
            "axisLabel": {"color": "#666"},
            "splitLine": {"show": False},
        })

    echarts_series = []
    for i, s in enumerate(series):
        color = s.get("color", DEFAULT_COLORS[i % len(DEFAULT_COLORS)])
        echarts_series.append({
            "id": i,
            "name": s["name"],
            "type": "line",
            "data": s["data"],
            "smooth": True,
            "symbol": "none",
            "lineStyle": {"color": color, "width": 2},
            "itemStyle": {"color": color},
            "yAxisIndex": s.get("yAxisIndex", 0),
        })

    return {
        "backgroundColor": "#fff",
        "tooltip": {"trigger": "axis"},
        "legend": {
            "data": [s["name"] for s in series],
            "bottom": 0,
            "textStyle": {"color": "#333"},
        },
        "grid": {
            "left": 60, "right": 60 if has_dual_axis else 30,
            "top": 20, "bottom": 40,
        },
        "xAxis": {
            "type": "category",
            "data": x_data,
            "boundaryGap": False,
            "axisLabel": {"color": "#666", "interval": 7},
            "axisLine": {"lineStyle": {"color": "#ddd"}},
        },
        "yAxis": y_axes,
        "series": echarts_series,
    }


def generate_multi_chart_html(
    output_path: str | Path,
    title: str,
    charts: list[dict],
    stats: dict[str, str] | None = None,
    extra_css: str = "",
) -> Path:
    """Generate a page with MULTIPLE ECharts charts stacked vertically.

    Each chart dict:
        - id: str (unique DOM id)
        - x_data: list[str]
        - series: list[dict] (same as single chart)
        - y_axis_name: str (optional)
        - height: str (optional, default "450px")

    Args:
        output_path: Output HTML path.
        title: Page title.
        charts: List of chart config dicts.
        stats: Optional stat cards.
        extra_css: Additional CSS to inject.

    Returns:
        Path to the generated HTML.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Stats HTML
    stats_html = ""
    if stats:
        cards = []
        for label, value in stats.items():
            cards.append(
                f'<div class="stat-card">'
                f'<div class="label">{label}</div>'
                f'<div class="value">{value}</div>'
                f'</div>'
            )
        stats_html = f'<div class="stats-grid">{"".join(cards)}</div>'

    # Charts HTML
    charts_html = ""
    for ch in charts:
        ch_id = ch["id"]
        height = ch.get("height", "450px")
        charts_html += (
            f'<div class="chart-container">'
            f'<div class="chart-box" id="{ch_id}" style="height:{height}"></div>'
            f'</div>'
        )

    # Init scripts
    init_scripts = []
    for ch in charts:
        ch_id = ch["id"]
        config = _build_chart_config(
            ch_id, ch["x_data"], ch["series"], None,
            ch.get("y_axis_name", "")
        )
        config_json = json.dumps(config, ensure_ascii=False)
        init_scripts.append(
            f"var chart_{ch_id} = echarts.init(document.getElementById('{ch_id}'));"
            f"chart_{ch_id}.setOption({config_json});"
        )

    scripts_html = f"""
<script>
{chr(10).join(init_scripts)}
var allCharts = document.querySelectorAll('.chart-box');
window.addEventListener('resize', function() {{
    allCharts.forEach(function(el) {{
        var instance = echarts.getInstanceByDom(el);
        if (instance) instance.resize();
    }});
}});
</script>
"""

    html = PAGE_TEMPLATE.format(
        title=title,
        css=CSS_STYLE + extra_css,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        controls_html="",
        stats_html=stats_html,
        charts_html=charts_html,
        table_html="",
        scripts=scripts_html,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Saved: {output_path}")
    return output_path