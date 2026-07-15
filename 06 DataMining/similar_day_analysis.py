"""Similar day analysis for bidding space curves.

Given a target date, find the most similar days based on:
1. 2h sliding window peak-valley difference (value + timing)
2. 96-point curve shape (Pearson correlation)
3. Seasonal bonus: 7-8月优先选2025年同期，其次选本年最近30日

Usage:
    python similar_day_analysis.py compute               # compute features for all dates
    python similar_day_analysis.py 2026-06-06            # generate HTML for target date
    python similar_day_analysis.py 2026-06-06 --top 10   # top N similar days

Data source: local SQLite (data/cache/local.db)
Output: output/竞价空间分析结果/相似日分析_YYYY-MM-DD.html
"""

import json
import math
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, date

# ── Paths ──
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'output', '竞价空间分析结果')
DB_PATH = os.path.join(ROOT, 'data', 'cache', 'local.db')
FEATURES_PATH = os.path.join(ROOT, '_tmp_similar_features.json')

# ── 96 time labels ──
TIME_LABELS = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0, 15, 30, 45)]

# ── Time period classification ──
# 凌晨 0-5, 上午 6-11, 中午 12-13, 下午 14-17, 晚间 18-23
PERIOD_NAMES = ['凌晨', '上午', '中午', '下午', '晚间']
PERIOD_BOUNDS = [0, 24, 48, 56, 72, 96]  # 15-min index boundaries


def get_period(idx: int) -> int:
    """Return period index (0-4) for a 15-min time index (0-95)."""
    for pi in range(5):
        if PERIOD_BOUNDS[pi] <= idx < PERIOD_BOUNDS[pi + 1]:
            return pi
    return 4


def get_period_name(idx: int) -> str:
    return PERIOD_NAMES[get_period(idx)]


def sliding_window_peak_valley(values: list[float]) -> dict:
    """Compute 2-hour (8-point) sliding window peak-valley characteristics.

    Peak = mean of the 2h window with the HIGHEST mean value.
    Valley = mean of the 2h window with the LOWEST mean value.
    Diff = peak - valley.
    Timing = period (凌晨/上午/中午/下午/晚间) of the window's center point.

    Returns:
        {'peak': float, 'valley': float, 'diff': float,
         'peak_idx': int, 'valley_idx': int,
         'peak_period': str, 'valley_period': str,
         'peak_time': str, 'valley_time': str}
    """
    n = len(values)
    best_peak = {'mean': -1e9, 'idx': 0}
    best_valley = {'mean': 1e9, 'idx': 0}

    for start in range(n - 8):
        window = values[start:start + 8]
        w_mean = sum(window) / 8
        if w_mean > best_peak['mean']:
            best_peak = {'mean': w_mean, 'idx': start + 4}  # center of window
        if w_mean < best_valley['mean']:
            best_valley = {'mean': w_mean, 'idx': start + 4}

    return {
        'peak': round(best_peak['mean'], 2),
        'valley': round(best_valley['mean'], 2),
        'diff': round(best_peak['mean'] - best_valley['mean'], 2),
        'peak_idx': best_peak['idx'],
        'valley_idx': best_valley['idx'],
        'peak_period': get_period_name(best_peak['idx']),
        'valley_period': get_period_name(best_valley['idx']),
        'peak_time': TIME_LABELS[best_peak['idx']],
        'valley_time': TIME_LABELS[best_valley['idx']],
    }


def pearson_correlation(a: list[float], b: list[float]) -> float:
    """Compute Pearson correlation coefficient between two 96-point series."""
    n = len(a)
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
    std_b = math.sqrt(sum((x - mean_b) ** 2 for x in b))
    if std_a == 0 or std_b == 0:
        return 0.0
    return cov / (std_a * std_b)


def load_data() -> dict[str, list[float]]:
    """Load all bidding_space_forecast from local SQLite. Returns {date: [96 values]}."""
    if not os.path.exists(DB_PATH):
        print(f'Database not found: {DB_PATH}')
        print('Sync first: python local_db.py sync')
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    sql = '''
        SELECT date, time_order, bidding_space
        FROM bidding_space_forecast
        ORDER BY date, time_order
    '''
    rows = conn.execute(sql).fetchall()
    conn.close()

    data = defaultdict(list)
    for d, to, bs in rows:
        data[d].append(bs or 0)

    return dict(data)


def _auto_sync_before_load():
    """Auto-sync all local tables from 天机库 before loading data.

    Delegates to local_db.auto_sync() which checks each table and syncs
    if 天机库 has newer data. 本地表优点：可以手动导入天机源表未更新的数据；
    天机源表优点：每日自动更新。取二者中最新的数据。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'local_db', os.path.join(os.path.dirname(__file__), 'local_db.py')
    )
    if spec and spec.loader:
        local_db = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(local_db)
        synced = local_db.auto_sync()
        if synced:
            print(f'Auto-sync: {synced} total rows synced across {len(synced)} tables')


def load_bs_actual() -> dict[str, list[float]]:
    """Load bidding_space_actual from local SQLite. Returns {date: [96 values]}."""
    if not os.path.exists(DB_PATH):
        return {}
    conn = sqlite3.connect(DB_PATH)
    sql = '''
        SELECT date, time_order, bidding_space
        FROM bidding_space_actual
        ORDER BY date, time_order
    '''
    rows = conn.execute(sql).fetchall()
    conn.close()

    data = defaultdict(list)
    for d, to, bs in rows:
        data[d].append(bs or 0)
    return dict(data)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'local_db', os.path.join(os.path.dirname(__file__), 'local_db.py')
    )
    if spec and spec.loader:
        local_db = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(local_db)
        try:
            local_db.auto_sync()
        except Exception as e:
            print(f'  Auto-sync skipped: {e}')


def load_prices() -> dict[str, dict[str, list[float]]]:
    """Load 润津 dayahead & realtime prices, auto-syncing from 天机库 first.

    Checks 天机库 for newer data before reading local DB. 天机源表优点在于
    每日自动更新，本地表的优点在于可以手动导入天机源表未更新的数据。

    Returns:
        {'dayahead': {date: [96 values]}, 'realtime': {date: [96 values]}}
        Missing time_orders are filled with 0.0.
    """
    if not os.path.exists(DB_PATH):
        return {'dayahead': {}, 'realtime': {}}

    # 先从天机库同步最新数据
    _auto_sync_before_load()

    conn = sqlite3.connect(DB_PATH)
    out = {}
    for key, table in [('dayahead', 'dayahead_price'), ('realtime', 'realtime_price')]:
        sql = f'''
            SELECT date, time_order, price
            FROM {table}
            ORDER BY date, time_order
        '''
        rows = conn.execute(sql).fetchall()
        per_date = defaultdict(lambda: [0.0] * 96)
        for d, to, price in rows:
            idx = (int(to) - 1) if int(to) >= 1 else 0
            if 0 <= idx < 96:
                per_date[d][idx] = float(price) if price is not None else 0.0
        out[key] = dict(per_date)
    conn.close()
    return out


def compute_features():
    """Compute peak-valley features for all dates, save to JSON."""
    data = load_data()
    features = {}

    for d, values in sorted(data.items()):
        if len(values) != 96:
            continue
        feat = sliding_window_peak_valley(values)
        feat['values'] = values  # store full curve for correlation
        features[d] = feat

    with open(FEATURES_PATH, 'w', encoding='utf-8') as f:
        # Don't store values in JSON (too large); store separately
        json.dump({d: {k: v for k, v in feat.items() if k != 'values'}
                   for d, feat in features.items()}, f, ensure_ascii=False, indent=2)

    print(f'Computed features for {len(features)} dates → {FEATURES_PATH}')
    return features


def load_features() -> dict[str, dict]:
    """Load pre-computed features from JSON."""
    if not os.path.exists(FEATURES_PATH):
        print('Features not found. Run "python similar_day_analysis.py compute" first.')
        sys.exit(1)
    with open(FEATURES_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def compute_similarity(target: str, candidates: dict, top_n: int = 10) -> list[dict]:
    """Compute similarity scores for all candidates vs target.

    Seasonal bonus rules（电力系统季节特性）:
    季节划分:
      - 夏季: 6-8月（7-8月为空调尖峰保供）
      - 供暖季: 11月15日 ~ 次年3月15日（12-2月为供暖尖峰保供）
      - 春季: 3月16日 ~ 5月31日
      - 秋季: 9月1日 ~ 11月14日

    保供尖峰月份 (7-8月, 12-2月):
      1. 去年同保供尖峰月份 → +0.12（最高）
      2. 本年同季节非保供月份 → +0.08
      3. 去年同季节非保供月份 → +0.06
      4. 本年30日内（非本季节）→ +0.04
      其他日期全部排除

    非保供季节 (6月, 3月16日-5月, 9月-11月14日):
      1. 去年同季节 → +0.08
      2. 本年同季节30日内 → +0.06
      3. 本年30日内 → +0.04
      其他日期全部排除

    Args:
        target: target date string.
        candidates: {date: feature_dict} — must include 'values' key.
        top_n: number of top results to return.

    Returns:
        Sorted list of {date, score, scores: {dim: score}, ...}, best first.
    """
    from datetime import datetime, timedelta

    t = candidates.get(target)
    if not t:
        return []

    t_vals = t['values']
    t_valley = t['valley']
    t_peak = t['peak']
    t_valley_period = t['valley_period']
    t_peak_period = t['peak_period']

    results = []

    valleys = [c['valley'] for c in candidates.values() if c.get('valley', 0) > 0]
    peaks = [c['peak'] for c in candidates.values() if c.get('peak', 0) > 0]
    max_valley = max(valleys) if valleys else 1
    max_peak = max(peaks) if peaks else 1

    target_dt = datetime.strptime(target, '%Y-%m-%d')
    target_year = target_dt.year
    target_month = target_dt.month
    target_day = target_dt.day

    # ── Determine target season ──
    # 供暖季: 11月15日 ~ 次年3月15日
    def is_heating_season(m, d):
        return (m == 11 and d >= 15) or m == 12 or m in (1, 2) or (m == 3 and d <= 15)

    # 供暖尖峰保供: 12-2月
    # 夏季: 6-8月
    # 空调尖峰保供: 7-8月

    def is_target_peak_season(m):
        """Check if target month is a peak supply-guarantee month."""
        return m in (7, 8, 12, 1, 2)

    def is_target_heating(m, d):
        return is_heating_season(m, d)

    def is_target_summer(m):
        return m in (6, 7, 8)

    def is_target_spring(m):
        return m in (3, 4, 5)

    def is_target_autumn(m, d):
        return (m == 9) or (m == 10) or (m == 11 and d < 15)

    def get_season_type(m, d):
        """Return ('peak'|'summer_nonpeak'|'heating'|'spring'|'autumn', month_range)."""
        if m in (7, 8):
            return 'summer_peak', (7, 8)
        if m in (12, 1, 2):
            return 'heating_peak', (12, 1, 2)
        if m == 6:
            return 'summer_nonpeak', (6,)
        if is_heating_season(m, d):
            return 'heating_nonpeak', None  # 11月15-30, 3月1-15
        if m in (3, 4, 5):
            return 'spring', (3, 4, 5)
        return 'autumn', (9, 10, 11)

    target_season_type, target_season_months = get_season_type(target_month, target_day)
    target_is_peak = target_season_type in ('summer_peak', 'heating_peak')

    for d, c in candidates.items():
        if d == target:
            continue
        if len(c.get('values', [])) != 96:
            continue

        c_vals = c['values']
        c_valley = c['valley']
        c_peak = c['peak']
        c_valley_period = c['valley_period']
        c_peak_period = c['peak_period']
        c_year = int(d.split('-')[0]) if '-' in d else 0
        c_month = int(d.split('-')[1]) if '-' in d else 0
        c_dt = datetime.strptime(d, '%Y-%m-%d')

        # ── Seasonal filtering ──
        bonus = 0.0
        bonus_label = ''

        if target_is_peak:
            # 保供尖峰月份 (7-8月, 12-2月)
            # 1. 本年同保供月份30日内 +0.12（最高）
            if c_year == target_year and c_month in target_season_months and abs((c_dt - target_dt).days) <= 30:
                bonus = 0.12
                bonus_label = ' [本年保供]'
            # 2. 去年同保供月份 +0.10
            elif c_year == target_year - 1 and c_month in target_season_months:
                bonus = 0.10
                bonus_label = ' [去年保供]'
            # 3. 本年同季节非保供月份 +0.08
            elif c_year == target_year and (
                (target_season_type == 'summer_peak' and c_month == 6) or
                (target_season_type == 'heating_peak' and is_heating_season(c_month, c_dt.day) and c_month not in (12, 1, 2))
            ):
                bonus = 0.08
                bonus_label = ' [本年同季]'
            # 4. 去年同季节非保供月份 +0.06
            elif c_year == target_year - 1 and (
                (target_season_type == 'summer_peak' and c_month == 6) or
                (target_season_type == 'heating_peak' and is_heating_season(c_month, c_dt.day) and c_month not in (12, 1, 2))
            ):
                bonus = 0.06
                bonus_label = ' [去年同季]'
            # 5. 本年30日内（非本季节） +0.04
            elif c_year == target_year and abs((c_dt - target_dt).days) <= 30:
                bonus = 0.04
                bonus_label = ' [本年30日]'
            else:
                continue
        else:
            # 非保供季节 (6月, 春季, 秋季)
            # 1. 去年同季节 +0.08
            if c_year == target_year - 1 and (
                (target_season_type == 'summer_nonpeak' and c_month in (6, 7, 8)) or
                (target_season_type == 'spring' and c_month in (3, 4, 5)) or
                (target_season_type == 'autumn' and c_month in (9, 10, 11)) or
                (target_season_type == 'heating_nonpeak' and is_heating_season(c_month, c_dt.day))
            ):
                bonus = 0.08
                bonus_label = ' [去年同季]'
            # 2. 本年同季节30日内 +0.06
            elif c_year == target_year and abs((c_dt - target_dt).days) <= 30 and (
                (target_season_type == 'summer_nonpeak' and c_month in (6, 7, 8)) or
                (target_season_type == 'spring' and c_month in (3, 4, 5)) or
                (target_season_type == 'autumn' and c_month in (9, 10, 11)) or
                (target_season_type == 'heating_nonpeak' and is_heating_season(c_month, c_dt.day))
            ):
                bonus = 0.06
                bonus_label = ' [本年同季]'
            # 3. 本年30日内 +0.04
            elif c_year == target_year and abs((c_dt - target_dt).days) <= 30:
                bonus = 0.04
                bonus_label = ' [本年30日]'
            else:
                continue

        # ── Dimension scores ──
        valley_score = max(0, 1 - abs(c_valley - t_valley) / max_valley)
        peak_score = max(0, 1 - abs(c_peak - t_peak) / max_peak)

        vp_dist = abs(PERIOD_NAMES.index(c_valley_period) - PERIOD_NAMES.index(t_valley_period))
        if vp_dist == 0:
            valley_period_score = 1.0
        elif vp_dist == 1:
            valley_period_score = 0.5
        else:
            valley_period_score = 0.0

        pp_dist = abs(PERIOD_NAMES.index(c_peak_period) - PERIOD_NAMES.index(t_peak_period))
        if pp_dist == 0:
            peak_period_score = 1.0
        elif pp_dist == 1:
            peak_period_score = 0.5
        else:
            peak_period_score = 0.0

        corr = pearson_correlation(t_vals, c_vals)
        shape_score = max(0, corr)

        score = (
            0.30 * valley_score
            + 0.25 * peak_score
            + 0.15 * valley_period_score
            + 0.10 * peak_period_score
            + 0.20 * shape_score
        ) + bonus

        results.append({
            'date': d,
            'score': round(score, 4),
            'scores': {
                '2h谷值': round(valley_score, 4),
                '2h峰值': round(peak_score, 4),
                '谷值时段': round(valley_period_score, 4),
                '峰值时段': round(peak_period_score, 4),
                '曲线形状': round(shape_score, 4),
            },
            'diff': round(c_peak - c_valley, 0),
            'diff_pct': round(((c_peak - c_valley) - (t_peak - t_valley)) / (t_peak - t_valley) * 100, 1) if (t_peak - t_valley) else 0,
            'peak': round(c_peak, 0),
            'valley': round(c_valley, 0),
            'peak_period': c_peak_period,
            'valley_period': c_valley_period,
            'peak_time': c['peak_time'],
            'valley_time': c['valley_time'],
            'correlation': round(corr, 4),
            'bonus': bonus_label,
        })

    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_n]


def generate_html(target_date: str, similar_days: list[dict],
                  features: dict[str, dict], all_dates: list[str],
                  prices: dict[str, dict[str, list[float]]]) -> str:
    """Generate interactive similar day analysis HTML."""
    init_date = target_date

    # Prepare data for embedding
    # Only include target + similar days' values for chart rendering
    embed_dates = [target_date] + [s['date'] for s in similar_days]

    # Load actual bidding space data for overlay
    bs_actual = load_bs_actual()

    embed_data = {}
    for d in embed_dates:
        feat = features.get(d, {})
        embed_data[d] = {
            'values': feat.get('values', []),          # 预测竞价空间
            'actual': bs_actual.get(d, []),             # 实际竞价空间
            'diff': feat.get('diff', 0),
            'peak': feat.get('peak', 0),
            'valley': feat.get('valley', 0),
            'peak_period': feat.get('peak_period', ''),
            'valley_period': feat.get('valley_period', ''),
            'peak_time': feat.get('peak_time', ''),
            'valley_time': feat.get('valley_time', ''),
        }

    # Build price data: {date: {'dayahead': [96], 'realtime': [96]}}
    da = prices.get('dayahead', {})
    rt = prices.get('realtime', {})
    embed_prices = {}
    for d in embed_dates:
        embed_prices[d] = {
            'dayahead': da.get(d, []),
            'realtime': rt.get(d, []),
        }

    time_labels_json = json.dumps(TIME_LABELS, ensure_ascii=False)
    embed_json = json.dumps(embed_data, ensure_ascii=False)
    embed_prices_json = json.dumps(embed_prices, ensure_ascii=False)
    similar_json = json.dumps(similar_days, ensure_ascii=False)
    all_dates_json = json.dumps(all_dates, ensure_ascii=False)

    # Build similar day table rows
    table_rows = ''
    for i, s in enumerate(similar_days):
        pct_str = f'{s["diff_pct"]:+.1f}%' if s['diff_pct'] else '—'
        pct_color = '#d13438' if s['diff_pct'] > 0 else '#107c10' if s['diff_pct'] < 0 else '#888'
        table_rows += f'''
        <tr class="sim-row" data-date="{s['date']}" onclick="highlightDay('{s['date']}')">
          <td class="rank">{i+1}</td>
          <td class="date">{s['date']}{s.get('bonus', '')}</td>
          <td class="score"><b>{s['score']:.4f}</b></td>
          <td>{s['valley']:.0f} MW <span style="color:#888;font-size:10px">({s['valley_period']})</span></td>
          <td>{s['peak']:.0f} MW <span style="color:#888;font-size:10px">({s['peak_period']})</span></td>
          <td>{s['diff']:.0f} MW <span style="color:{pct_color};font-size:10px">({pct_str})</span></td>
          <td>{s['correlation']:.4f}</td>
        </tr>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>竞价空间相似日分析 — {target_date}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:#f3f3f3;color:#333;min-height:100vh}}
.header{{background:#fff;padding:12px 24px;border-bottom:1px solid #d9d9d9;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.header h1{{font-size:18px;color:#0078d4;font-weight:600}}
.header .info{{font-size:11px;color:#888}}
.date-picker{{display:flex;align-items:center;gap:8px;font-size:13px}}
.date-picker select{{padding:4px 8px;border:1px solid #c8c8c8;border-radius:4px;font-size:13px}}
.date-picker button{{padding:5px 14px;background:#0078d4;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px}}
.date-picker button:hover{{opacity:.85}}
.main-grid{{display:grid;grid-template-columns:1fr 380px;gap:0}}
@media(max-width:1200px){{.main-grid{{grid-template-columns:1fr}}}}
.charts-area{{padding:8px;display:flex;flex-direction:column;gap:6px}}
.chart-panel{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.chart-panel .panel-title{{padding:6px 14px;font-size:12px;font-weight:600;color:#333;border-bottom:1px solid #e8e8e8;background:#fafafa}}
.chart-box{{width:100%;height:380px}}
.sidebar{{background:#fff;border-left:1px solid #e0e0e0;padding:12px;display:flex;flex-direction:column;gap:6px;overflow:hidden}}
.sidebar h3{{font-size:13px;color:#0078d4;margin-bottom:2px;border-bottom:1px solid #e8e8e8;padding-bottom:4px;flex-shrink:0}}
.radar-box{{width:100%;height:220px;flex-shrink:0}}
.sim-table{{width:100%;border-collapse:collapse;font-size:11px}}
.sim-table th{{background:#f5f5f5;color:#333;padding:5px 6px;text-align:left;border-bottom:2px solid #e0e0e0;position:sticky;top:0;white-space:nowrap}}
.sim-table td{{padding:4px 6px;border-bottom:1px solid #f0f0f0;white-space:nowrap}}
.sim-table tr:hover td{{background:#e5f3ff;cursor:pointer}}
.sim-table tr.selected td{{background:#cce5ff;font-weight:600}}
.sim-table .rank{{text-align:center;font-weight:bold;color:#0078d4;width:24px}}
.sim-table .score{{color:#0078d4}}
.sim-table .date{{font-family:monospace}}
.sim-table th.sortable{{cursor:pointer;user-select:none}}
.sim-table th.sortable:hover{{color:#0078d4}}
.table-wrap{{overflow-x:auto;border:1px solid #e0e0e0;border-radius:4px}}
.legend-tip{{font-size:10px;color:#999;margin-top:4px;line-height:1.4;flex-shrink:0}}
.summary-bar{{display:flex;gap:8px;padding:8px 20px;flex-wrap:wrap}}
.summary-chip{{background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:6px 14px;flex:1;min-width:120px;text-align:center}}
.summary-chip .chip-label{{font-size:10px;color:#888;margin-bottom:2px}}
.summary-chip .chip-value{{font-size:18px;font-weight:700;color:#0078d4}}
.summary-chip .chip-sub{{font-size:10px;color:#999}}
.footer{{text-align:center;padding:8px;font-size:10px;color:#aaa}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>竞价空间相似日分析</h1>
    <div class="info">目标日期: {target_date} | 算法: 2h谷值(30%) + 2h峰值(25%) + 谷值时段(15%) + 峰值时段(10%) + 曲线形状(20%)</div>
  </div>
  <div class="date-picker">
    <span>跳转日期:</span>
    <select id="dateSelect"></select>
    <button onclick="jumpToDate()">分析</button>
  </div>
</div>
<div class="summary-bar" id="summaryBar"></div>
<div class="main-grid">
  <div class="charts-area">
    <div class="chart-panel">
      <div class="panel-title">目标日竞价空间 + 电价 <span style="font-weight:400;color:#888;font-size:11px">(左轴 MW / 右轴 元/MWh) — {target_date}，点击表格行切换电价</span></div>
      <div class="chart-box" id="chartTarget"></div>
    </div>
    <div class="chart-panel">
      <div class="panel-title">相似日曲线对比 <span style="font-weight:400;color:#888;font-size:11px">(MW) — 点击表格高亮</span></div>
      <div class="chart-box" id="chartCompare"></div>
    </div>
  </div>
  <div class="sidebar">
    <h3>相似度雷达图 — {target_date}</h3>
    <div class="radar-box" id="chartRadar"></div>
    <h3>Top {len(similar_days)} 相似日排名
      <span style="font-size:10px;color:#888;font-weight:400;margin-left:8px">点击表头排序</span>
      <span style="float:right;font-size:11px;font-weight:400">
        <label style="cursor:pointer"><input type="radio" name="sortBy" value="score" checked onchange="renderTable()"> 按相似度</label>
        <label style="cursor:pointer;margin-left:8px"><input type="radio" name="sortBy" value="date" onchange="renderTable()"> 按日期</label>
      </span>
    </h3>
    <div class="table-wrap">
      <table class="sim-table">
        <thead>
          <tr><th class="rank">#</th><th class="sortable">日期</th><th class="sortable">相似度</th><th>2h谷值</th><th>2h峰值</th><th>峰谷差</th><th>相关系数</th></tr>
        </thead>
        <tbody id="simTbody"></tbody>
      </table>
    </div>
    <div class="legend-tip">
      算法说明：<br>
      · 2h谷值(30%)：2h最低均值窗口的MW值<br>
      · 2h峰值(25%)：2h最高均值窗口的MW值<br>
      · 谷值时段(15%)：谷值窗口在哪个时段<br>
      · 峰值时段(10%)：峰值窗口在哪个时段<br>
      · 曲线形状(20%)：Pearson相关系数<br>
      · 2h均值权重55%，时段25%，曲线20%
    </div>
  </div>
</div>
<div class="footer">润津储能 · 竞价空间相似日分析 · 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>

<script>
var DATA = {embed_json};
var PRICES = {embed_prices_json};
var SIMILAR = {similar_json};
var TIMES = {time_labels_json};
var ALL_DATES = {all_dates_json};
var TARGET = '{target_date}';

// ── Date selector ──
var sel = document.getElementById('dateSelect');
ALL_DATES.forEach(function(d) {{
  var opt = document.createElement('option');
  opt.value = d;
  opt.textContent = d;
  if (d === TARGET) opt.selected = true;
  sel.appendChild(opt);
}});

function jumpToDate() {{
  var d = sel.value;
  if (d && d !== TARGET) {{
    // Use full href, replace the date part in the filename
    var url = window.location.href;
    var newUrl = url.replace(/相似日分析_[0-9-]+\\.html/, '相似日分析_' + d + '.html');
    window.location.href = newUrl;
  }}
}}

// ── Charts ──
var cTarget = echarts.init(document.getElementById('chartTarget'));
var cCompare = echarts.init(document.getElementById('chartCompare'));
var cRadar = echarts.init(document.getElementById('chartRadar'));

var g = {{left:55,right:60,top:20,bottom:35}};
var ec = {{axisLabel:{{color:'#888',fontSize:10}},axisLine:{{lineStyle:{{color:'#d0d0d0'}}}},splitLine:{{lineStyle:{{color:'#f0f0f0'}}}}}};
var ec2 = {{axisLabel:{{color:'#e67e22',fontSize:10}},axisLine:{{lineStyle:{{color:'#e67e22'}}}},splitLine:{{show:false}}}};
var el = {{textStyle:{{color:'#666',fontSize:11}},top:3}};

function fmt(v){{return v!=null?v.toFixed(0):'—';}}
function fmtPrice(v){{return v!=null?v.toFixed(2):'—';}}

var COLORS = ['#0078d4','#d13438','#107c10','#f2a900','#9a60b4','#5470c6','#d83b01','#73c0de','#fc8452','#3ba272'];

// Chart 1: Target day 竞价空间(左轴) + 电价(右轴)
function getTargetOpt() {{
  var d = DATA[TARGET];
  var s = [{{
    name:TARGET+' 预测竞价空间', type:'line', data:d.values, smooth:true,
    lineStyle:{{width:2.5,color:'#0078d4'}}, itemStyle:{{color:'#0078d4'}}, symbol:'none',
    areaStyle:{{color:new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:'rgba(0,120,212,0.2)'}},{{offset:1,color:'rgba(0,120,212,0)'}}])}}
  }}];
  // 目标日实际竞价空间
  if (d.actual && d.actual.length === 96 && d.actual.some(function(v){{return v!==0;}})) {{
    s.push({{
      name:TARGET+' 实际竞价空间', type:'line', data:d.actual, smooth:true,
      lineStyle:{{width:2,color:'#107c10',type:'dashed'}}, itemStyle:{{color:'#107c10'}}, symbol:'none'
    }});
  }}
  // 相似日（高亮）的预测竞价空间
  var hld = highlightedDay || null;
  if (hld && DATA[hld]) {{
    var hd = DATA[hld];
    s.push({{
      name:hld+' 预测竞价空间', type:'line', data:hd.values, smooth:true,
      lineStyle:{{width:2,color:'#f2a900',type:'dotted'}}, itemStyle:{{color:'#f2a900'}}, symbol:'none'
    }});
    if (hd.actual && hd.actual.length === 96 && hd.actual.some(function(v){{return v!==0;}})) {{
      s.push({{
        name:hld+' 实际竞价空间', type:'line', data:hd.actual, smooth:true,
        lineStyle:{{width:1.5,color:'#d13438',type:'dashed'}}, itemStyle:{{color:'#d13438'}}, symbol:'none'
      }});
    }}
  }}
  // 电价（右轴）——显示目标日或高亮相似日的电价
  var pdd = highlightedDay || TARGET;
  var p = PRICES[pdd] || {{dayahead:[],realtime:[]}};
  var hasDA = p.dayahead && p.dayahead.length === 96 && p.dayahead.some(function(v){{return v!==0;}});
  var hasRT = p.realtime && p.realtime.length === 96 && p.realtime.some(function(v){{return v!==0;}});
  var priceTag = highlightedDay ? (' [' + pdd + ' 相似日电价]') : ' [目标日电价]';
  if (hasDA) {{
    s.push({{name:'日前电价'+priceTag, type:'line', data:p.dayahead, smooth:true,
      lineStyle:{{width:2,color:'#9a60b4'}}, itemStyle:{{color:'#9a60b4'}}, symbol:'none', yAxisIndex:1}});
  }}
  if (hasRT) {{
    s.push({{name:'实时电价'+priceTag, type:'line', data:p.realtime, smooth:true,
      lineStyle:{{width:2,color:'#d13438'}}, itemStyle:{{color:'#d13438'}}, symbol:'none', yAxisIndex:1}});
  }}
  var yAxis = [Object.assign({{type:'value',name:'MW'}},ec)];
  if (hasDA || hasRT) {{
    yAxis.push(Object.assign({{type:'value',name:'元/MWh',min:-100,max:1500}},ec2));
  }}
  var legendData = s.map(function(x){{return x.name;}});
  return {{grid:g,tooltip:{{trigger:'axis',valueFormatter:function(v){{return v!=null?(Math.abs(v)<1000?v.toFixed(2):v.toFixed(0)):'—';}}}},
    legend:Object.assign({{data:legendData}},el),
    xAxis:Object.assign({{type:'category',data:TIMES,axisLabel:{{interval:7}}}},ec),
    yAxis:yAxis,
    series:s}};
}}

// Chart 2: Comparison curves
var highlightedDay = null;

function getCompareOpt() {{
  var s = [];
  // Target prediction line
  var d = DATA[TARGET];
  s.push({{
    name:TARGET+' 预测(目标)', type:'line', data:d.values, smooth:true,
    lineStyle:{{width:3,color:'#0078d4'}}, itemStyle:{{color:'#0078d4'}}, symbol:'none',
    z:10
  }});
  // Target actual line
  if (d.actual && d.actual.length === 96 && d.actual.some(function(v){{return v!==0;}})) {{
    s.push({{
      name:TARGET+' 实际(目标)', type:'line', data:d.actual, smooth:true,
      lineStyle:{{width:2,color:'#107c10',type:'dashed'}}, itemStyle:{{color:'#107c10'}}, symbol:'none',
      z:9
    }});
  }}
  // Similar days
  SIMILAR.forEach(function(sim, i) {{
    var sd = DATA[sim.date];
    if (!sd) return;
    var isHL = (sim.date === highlightedDay);
    s.push({{
      name:sim.date+' 预测(相似度:'+sim.score.toFixed(4)+')',
      type:'line', data:sd.values, smooth:true,
      lineStyle:{{width:isHL?3:1,color:COLORS[(i+1)%COLORS.length],opacity:isHL?1:0.5}},
      itemStyle:{{color:COLORS[(i+1)%COLORS.length]}}, symbol:'none',
      z:isHL?9:1
    }});
    // Highlighted similar day actual
    if (isHL && sd.actual && sd.actual.length === 96 && sd.actual.some(function(v){{return v!==0;}})) {{
      s.push({{
        name:sim.date+' 实际', type:'line', data:sd.actual, smooth:true,
        lineStyle:{{width:2,color:'#d13438',type:'dashed'}}, itemStyle:{{color:'#d13438'}}, symbol:'none',
        z:8
      }});
    }}
  }});
  return {{grid:g,tooltip:{{trigger:'axis'}},legend:Object.assign({{data:s.map(function(x){{return x.name;}}),type:'scroll',bottom:0}},el),xAxis:Object.assign({{type:'category',data:TIMES,axisLabel:{{interval:7}}}},ec),yAxis:Object.assign({{type:'value',name:'MW'}},ec),series:s}};
}}

// Chart 3: Radar
function getRadarOpt() {{
  var dims = ['2h谷值','2h峰值','谷值时段','峰值时段','曲线形状'];
  var indicator = dims.map(function(d){{return {{name:d, max:1}};}});
  var series = [];
  series.push({{
    name:TARGET, type:'radar',
    data:[{{value:[1,1,1,1,1], name:TARGET+' (目标)'}}],
    lineStyle:{{color:'#0078d4',width:2}}, itemStyle:{{color:'#0078d4'}},
    areaStyle:{{color:'rgba(0,120,212,0.1)'}}, symbol:'none'
  }});
  SIMILAR.forEach(function(sim, i) {{
    var sc = sim.scores;
    series.push({{
      name:sim.date, type:'radar',
      data:[{{value:[sc['2h谷值'],sc['2h峰值'],sc['谷值时段'],sc['峰值时段'],sc['曲线形状']],name:sim.date+' ('+sim.score.toFixed(4)+')'}}],
      lineStyle:{{color:COLORS[(i+1)%COLORS.length],width:1}}, itemStyle:{{color:COLORS[(i+1)%COLORS.length]}},
      symbol:'none'
    }});
  }});
  return {{
    radar:{{indicator:indicator,center:['50%','55%'],radius:'65%'}},
    legend:{{show:false}},
    series:series
  }};
}}

function highlightDay(d) {{
  highlightedDay = (highlightedDay === d) ? null : d;
  document.querySelectorAll('.sim-row').forEach(function(r){{r.classList.remove('selected');}});
  if (highlightedDay) {{
    var rows = document.querySelectorAll('.sim-row');
    rows.forEach(function(r){{if(r.dataset.date===highlightedDay) r.classList.add('selected');}});
  }}
  cCompare.setOption(getCompareOpt(), true);
  cTarget.setOption(getTargetOpt(), true);
}}

// ── Table rendering with sort ──
var sortMode = 'score';  // 'score' or 'date'

function renderTable() {{
  var sortBy = document.querySelector('input[name="sortBy"]:checked');
  sortMode = sortBy ? sortBy.value : 'score';
  var rows = SIMILAR.slice();
  if (sortMode === 'date') {{
    rows.sort(function(a,b){{return a.date < b.date ? -1 : (a.date > b.date ? 1 : 0);}});
  }} else {{
    rows.sort(function(a,b){{return b.score - a.score;}});
  }}
  var html = '';
  rows.forEach(function(s, i) {{
    var pctStr = s.diff_pct ? (s.diff_pct > 0 ? '+' : '') + s.diff_pct.toFixed(1) + '%' : '—';
    var pctColor = s.diff_pct > 0 ? '#d13438' : (s.diff_pct < 0 ? '#107c10' : '#888');
    html += '<tr class="sim-row" data-date="' + s.date + '" onclick="highlightDay(\\'' + s.date + '\\')">';
    html += '<td class="rank">' + (i+1) + '</td>';
    html += '<td class="date">' + s.date + (s.bonus || '') + '</td>';
    html += '<td class="score"><b>' + s.score.toFixed(4) + '</b></td>';
    html += '<td>' + s.valley.toFixed(0) + ' MW <span style="color:#888;font-size:10px">(' + s.valley_period + ')</span></td>';
    html += '<td>' + s.peak.toFixed(0) + ' MW <span style="color:#888;font-size:10px">(' + s.peak_period + ')</span></td>';
    html += '<td>' + s.diff.toFixed(0) + ' MW <span style="color:' + pctColor + ';font-size:10px">(' + pctStr + ')</span></td>';
    html += '<td>' + s.correlation.toFixed(4) + '</td>';
    html += '</tr>';
  }});
  var tbody = document.getElementById('simTbody');
  tbody.innerHTML = html;
  // Restore highlighted row state
  if (highlightedDay) {{
    document.querySelectorAll('.sim-row').forEach(function(r){{if(r.dataset.date===highlightedDay) r.classList.add('selected');}});
  }}
}}

function renderSummary() {{
  var d = DATA[TARGET];
  var bs = d.values;
  var bsAvg = bs.reduce(function(a,b){{return a+b;}},0)/96;
  var bsMax = Math.max.apply(null, bs);
  var bsMin = Math.min.apply(null, bs);
  var html = '';
  html += '<div class="summary-chip"><div class="chip-label">目标日</div><div class="chip-value">'+TARGET+'</div><div class="chip-sub"></div></div>';
  html += '<div class="summary-chip"><div class="chip-label">竞价空间均值</div><div class="chip-value" style="color:#0078d4">'+fmt(bsAvg)+'</div><div class="chip-sub">MW</div></div>';
  html += '<div class="summary-chip"><div class="chip-label">2h谷值</div><div class="chip-value" style="color:#d13438">'+fmt(d.valley)+' MW</div><div class="chip-sub">'+d.valley_period+'</div></div>';
  html += '<div class="summary-chip"><div class="chip-label">2h峰值</div><div class="chip-value" style="color:#107c10">'+fmt(d.peak)+' MW</div><div class="chip-sub">'+d.peak_period+'</div></div>';
  html += '<div class="summary-chip"><div class="chip-label">峰谷差</div><div class="chip-value" style="color:#0078d4">'+fmt(d.peak - d.valley)+' MW</div><div class="chip-sub"></div></div>';
  html += '<div class="summary-chip"><div class="chip-label">最佳相似日</div><div class="chip-value">'+(SIMILAR[0]?SIMILAR[0].date:'—')+'</div><div class="chip-sub">相似度 '+(SIMILAR[0]?SIMILAR[0].score.toFixed(4):'—')+'</div></div>';
  html += '<div class="summary-chip"><div class="chip-label">候选池</div><div class="chip-value">'+(ALL_DATES.length-1)+'天</div><div class="chip-sub">'+ALL_DATES[0]+' ~ '+ALL_DATES[ALL_DATES.length-1]+'</div></div>';
  document.getElementById('summaryBar').innerHTML = html;
}}

function renderAll() {{
  cTarget.setOption(getTargetOpt(), true);
  cCompare.setOption(getCompareOpt(), true);
  cRadar.setOption(getRadarOpt(), true);
  renderSummary();
  renderTable();
}}

renderAll();
window.addEventListener('resize', function(){{cTarget.resize();cCompare.resize();cRadar.resize();}});
</script>
</body>
</html>'''
    return html


def main(target_date: str = None, top_n: int = 10, recompute: bool = False):
    """Main entry point.

    Args:
        target_date: ISO date string for analysis.
        top_n: Number of similar days to return.
        recompute: If True, recompute features even if JSON exists.
    """
    # Load data
    data = load_data()
    all_dates = sorted(data.keys())

    if not all_dates:
        print('No data found in local database.')
        return

    # Load 润津 dayahead & realtime prices
    prices = load_prices()
    print(f'Prices loaded: dayahead={len(prices["dayahead"])} dates, realtime={len(prices["realtime"])} dates')

    # Compute or load features
    if recompute or not os.path.exists(FEATURES_PATH):
        features = compute_features()
    else:
        features = load_features()
        # Merge values from data
        for d in features:
            if d in data:
                features[d]['values'] = data[d]

    # Validate target
    if target_date is None:
        target_date = all_dates[-1]  # default to latest
    if target_date not in features:
        print(f'Target date {target_date} not found. Available: {all_dates[0]} ~ {all_dates[-1]}')
        return

    # Compute similarity
    similar = compute_similarity(target_date, features, top_n)

    if not similar:
        print('No similar days found.')
        return

    print(f'Target: {target_date}')
    print(f'Candidate pool: {len(features) - 1} days')
    print(f'\nTop {len(similar)} similar days:')
    print(f'{"Rank":>4}  {"Date":>12}  {"Score":>8}  {"Diff":>10}  {"Valley":>10}  {"Corr":>8}')
    print('-' * 62)
    for i, s in enumerate(similar):
        print(f'{i+1:>4}  {s["date"]:>12}  {s["score"]:.4f}  {s["diff"]:>8.0f} MW  {s["valley_time"]:>10}  {s["correlation"]:.4f}')

    # Generate HTML
    html = generate_html(target_date, similar, features, all_dates, prices)

    os.makedirs(OUT_DIR, exist_ok=True)
    fname = f'相似日分析_{target_date}.html'
    out_path = os.path.join(OUT_DIR, fname)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'\nSaved: {out_path}')
    print(f'Size: {len(html):,} bytes, {len(html.encode("utf-8")):,} bytes (UTF-8)')


if __name__ == '__main__':
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    if args[0] == 'compute':
        compute_features()
        sys.exit(0)

    # target_date [--top N] [--recompute]
    target_date = args[0]
    top_n = 10
    recompute = False

    i = 1
    while i < len(args):
        if args[i] == '--top' and i + 1 < len(args):
            top_n = int(args[i + 1]); i += 2
        elif args[i] == '--recompute':
            recompute = True; i += 1
        else:
            i += 1

    main(target_date, top_n, recompute)