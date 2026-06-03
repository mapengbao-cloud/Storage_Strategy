"""
数据查看工具 - 从数据库读取时间序列数据，生成可交互的折线图 HTML 页面。
支持多系列不同颜色显示，勾选框控制显示/隐藏。
"""

import pymysql
import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path

# ==================== 配置 ====================
DB_CONFIG = {
    "host": os.getenv("DB_TIANJI_HOST", "rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com"),
    "port": int(os.getenv("DB_TIANJI_PORT", "3306")),
    "user": os.getenv("DB_TIANJI_USER", "pengyiqiang"),
    "password": os.getenv("DB_TIANJI_PASSWORD", "pengyiqiang123"),
    "database": os.getenv("DB_TIANJI_DATABASE", "tianrun_new"),
}

# 预设颜色方案
COLORS = [
    "#5470C6", "#91CC75", "#FAC858", "#EE6666", "#73C0DE",
    "#3BA272", "#FC8452", "#9A60B4", "#EA7CCC", "#48B9C7",
    "#E69D87", "#52A88C", "#D4626B", "#7F88E0", "#DDA93A",
]

# ==================== HTML 模板 ====================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #f5f6f8; }}
.header {{
    background: linear-gradient(135deg, #1a3a5c 0%, #2d6aa6 100%);
    color: #fff; padding: 16px 24px; display: flex; align-items: center;
    justify-content: space-between; box-shadow: 0 2px 8px rgba(0,0,0,.15);
}}
.header h1 {{ font-size: 18px; font-weight: 500; }}
.header .info {{ font-size: 12px; opacity: .75; }}

.controls {{
    background: #fff; margin: 12px 20px; padding: 14px 20px;
    border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.08);
    display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
}}
.controls label {{ display: flex; align-items: center; gap: 6px;
    font-size: 13px; cursor: pointer; padding: 4px 12px;
    border-radius: 4px; background: #f0f2f5; transition: background .2s;
}}
.controls label:hover {{ background: #e4e7ed; }}
.controls label input[type="checkbox"] {{ accent-color: #5470C6; }}
.controls .btn-group {{ margin-left: auto; display: flex; gap: 8px; }}
.controls button {{
    padding: 6px 16px; border: 1px solid #d0d5dd; border-radius: 6px;
    background: #fff; cursor: pointer; font-size: 13px; transition: all .2s;
}}
.controls button:hover {{ background: #f0f2f5; border-color: #5470C6; color: #5470C6; }}
.controls button.primary {{ background: #5470C6; color: #fff; border-color: #5470C6; }}
.controls button.primary:hover {{ opacity: .85; }}

.chart-wrap {{
    margin: 0 20px 12px; background: #fff; border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,.08); padding: 10px;
}}
.chart {{ width: 100%; height: 520px; }}

.data-table {{
    margin: 0 20px 20px; background: #fff; border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,.08); overflow: hidden;
}}
.data-table summary {{
    padding: 12px 20px; cursor: pointer; font-size: 14px; color: #555;
    border-bottom: 1px solid #eee; user-select: none;
}}
.data-table table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
.data-table thead {{ position: sticky; top: 0; }}
.data-table th {{
    background: #f8f9fb; padding: 8px 12px; text-align: left;
    border-bottom: 2px solid #e0e0e0; white-space: nowrap; font-weight: 500; color: #555;
}}
.data-table td {{ padding: 7px 12px; border-bottom: 1px solid #f0f0f0; white-space: nowrap; }}
.data-table tr:hover td {{ background: #f5f8ff; }}
.data-table .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.data-table-wrap {{ max-height: 400px; overflow-y: auto; }}

.tooltip-row {{ display: flex; gap: 20px; align-items: center; }}
.tooltip-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
</style>
</head>
<body>
<div class="header">
    <div>
        <h1>{title}</h1>
        <div class="info">数据来源: {source} | 更新时间: {update_time}</div>
    </div>
</div>

<div class="controls">
    <span style="font-size:13px;color:#888;font-weight:500;">系列筛选:</span>
    {checkboxes}
    <div class="btn-group">
        <button onclick="selectAll()">全选</button>
        <button onclick="deselectAll()">全不选</button>
        <button class="primary" onclick="resetZoom()">重置缩放</button>
    </div>
</div>

<div class="chart-wrap">
    <div id="chart" class="chart"></div>
</div>

<div class="data-table-wrap">
<details class="data-table" open>
    <summary>数据明细 ({row_count} 条)</summary>
    <div class="data-table-wrap">
        <table>
            <thead>{table_head}</thead>
            <tbody>{table_body}</tbody>
        </table>
    </div>
</details>
</div>

<script>
const RAW_DATA = {raw_data};
const SERIES = {series};
const COLORS = {colors};

const chart = echarts.init(document.getElementById('chart'));

function buildOption() {{
    const checked = new Set(
        Array.from(document.querySelectorAll('.series-cb:checked')).map(cb => cb.value)
    );
    const activeSeries = SERIES.filter(s => checked.has(s.name));
    const datasets = [];

    activeSeries.forEach(s => {{
        datasets.push({{
            name: s.name,
            type: 'line',
            data: RAW_DATA.map(row => [row[s.x_field], row[s.y_field]]),
            smooth: true,
            symbol: 'none',
            lineStyle: {{ width: 2, color: s.color }},
            itemStyle: {{ color: s.color }},
            emphasis: {{ focus: 'series' }},
        }});
    }});

    return {{
        tooltip: {{
            trigger: 'axis',
            axisPointer: {{ type: 'cross' }},
        }},
        legend: {{
            type: 'scroll', bottom: 0, data: activeSeries.map(s => s.name),
            textStyle: {{ fontSize: 12 }},
        }},
        grid: {{ left: 70, right: 60, top: 30, bottom: 40 }},
        xAxis: {{
            type: 'time', axisLabel: {{ fontSize: 11 }},
            splitLine: {{ show: false }},
        }},
        yAxis: {{
            type: 'value', axisLabel: {{ fontSize: 11 }},
            splitLine: {{ lineStyle: {{ color: '#eee', type: 'dashed' }} }},
        }},
        dataZoom: [
            {{ type: 'inside', start: 0, end: 100 }},
            {{ type: 'slider', start: 0, end: 100, height: 24, bottom: 28 }},
        ],
        series: datasets,
    }};
}}

function render() {{
    chart.setOption(buildOption(), true);
}}

document.querySelectorAll('.series-cb').forEach(cb => cb.addEventListener('change', render));

function selectAll()   {{ document.querySelectorAll('.series-cb').forEach(cb => cb.checked = true);  render(); }}
function deselectAll() {{ document.querySelectorAll('.series-cb').forEach(cb => cb.checked = false); render(); }}
function resetZoom()   {{ chart.dispatchAction({{ type: 'dataZoom', start: 0, end: 100 }}); }}

window.addEventListener('resize', () => chart.resize());
render();
</script>
</body>
</html>
"""


from decimal import Decimal

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


import re

_DT_PAT = re.compile(r'^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}$')

def _fix_value(v):
    """将 MySQL 返回的字符串类型 datetime 转为 JS 可解析的 ISO 格式"""
    if isinstance(v, str) and _DT_PAT.match(v):
        return v.replace(' ', 'T')
    if isinstance(v, Decimal):
        return float(v)
    return v

def _query_data(sql: str) -> list[dict]:
    """执行查询，返回字典列表"""
    conn = pymysql.connect(**DB_CONFIG, connect_timeout=10,
                           cursorclass=pymysql.cursors.DictCursor)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        for row in rows:
            for k, v in row.items():
                row[k] = _fix_value(v)
        return rows
    finally:
        conn.close()


def generate_html(
    sql: str,
    output_path: str,
    title: str = "数据查看",
    x_field: str = None,
    y_fields: list[str] = None,
    series_names: dict = None,
    max_rows: int = 50000,
):
    """
    从 SQL 查询数据，生成交互式 HTML 折线图。

    参数:
        sql:         查询 SQL
        output_path: 输出 HTML 文件路径
        title:       页面标题
        x_field:     X 轴字段名（必须是时间类型），不指定则取第一个日期/时间字段
        y_fields:    Y 轴字段列表（多个=多条线），不指定则取所有数值字段
        series_names: 字段名 -> 显示名的映射，如 {'fore_price': '预测价', 'org_price': '实际价'}
        max_rows:    最大行数限制
    """
    rows = _query_data(sql)

    if not rows:
        print("查询结果为空！")
        return

    # 超过限制时截断并提示
    if len(rows) > max_rows:
        rows = rows[:max_rows]
        print(f"数据已截断至 {max_rows} 行")

    all_fields = list(rows[0].keys())

    # 自动推断 X 轴字段
    if x_field is None:
        for f in all_fields:
            if f.lower() in ("datetime", "date", "time", "ts", "timestamp"):
                x_field = f
                break
        if x_field is None:
            for f in all_fields:
                if isinstance(rows[0][f], (datetime, date)):
                    x_field = f
                    break
        if x_field is None:
            x_field = all_fields[0]  # fallback

    # 自动推断 Y 轴字段（数值类）
    if y_fields is None:
        y_fields = []
        for f in all_fields:
            if f == x_field:
                continue
            val = rows[0][f]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                y_fields.append(f)
        if not y_fields:
            y_fields = [all_fields[1]] if len(all_fields) > 1 else [all_fields[0]]

    # 系列配置
    series = []
    for i, yf in enumerate(y_fields):
        name = series_names.get(yf, yf) if series_names else yf
        series.append({
            "name": name,
            "x_field": x_field,
            "y_field": yf,
            "color": COLORS[i % len(COLORS)],
        })

    # 表格
    num_fields = set(y_fields) | {x_field}
    all_numeric = all(isinstance(rows[0][f], (int, float, type(None))) for f in y_fields)

    th_parts = []
    for f in all_fields:
        cls = ' class="num"' if (f in num_fields and all_numeric) else ''
        th_parts.append(f"<th{cls}>{f}</th>")

    tb_parts = []
    for row in rows:
        tds = []
        for f in all_fields:
            v = row[f]
            if v is None:
                v = ""
            elif isinstance(v, (datetime, date)):
                v = v.isoformat() if hasattr(v, 'isoformat') else str(v)
            cls = ' class="num"' if f in num_fields else ''
            tds.append(f"<td{cls}>{v}</td>")
        tb_parts.append(f"<tr>{''.join(tds)}</tr>")

    # 生成勾选框
    cb_parts = []
    for s in series:
        color = s["color"]
        cb_parts.append(
            f'<label>'
            f'<input type="checkbox" class="series-cb" value="{s["name"]}" checked>'
            f'<span style="display:inline-block;width:12px;height:12px;'
            f'border-radius:50%;background:{color};"></span>'
            f'{s["name"]}'
            f'</label>'
        )

    html = HTML_TEMPLATE.format(
        title=title,
        source=f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}",
        update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        checkboxes="\n    ".join(cb_parts),
        row_count=len(rows),
        table_head="".join(th_parts),
        table_body="".join(tb_parts),
        raw_data=json.dumps(rows, ensure_ascii=False, cls=DateTimeEncoder),
        series=json.dumps(series, ensure_ascii=False),
        colors=json.dumps(COLORS, ensure_ascii=False),
    )

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"已生成: {output_path} ({len(rows)} 行, {len(series)} 个系列)")
    return output_path


# ==================== 快捷查询预设 ====================
PRESET_QUERIES = {
    "clearing_price": {
        "sql": """
            SELECT
                ADDTIME(CONCAT(date, ' 00:00:00'), SEC_TO_TIME((time_order-1)*900)) AS datetime,
                org_price, fore_price, fore_price_adjusted
            FROM algorithm_clearing_price_forecast
            WHERE province_id = 14 AND date >= '2026-05-01'
            ORDER BY datetime
            LIMIT 10000
        """,
        "title": "出清价格预测",
        "x_field": "datetime",
        "y_fields": ["org_price", "fore_price", "fore_price_adjusted"],
        "series_names": {
            "org_price": "实际价格",
            "fore_price": "预测价格",
            "fore_price_adjusted": "调整后预测价",
        },
    },
    "supply_demand": {
        "sql": """
            SELECT datetime, fore_value, fore_type, area_type
            FROM all_province_supply_and_demand_forecast
            ORDER BY datetime DESC
            LIMIT 5000
        """,
        "title": "供需预测",
        "x_field": "datetime",
        "y_fields": ["fore_value"],
        "series_names": {"fore_value": "预测值"},
    },
    "boundary": {
        "sql": """
            SELECT date, hour, data, data_type, area_type
            FROM all_province_boundary_data_mtl_forecast
            ORDER BY date DESC, hour
            LIMIT 5000
        """,
        "title": "边界数据预测",
        "x_field": "date",
        "y_fields": ["data"],
        "series_names": {"data": "边界数据"},
    },
}


def run_preset(name: str, output_dir: str = "."):
    """运行预设查询"""
    preset = PRESET_QUERIES[name]
    out = os.path.join(output_dir, f"view_{name}.html")
    generate_html(
        sql=preset["sql"],
        output_path=out,
        title=preset["title"],
        x_field=preset.get("x_field"),
        y_fields=preset.get("y_fields"),
        series_names=preset.get("series_names"),
    )


def run_custom(sql: str, title: str = "自定义查询", output: str = "view_custom.html",
                x_field: str = None, y_fields: list[str] = None,
                series_names: dict = None):
    """运行自定义 SQL 查询"""
    generate_html(
        sql=sql,
        output_path=output,
        title=title,
        x_field=x_field,
        y_fields=y_fields,
        series_names=series_names,
    )


# ==================== CLI ====================
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in PRESET_QUERIES:
            run_preset(cmd)
        elif cmd == "custom":
            sql = sys.argv[2] if len(sys.argv) > 2 else input("请输入SQL: ")
            title = sys.argv[3] if len(sys.argv) > 3 else "自定义查询"
            out = sys.argv[4] if len(sys.argv) > 4 else "view_custom.html"
            run_custom(sql, title, out)
        elif cmd == "list":
            print("预设查询:")
            for k, v in PRESET_QUERIES.items():
                print(f"  {k:20s} - {v['title']}")
            print("\n用法:")
            print(f"  python {sys.argv[0]} <preset_name>  # 运行预设查询")
            print(f"  python {sys.argv[0]} custom \"<SQL>\" \"<title>\" [output.html]")
        else:
            print(f"未知命令: {cmd}")
            print(f"用法: python {sys.argv[0]} [list|clearing_price|supply_demand|boundary|custom]")
    else:
        # 默认：打开出清价格预测
        print("未指定查询，使用默认预设 'clearing_price'")
        print("可用预设: clearing_price, supply_demand, boundary")
        print(f"用法: python {sys.argv[0]} [list|preset_name]")
        run_preset("clearing_price")
