"""Local SQLite cache database for bidding space, clearing price, and price forecast.

Syncs data from remote MySQL (tianrun_new) to local SQLite for offline analysis.

Usage:
    python local_db.py sync                              # sync all tables, default date range
    python local_db.py sync --start 2026-06-01 --end 2026-06-22
    python local_db.py sync --tables bidding_space       # sync specific tables
    python local_db.py sync --tables price               # clearing_price + price_forecast
    python local_db.py status                            # show table row counts & date ranges
"""

import os
import sqlite3
import sys
from datetime import datetime

import pymysql

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, 'data', 'cache', 'local.db')

# ── Remote MySQL config ────────────────────────────────────────────
REMOTE_DB = {
    'host': 'rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com',
    'port': 3306,
    'user': 'pengyiqiang',
    'password': 'pengyiqiang123',
    'database': 'tianrun_new',
}

# Default sync date range
DEFAULT_START = '2026-06-01'
DEFAULT_END = '2026-06-22'

# ── Table definitions ──────────────────────────────────────────────
# Each table maps to: remote table, columns to fetch, local table name, CREATE SQL

TABLES = {
    'bidding_space_forecast': {
        'local': 'bidding_space_forecast',
        'remote_table': 'shandong_px_spot_dayahead_load_info',
        'remote_cols': [
            'dispatched_load_forecast',
            'tie_line_load_forecast',
            'wind_power_forecast',
            'photovoltaic_power_forecast',
            'nuclear_power_forecast',
            'local_power_forecast',   # 地方电厂发电总加，预留用于分布式光伏=全网负荷-直调-地方电厂，不参与bs计算
            'self_power_forecast',
        ],
        'create': '''
            CREATE TABLE IF NOT EXISTS bidding_space_forecast (
                date        TEXT NOT NULL,
                time_order  INTEGER NOT NULL,
                dispatched_load     REAL,
                tie_line_load       REAL,
                wind_power          REAL,
                photovoltaic_power  REAL,
                nuclear_power       REAL,
                local_power         REAL,   -- 地方电厂发电总加，预留(分布式光伏用)，不参与bs
                self_power          REAL,
                bidding_space       REAL,   -- 直调-(联络+风+光+核+自备)
                PRIMARY KEY (date, time_order)
            )
        ''',
    },
    'bidding_space_actual': {
        'local': 'bidding_space_actual',
        'remote_table': 'shandong_px_spot_actual_load_info',
        'remote_cols': [
            'actual_dispatched_load',
            'actual_tie_line_load',
            'actual_wind_power',
            'actual_photovoltaic_power',
            'actual_nuclear_power',
            'actual_local_power',   # 地方电厂发电总加，预留，不参与bs
            'actual_self_power',
        ],
        'create': '''
            CREATE TABLE IF NOT EXISTS bidding_space_actual (
                date        TEXT NOT NULL,
                time_order  INTEGER NOT NULL,
                dispatched_load     REAL,
                tie_line_load       REAL,
                wind_power          REAL,
                photovoltaic_power  REAL,
                nuclear_power       REAL,
                local_power         REAL,   -- 地方电厂发电总加，预留(分布式光伏用)，不参与bs
                self_power          REAL,
                bidding_space       REAL,   -- 直调-(联络+风+光+核+自备)
                PRIMARY KEY (date, time_order)
            )
        ''',
    },
    'clearing_price': {
        'local': 'clearing_price',
        'remote_table': None,  # two tables, handled specially
        'remote_cols': [],
        'create': '''
            CREATE TABLE IF NOT EXISTS clearing_price (
                date        TEXT NOT NULL,
                time_order  INTEGER NOT NULL,
                market      TEXT NOT NULL,  -- 'dayahead' or 'realtime'
                price       REAL,
                PRIMARY KEY (date, time_order, market)
            )
        ''',
    },
    'price_forecast': {
        'local': 'price_forecast',
        'remote_table': 'algorithm_clearing_price_forecast',
        'remote_cols': [
            'org_price', 'fore_price', 'fore_price_adjusted',
        ],
        'create': '''
            CREATE TABLE IF NOT EXISTS price_forecast (
                date        TEXT NOT NULL,
                time_order  INTEGER NOT NULL,
                price_type  INTEGER NOT NULL,  -- 1=日前, 2=实时
                org_price           REAL,
                fore_price          REAL,
                fore_price_adjusted REAL,
                PRIMARY KEY (date, time_order, price_type)
            )
        ''',
    },
    'dayahead_price': {
        'local': 'dayahead_price',
        'remote_table': 'shandong_px_reliable_clearing_unit_data',
        'remote_cols': [],
        'create': '''
            CREATE TABLE IF NOT EXISTS dayahead_price (
                date        TEXT NOT NULL,
                time_order  INTEGER NOT NULL,
                price       REAL,
                PRIMARY KEY (date, time_order)
            )
        ''',
    },
    'realtime_price': {
        'local': 'realtime_price',
        'remote_table': 'shandong_px_realtime_clearing_results_query',
        'remote_cols': [],
        'create': '''
            CREATE TABLE IF NOT EXISTS realtime_price (
                date        TEXT NOT NULL,
                time_order  INTEGER NOT NULL,
                price       REAL,
                PRIMARY KEY (date, time_order)
            )
        ''',
    },
}


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    """Create all tables if they don't exist. Auto-migrate missing columns."""
    conn = _get_conn()
    for name, cfg in TABLES.items():
        conn.execute(cfg['create'])
        conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{name}_date ON {cfg["local"]}(date)')
        # Auto-migrate: add columns present in CREATE SQL but missing in existing table
        existing = {r[1] for r in conn.execute(f'PRAGMA table_info({cfg["local"]})')}
        for col in _extract_col_names(cfg['create']):
            if col not in existing and col not in ('date', 'time_order'):
                # default REAL type (read from CREATE via regex would be cleaner; use REAL)
                conn.execute(f'ALTER TABLE {cfg["local"]} ADD COLUMN {col} REAL')
    conn.commit()
    conn.close()
    print(f'Initialized: {DB_PATH}')


def _extract_col_names(create_sql: str) -> list[str]:
    """Extract column names from a CREATE TABLE SQL string."""
    import re
    # Strip the part inside parentheses
    m = re.search(r'\((.*)\)', create_sql, re.S)
    if not m:
        return []
    body = m.group(1)
    cols = []
    for line in body.split('\n'):
        line = line.strip().rstrip(',')
        if not line or line.startswith('PRIMARY') or line.startswith('FOREIGN'):
            continue
        col = line.split()[0]
        cols.append(col)
    return cols


def _remote_query(sql: str, params: tuple = ()) -> list[tuple]:
    """Execute query on remote MySQL, return list of tuples."""
    conn = pymysql.connect(**REMOTE_DB)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def _sync_bidding_space(conn: sqlite3.Connection, table_key: str, start: str, end: str):
    """Sync bidding_space_forecast or bidding_space_actual from remote."""
    cfg = TABLES[table_key]
    local_name = cfg['local']
    remote_table = cfg['remote_table']
    remote_cols = cfg['remote_cols']
    col_sql = ', '.join(remote_cols)

    sql = f"""
        SELECT date, time_order, {col_sql}
        FROM {remote_table}
        WHERE date >= %s AND date <= %s
        ORDER BY date, time_order
    """
    print(f'  Fetching {remote_table}: {start} ~ {end} ...')
    rows = _remote_query(sql, (start, end))

    insert_sql = f'''
        INSERT OR REPLACE INTO {local_name}
            (date, time_order, dispatched_load, tie_line_load, wind_power,
             photovoltaic_power, nuclear_power, local_power, self_power,
             bidding_space)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    count = 0
    for row in rows:
        d = str(row[0])
        to = int(row[1])
        vals = [float(v) if v is not None else 0.0 for v in row[2:]]
        # bidding_space = 直调负荷 - (联络线受电 + 风电 + 光伏 + 核电 + 自备)
        # 注：local_power(地方电厂发电总加)不参与bs，预留用于分布式光伏=全网负荷-直调-地方电厂
        # vals: [dispatched, tie_line, wind, pv, nuclear, local, self]
        bs = vals[0] - vals[1] - vals[2] - vals[3] - vals[4] - vals[6]
        conn.execute(insert_sql, (d, to, *vals, bs))
        count += 1
        if count % 1000 == 0:
            conn.commit()
    conn.commit()
    print(f'    {count} rows synced → {local_name}')


def _sync_clearing_price(conn: sqlite3.Connection, start: str, end: str):
    """Sync clearing_price from shandong_px_spot_dayahead_clearing_price and _realtime_.

    Note: day-ahead uses time_price column, real-time uses clearing_price column.
    Both use time_order_24 (24 hourly points), not 96-point.
    """
    member_id = 'b9e64e64a713458eba94c9af05c0a757'
    insert_sql = '''
        INSERT OR REPLACE INTO clearing_price (date, time_order, market, price)
        VALUES (?, ?, ?, ?)
    '''
    total = 0

    for market, table, price_col in [
        ('dayahead', 'shandong_px_spot_dayahead_clearing_price', 'time_price'),
        ('realtime', 'shandong_px_spot_realtime_clearing_price', 'clearing_price'),
    ]:
        print(f'  Fetching {table} ({market}): {start} ~ {end} ...')
        sql = f"""
            SELECT date, time_order_24, {price_col}
            FROM {table}
            WHERE member_id = %s AND date >= %s AND date <= %s
            ORDER BY date, time_order_24
        """
        rows = _remote_query(sql, (member_id, start, end))
        for row in rows:
            d = str(row[0])
            to = int(row[1])
            price = float(row[2]) if row[2] is not None else 0.0
            conn.execute(insert_sql, (d, to, market, price))
            total += 1
            if total % 1000 == 0:
                conn.commit()
        print(f'    {len(rows)} rows ({market})')
    conn.commit()
    print(f'    {total} total rows synced → clearing_price')


def _sync_price_forecast(conn: sqlite3.Connection, start: str, end: str):
    """Sync price_forecast from algorithm_clearing_price_forecast."""
    cfg = TABLES['price_forecast']
    sql = f"""
        SELECT date, time_order, price_type, org_price, fore_price, fore_price_adjusted
        FROM {cfg['remote_table']}
        WHERE province_id = 14 AND date >= %s AND date <= %s
        ORDER BY date, price_type, time_order
    """
    print(f'  Fetching {cfg["remote_table"]}: {start} ~ {end} ...')
    rows = _remote_query(sql, (start, end))

    insert_sql = '''
        INSERT OR REPLACE INTO price_forecast
            (date, time_order, price_type, org_price, fore_price, fore_price_adjusted)
        VALUES (?, ?, ?, ?, ?, ?)
    '''
    count = 0
    for row in rows:
        d = str(row[0])
        to = int(row[1])
        pt = int(row[2])
        vals = [float(v) if v is not None else 0.0 for v in row[3:]]
        conn.execute(insert_sql, (d, to, pt, *vals))
        count += 1
        if count % 1000 == 0:
            conn.commit()
    conn.commit()
    print(f'    {count} rows synced → price_forecast')


def _sync_price_simple(conn: sqlite3.Connection, table_key: str, start: str, end: str):
    """Sync dayahead_price or realtime_price from remote (润津电站 96点电价)."""
    cfg = TABLES[table_key]
    local_name = cfg['local']
    remote_table = cfg['remote_table']
    member_id = 'b9e64e64a713458eba94c9af05c0a757'

    print(f'  Fetching {remote_table} ({local_name}): {start} ~ {end} ...')
    sql = f"""
        SELECT date, time_point, price
        FROM {remote_table}
        WHERE member_id = %s AND date >= %s AND date <= %s
            AND unit_name LIKE '%%润津%%'
        ORDER BY date, time_point
    """
    rows = _remote_query(sql, (member_id, start, end))

    insert_sql = f'''
        INSERT OR REPLACE INTO {local_name} (date, time_order, price)
        VALUES (?, ?, ?)
    '''
    count = 0
    for row in rows:
        d = str(row[0])
        # time_point is 'HH:MM' string → convert to 1-based time_order
        tp = row[1]
        if isinstance(tp, str):
            parts = tp.split(':')
            to = int(parts[0]) * 4 + int(parts[1]) // 15 + 1
        else:
            to = int(tp)
        price = float(row[2]) if row[2] is not None else 0.0
        conn.execute(insert_sql, (d, to, price))
        count += 1
        if count % 1000 == 0:
            conn.commit()
    conn.commit()
    print(f'    {count} rows synced → {local_name}')


def sync(start: str = DEFAULT_START, end: str = DEFAULT_END,
         tables: list[str] | None = None):
    """Sync all or specified tables from remote MySQL to local SQLite.

    Args:
        start, end: ISO date range.
        tables: List of table keys, or None for all. Supports aliases:
                'bidding_space' → both forecast + actual
                'price' → clearing_price + price_forecast
    """
    init_db()

    # Resolve aliases
    if tables is None:
        tables = list(TABLES.keys())
    else:
        resolved = []
        for t in tables:
            if t == 'bidding_space':
                resolved.extend(['bidding_space_forecast', 'bidding_space_actual'])
            elif t == 'price':
                resolved.extend(['clearing_price', 'price_forecast', 'dayahead_price', 'realtime_price'])
            else:
                resolved.append(t)
        tables = resolved

    conn = _get_conn()
    print(f'Syncing {start} ~ {end} ...')

    for t in tables:
        if t == 'bidding_space_forecast':
            _sync_bidding_space(conn, t, start, end)
        elif t == 'bidding_space_actual':
            _sync_bidding_space(conn, t, start, end)
        elif t == 'clearing_price':
            _sync_clearing_price(conn, start, end)
        elif t == 'price_forecast':
            _sync_price_forecast(conn, start, end)
        elif t == 'dayahead_price':
            _sync_price_simple(conn, t, start, end)
        elif t == 'realtime_price':
            _sync_price_simple(conn, t, start, end)
        else:
            print(f'  Unknown table: {t}')

    conn.close()
    print('Sync complete.')


def auto_sync() -> dict[str, int]:
    """Auto-sync all tables: 探查天机源表最新日期, 如果天机库有更新则同步到本地库.

    本地表优点：可以手动导入天机源表未更新的数据
    天机源表优点：每日自动更新
    取二者中最新的数据

    Returns:
        {table_name: rows_synced} — 各表同步行数
    """
    import pymysql
    from datetime import date as date_type

    init_db()

    result = {}
    conn = _get_conn()

    # 表映射: (local_table, remote_table, extra_where, sync_func)
    # sync_func(local_conn, start, end) → row_count
    sync_tasks = [
        ('bidding_space_forecast', 'shandong_px_spot_dayahead_load_info',
         '', _sync_bidding_space),
        ('bidding_space_actual', 'shandong_px_spot_actual_load_info',
         '', _sync_bidding_space),
        ('dayahead_price', 'shandong_px_reliable_clearing_unit_data',
         "", _sync_price_simple),  # uses member_id internally
        ('realtime_price', 'shandong_px_realtime_clearing_results_query',
         "", _sync_price_simple),
    ]

    member_id = 'b9e64e64a713458eba94c9af05c0a757'

    try:
        remote = pymysql.connect(**REMOTE_DB, connect_timeout=10)
    except Exception as e:
        print(f'Auto-sync: 天机库不可达 ({e}), 跳过')
        conn.close()
        return result

    for local_table, remote_table, extra_where, sync_func in sync_tasks:
        try:
            rcur = remote.cursor()
            if remote_table in ('shandong_px_reliable_clearing_unit_data',
                                'shandong_px_realtime_clearing_results_query'):
                rcur.execute(
                    f"SELECT MAX(date) FROM {remote_table} "
                    f"WHERE member_id = %s AND unit_name LIKE '%%润津%%'",
                    (member_id,)
                )
            else:
                rcur.execute(f"SELECT MAX(date) FROM {remote_table}")
            remote_max = rcur.fetchone()[0]
            rcur.close()

            if remote_max is None:
                result[local_table] = 0
                continue
            remote_max_str = str(remote_max) if isinstance(remote_max, date_type) else remote_max

            lcur = conn.cursor()
            lcur.execute(f"SELECT MAX(date) FROM {local_table}")
            local_max = lcur.fetchone()[0]
            lcur.close()

            if local_max is None or remote_max_str > local_max:
                start = local_max if local_max else remote_max_str
                end = remote_max_str
                print(f'  Auto-syncing {local_table}: {start} ~ {end} ...')
                sync_func(conn, local_table, start, end)
                # Count rows synced
                lcur = conn.cursor()
                lcur.execute(
                    f"SELECT COUNT(*) FROM {local_table} WHERE date >= ? AND date <= ?",
                    (start, end)
                )
                cnt = lcur.fetchone()[0]
                lcur.close()
                result[local_table] = cnt
                print(f'    {cnt} rows synced → {local_table}')
            else:
                result[local_table] = 0
        except Exception as e:
            print(f'  Auto-sync {local_table} skipped: {e}')
            result[local_table] = 0

    # clearing_price: special handling (two remote tables)
    try:
        rcur = remote.cursor()
        rcur.execute(
            "SELECT MAX(date) FROM shandong_px_spot_dayahead_clearing_price "
            "WHERE member_id = %s", (member_id,)
        )
        da_max = rcur.fetchone()[0]
        rcur.execute(
            "SELECT MAX(date) FROM shandong_px_spot_realtime_clearing_price "
            "WHERE member_id = %s", (member_id,)
        )
        rt_max = rcur.fetchone()[0]
        rcur.close()
        remote_max = max(filter(None, [da_max, rt_max]), default=None)

        if remote_max is not None:
            remote_max_str = str(remote_max) if isinstance(remote_max, date_type) else remote_max
            lcur = conn.cursor()
            lcur.execute("SELECT MAX(date) FROM clearing_price")
            local_max = lcur.fetchone()[0]
            lcur.close()
            if local_max is None or remote_max_str > local_max:
                start = local_max if local_max else remote_max_str
                _sync_clearing_price(conn, start, remote_max_str)
    except Exception as e:
        print(f'  Auto-sync clearing_price skipped: {e}')

    # price_forecast
    try:
        rcur = remote.cursor()
        rcur.execute(
            "SELECT MAX(date) FROM algorithm_clearing_price_forecast "
            "WHERE province_id = 14"
        )
        remote_max = rcur.fetchone()[0]
        rcur.close()
        if remote_max is not None:
            remote_max_str = str(remote_max) if isinstance(remote_max, date_type) else remote_max
            lcur = conn.cursor()
            lcur.execute("SELECT MAX(date) FROM price_forecast")
            local_max = lcur.fetchone()[0]
            lcur.close()
            if local_max is None or remote_max_str > local_max:
                start = local_max if local_max else remote_max_str
                _sync_price_forecast(conn, start, remote_max_str)
    except Exception as e:
        print(f'  Auto-sync price_forecast skipped: {e}')

    remote.close()
    conn.close()

    total = sum(result.values())
    if total > 0:
        print(f'Auto-sync: {total} total rows synced across {sum(1 for v in result.values() if v > 0)} tables')
    else:
        print('Auto-sync: 本地库已是最新')

    return result


def status():
    """Print table row counts and date ranges."""
    if not os.path.exists(DB_PATH):
        print(f'Database not found: {DB_PATH}')
        print('Run "python local_db.py sync" first.')
        return

    conn = _get_conn()
    print(f'Database: {DB_PATH}')
    print(f'{"Table":<30} {"Rows":>8}  {"From":>12}  {"To":>12}')
    print('-' * 68)

    total = 0
    for name, cfg in TABLES.items():
        local_name = cfg['local']
        cur = conn.execute(f'SELECT COUNT(*) FROM {local_name}')
        cnt = cur.fetchone()[0]
        total += cnt

        cur = conn.execute(
            f'SELECT MIN(date), MAX(date) FROM {local_name} WHERE date > "2000-01-01"'
        )
        mn, mx = cur.fetchone()
        fr = mn or '—'
        to = mx or '—'
        print(f'{local_name:<30} {cnt:>8,}  {fr:>12}  {to:>12}')

    print('-' * 68)
    print(f'{"Total":<30} {total:>8,}')

    # File size
    size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    print(f'\nFile size: {size_mb:.1f} MB')
    conn.close()


# ── Query helpers (used by other scripts) ──────────────────────────

def query_bidding_space(start: str, end: str,
                        data_type: str = 'forecast') -> dict[str, dict]:
    """Query bidding space from local SQLite.

    Returns:
        {date: {field: [96 values]}} — same format as fetch_data() in bidding_space_viz.py
    """
    from collections import defaultdict

    table = 'bidding_space_forecast' if data_type == 'forecast' else 'bidding_space_actual'
    conn = _get_conn()
    sql = f'''
        SELECT date, time_order, dispatched_load, tie_line_load,
               wind_power, photovoltaic_power, nuclear_power,
               local_power, self_power, bidding_space
        FROM {table}
        WHERE date >= ? AND date <= ?
        ORDER BY date, time_order
    '''
    rows = conn.execute(sql, (start, end)).fetchall()
    conn.close()

    data = defaultdict(lambda: defaultdict(list))
    for d, to, dl, tl, wp, pv, nu, loc, slf, bs in rows:
        ds = d
        data[ds]['直调负荷'].append(dl or 0)
        data[ds]['联络线受电'].append(tl or 0)
        data[ds]['风电总加'].append(wp or 0)
        data[ds]['光伏总加'].append(pv or 0)
        data[ds]['核电总加'].append(nu or 0)
        data[ds]['地方电厂'].append(loc or 0)   # 地方电厂发电总加，预留(分布式光伏用)，不参与bs
        data[ds]['自备机组'].append(slf or 0)
        data[ds]['竞价空间'].append(bs or 0)

    return dict(data)


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == 'status':
        status()

    elif cmd == 'auto-sync':
        auto_sync()

    elif cmd == 'sync':
        start = DEFAULT_START
        end = DEFAULT_END
        tables = None

        i = 1
        while i < len(args):
            if args[i] == '--start' and i + 1 < len(args):
                start = args[i + 1]; i += 2
            elif args[i] == '--end' and i + 1 < len(args):
                end = args[i + 1]; i += 2
            elif args[i] == '--tables' and i + 1 < len(args):
                tables = [t.strip() for t in args[i + 1].split(',')]; i += 2
            else:
                i += 1

        sync(start, end, tables)

    else:
        print(f'Unknown command: {cmd}')
        print('Usage: python local_db.py [sync|status]')