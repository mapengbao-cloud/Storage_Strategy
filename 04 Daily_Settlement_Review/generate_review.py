import openpyxl
import os

BASE = r'E:\DataWork\Storage\04 Daily_Settlement_Review'
ASSETS = os.path.join(BASE, 'assets')
OUTPUT = os.path.join(BASE, 'output')
os.makedirs(OUTPUT, exist_ok=True)

TEMPLATE_PATH = os.path.join(ASSETS, '0504-日结算收益复盘.xlsx')
DATES = ['0511', '0512', '0513', '0514', '0515', '0516']

# Sheet mapping: template sheet name → (source file type, source sheet name)
# source_file_type: 'charge' | 'discharge' | 'rt'
SHEET_MAP = {
    '充电日清算费用': ('charge', '日清算数据'),
    '放电日清算费用': ('discharge', '日清算费用'),
    '充放测算':          ('rt', '充放测算'),
    '报价及预中标':       ('rt', '报价及预中标'),
    '容量分摊系数':       ('rt', '容量分摊系数'),
}


def convert_to_numeric(ws):
    """Convert string values that look like numbers to float/int. Skips formula strings."""
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if _is_merged_cell(cell) or cell.value is None:
                continue
            if not isinstance(cell.value, str):
                continue
            if cell.value.startswith('='):
                continue
            s = cell.value.strip()
            try:
                v = float(s)
                if v == int(v) and '.' not in s and 'e' not in s.lower():
                    cell.value = int(v)
                else:
                    cell.value = v
            except ValueError:
                pass


def _is_merged_cell(cell):
    """Check if a cell is a non-writable MergedCell."""
    return type(cell).__name__ == 'MergedCell'


def write_values(target_ws, source_ws):
    """Write non-None values from source_ws into target_ws.
    Only overwrites cells where source has a value; preserves template-only cells
    that have no corresponding data in the source (e.g. 充放测算 N6:O8)."""
    for row in source_ws.iter_rows(min_row=1, max_row=source_ws.max_row, max_col=source_ws.max_column):
        for src_cell in row:
            if src_cell.value is None:
                continue
            tgt_cell = target_ws.cell(row=src_cell.row, column=src_cell.column)
            if not _is_merged_cell(tgt_cell):
                tgt_cell.value = src_cell.value


def generate_review(date_mmdd):
    """Generate daily settlement review using 0504 template, replacing data only."""
    day = date_mmdd[2:4]
    date_iso = f'2026-05-{day}'

    charge_stmt = os.path.join(ASSETS, f'6052-{date_iso}德州润津储能科技有限公司结算单-充电.xlsx')
    discharge_stmt = os.path.join(ASSETS, f'6052-{date_iso}德州润津储能科技有限公司结算单-放电.xlsx')
    rt_review = os.path.join(ASSETS, f'{date_mmdd}-实时机组组合收益复盘.xlsx')
    output_path = os.path.join(OUTPUT, f'{date_mmdd}-日结算收益复盘.xlsx')

    for f in [charge_stmt, discharge_stmt, rt_review]:
        if not os.path.exists(f):
            print(f'  SKIP: Missing source file {os.path.basename(f)}')
            return False

    # Load settlement statements with data_only=True (plain values, no formulas)
    wb_charge = openpyxl.load_workbook(charge_stmt, data_only=True)
    wb_discharge = openpyxl.load_workbook(discharge_stmt, data_only=True)
    # Load RT review with data_only=False to preserve formulas (cache is empty for 0511-0516)
    wb_rt = openpyxl.load_workbook(rt_review, data_only=False)

    # Load template
    wb_target = openpyxl.load_workbook(TEMPLATE_PATH)

    # Replace data in each sheet
    for sheet_name, (src_type, src_sheet_name) in SHEET_MAP.items():
        target_ws = wb_target[sheet_name]

        if src_type == 'charge':
            source_ws = wb_charge[src_sheet_name]
        elif src_type == 'discharge':
            source_ws = wb_discharge[src_sheet_name]
        else:  # rt
            source_ws = wb_rt[src_sheet_name]

        write_values(target_ws, source_ws)
        convert_to_numeric(target_ws)

    wb_target.save(output_path)

    wb_charge.close()
    wb_discharge.close()
    wb_rt.close()
    wb_target.close()

    print(f'  Generated: {os.path.basename(output_path)}')
    return True


if __name__ == '__main__':
    print(f'Template: {os.path.basename(TEMPLATE_PATH)}')
    print(f'Generating daily settlement reviews for dates: {", ".join(DATES)}\n')
    for d in DATES:
        generate_review(d)
    print('\nDone.')
