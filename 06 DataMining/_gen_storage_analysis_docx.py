"""生成储能投运分析 Word 文档（汇总全部分析过程与支撑数据）。

输入：本地 JSON/CSV 分析产物
输出：output/储能投运分析报告.docx
"""
import os, json, sqlite3
from pathlib import Path
import pandas as pd, numpy as np
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)
OUT_PATH = OUT_DIR / "储能投运分析报告.docx"


def set_font(run, name="微软雅黑", size=10.5, bold=False, color=None):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    run._element.rPr.rFonts.set(qn('w:eastAsia'), name)


def add_heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        set_font(run, name="微软雅黑", size=16-level*2, bold=True, color=(0x00,0x5a,0xb4))
    return h


def add_para(doc, text, size=10.5, bold=False, color=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_font(run, size=size, bold=bold, color=color)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.5
    return p


def add_table(doc, headers, rows, col_widths=None, font_size=9):
    """添加带样式的表格"""
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = 'Light Grid Accent 1'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    # 表头
    for i, h in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(str(h))
        set_font(run, size=font_size, bold=True)
    # 数据行
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(str(v))
            set_font(run, size=font_size)
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    return t


def add_note(doc, text):
    """添加注释框（灰色背景）"""
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_font(run, size=9, color=(0x66,0x66,0x66))
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.space_after = Pt(6)
    # 加左边框
    pPr = p._p.get_or_add_pPr()
    pBdr = pPr.makeelement(qn('w:pBdr'), {})
    left = pBdr.makeelement(qn('w:left'), {qn('w:val'):'single', qn('w:sz'):'18', qn('w:color'):'005ab4', qn('w:space'):'8'})
    pBdr.append(left)
    pPr.append(pBdr)
    shd = pPr.makeelement(qn('w:shd'), {qn('w:val'):'clear', qn('w:fill'):'F5F5F5'})
    pPr.append(shd)
    return p


def main():
    doc = Document()
    # 页边距
    for section in doc.sections:
        section.left_margin = Cm(2)
        section.right_margin = Cm(2)
        section.top_margin = Cm(2.2)
        section.bottom_margin = Cm(2.2)

    # ===== 封面标题 =====
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("山东电力现货市场\n储能充电投运分析与预测报告")
    set_font(run, size=22, bold=True, color=(0x00,0x5a,0xb4))
    title.paragraph_format.space_before = Pt(40)
    title.paragraph_format.space_after = Pt(20)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub.add_run("基于 2025-07 ~ 2026-07 历史 773 天数据\n润津储能电站 / 天机数据库")
    set_font(run, size=12, color=(0x66,0x66,0x66))
    sub.paragraph_format.space_after = Pt(40)

    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = info.add_run(f"生成日期：2026-07-22\n数据范围：2025-07-01 ~ 2026-07-22（773 天）")
    set_font(run, size=10.5, color=(0x88,0x88,0x88))

    doc.add_page_break()

    # ===== 摘要 =====
    add_heading(doc, "摘要", 1)
    add_para(doc, "本报告基于山东电力现货市场 2025-07 ~ 2026-07 共 773 天历史数据，系统分析储能+抽蓄投运规律，建立次日储能充电投运的双变量判断模型。")
    add_para(doc, "核心结论：")
    add_para(doc, "1. 储能投运的根本动力是低价充电获利，当火电被迫压到最小出力运行方式时，现货电价触及 -80 元/MWh 地板价，储能深度充电套利。", size=10)
    add_para(doc, "2. 主判据为竞价空间（bs）2h谷值：谷值<0 时 98.6% 触地板（必投）；谷值>20GW 时仅 11%（不投）。", size=10)
    add_para(doc, "3. 辅判据为火电峰值台数：开停机有费用，为保峰值供应少停机→峰值台数决定谷段最小出力地板线（<60台→7856MW，>100台→22421MW）。", size=10)
    add_para(doc, "4. 双变量矩阵在中间区间（10-20GW）起关键修正作用：少开机可深压→触地板概率高；保供多开机压不下去→概率低。", size=10)
    add_para(doc, "5. 完整逻辑链：bs峰值→峰值台数→谷段最小出力地板线→bs谷值vs地板线→是否触地板→储能投运强度。", size=10)

    # ===== 第一章：数据基础 =====
    add_heading(doc, "一、数据基础与分析框架", 1)
    add_heading(doc, "1.1 数据源", 2)
    add_para(doc, "天机数据库（tianrun_new @ 阿里云RDS）+ 本地 SQLite 缓存（data/cache/local.db）。")
    add_table(doc,
        ["表名", "用途", "数据范围"],
        [
            ["shandong_px_spot_dayahead_load_info", "日前负荷预测（直调/联络/风/光/核/地方/自备）", "2021-11 ~ 2026-07"],
            ["shandong_px_spot_actual_load_info", "实际负荷信息", "同上"],
            ["shandong_px_dayahead_clearing_quantity_number", "出清电量+台数（火电/储能/抽蓄/虚拟/公用）", "2024-06 ~ 2026-07"],
            ["shandong_px_reliable_clearing_unit_data", "润津日前出清价（96点）", "2026-01 ~ 2026-07"],
            ["shandong_px_realtime_clearing_results_query", "润津实时出清价（96点）", "2025-11 ~ 2026-07"],
        ], col_widths=[6, 6, 4], font_size=9)
    add_para(doc, "")
    add_para(doc, "竞价空间标准定义（5项）：")
    add_para(doc, "竞价空间 = 直调负荷 − (联络线受电 + 风电 + 光伏 + 核电 + 自备机组)", bold=True, color=(0x00,0x5a,0xb4))
    add_para(doc, "功率换算：出清电量（MWh）× 4 = 功率（MW），因每个时点为15分钟（÷0.25h）= ×4。")

    add_heading(doc, "1.2 分析框架", 2)
    add_para(doc, "本分析围绕「次日储能+抽蓄是否投运、投运多强」展开，分四个层次：")
    add_para(doc, "① 规律挖掘：光伏最大值/2h谷值与储能投运的相关性", size=10)
    add_para(doc, "② 机制验证：削峰填谷、充放效率、火电vs储能替代关系", size=10)
    add_para(doc, "③ 阈值确定：单变量阈值 + 双变量概率矩阵", size=10)
    add_para(doc, "④ 模型落地：similar_day_analysis.py 的 compute_storage_recommendation()", size=10)

    # ===== 第二章：光伏最大值法 =====
    add_heading(doc, "二、光伏最大值阈值法（第一轮分析）", 1)
    add_para(doc, "思路：次日10:15天机库发布日前光伏预测，取96点最大值，判断储能投运意愿。")
    add_heading(doc, "2.1 相关性", 2)
    add_table(doc,
        ["指标", "相关系数 r", "判别力"],
        [
            ["光伏最大值 vs 独立储能最大功率", "+0.79", "强"],
            ["光伏最大值 vs 独立储能平均功率", "+0.81", "强"],
            ["光伏最大值 vs 抽蓄最大功率", "+0.55", "中等"],
            ["光伏最大值 vs 独立储能台数", "+0.41", "弱"],
        ], col_widths=[7,4,4], font_size=9)
    add_para(doc, "")
    add_para(doc, "结论：投运意愿主要通过功率强度调节（r=0.79-0.81），而非开停机台数（r=0.41）。")
    add_heading(doc, "2.2 分箱统计与阈值", 2)
    add_table(doc,
        ["光伏最大值", "天数", "储能最大功率(MW)", "抽蓄最大功率(MW)"],
        [
            ["< 5 GW", "1", "6233", "860"],
            ["5-10 GW", "9", "2081", "1034"],
            ["10-15 GW", "7", "1630", "1259"],
            ["15-18 GW", "5", "1974", "824"],
            ["18-20 GW", "6", "5316", "2257"],
            ["20-22 GW", "18", "6759", "3197"],
            ["> 22 GW", "34", "7469", "2910"],
        ], col_widths=[3.5,2,4,4], font_size=9)
    add_para(doc, "")
    add_para(doc, "关键阈值：光伏最大值 ≥ 18 GW → 储能高投运，准确率 93.8%。", bold=True, color=(0x52,0xc4,0x1a))
    add_note(doc, "局限：光伏最大值只反映单一光伏出力，未综合负荷和风电。节假日修正因子需额外考虑。")

    # ===== 第三章：2h谷值法 =====
    add_heading(doc, "三、竞价空间2h谷值阈值法（主判据）", 1)
    add_para(doc, "改进：2h谷值是竞价空间曲线连续8点（2小时）的最低均值，已综合光伏+负荷+风电，比单一光伏最大值更贴近调度本质。")
    add_heading(doc, "3.1 谷值与光伏最大值对比", 2)
    add_table(doc,
        ["信号 vs 储能最大功率", "r 值", "性质"],
        [
            ["光伏最大值", "+0.79", "正相关"],
            ["2h谷值", "−0.87", "负相关，更强"],
        ], col_widths=[6,3,4], font_size=9)
    add_para(doc, "")
    add_para(doc, "2h谷值与光伏最大值本身 r=−0.83（强负相关），说明谷值由光伏决定，但已综合负荷和风电影响。")
    add_heading(doc, "3.2 谷值 → 触地板概率（773天日级统计）", 2)
    add_table(doc,
        ["2h谷值", "天数", "触地板天", "概率", "投运意愿"],
        [
            ["< 0（负）", "138", "136", "98.6%", "极强"],
            ["0-5 GW", "73", "60", "82.2%", "强"],
            ["5-10 GW", "111", "69", "62.2%", "中强"],
            ["10-15 GW", "150", "68", "45.3%", "中"],
            ["15-20 GW", "240", "77", "32.1%", "弱中"],
            ["> 20 GW", "1012", "112", "11.1%", "弱"],
        ], col_widths=[3,2,2.5,2,2.5], font_size=9)
    add_para(doc, "")
    add_para(doc, "规律：谷值<0→98.6%触地板；谷值>20GW→仅11%。阈值 17.5GW，准确率 94.9%。", bold=True, color=(0x00,0x5a,0xb4))

    add_heading(doc, "3.3 谷值 → 充电功率推荐档", 2)
    add_table(doc,
        ["2h谷值", "充电功率(MW)", "意愿", "2h充电能量(MWh)"],
        [
            ["< 0", "-9000", "极强", "18000"],
            ["0-5 GW", "-9600", "强", "19200"],
            ["5-10 GW", "-8400", "中强", "16800"],
            ["10-15 GW", "-7700", "中", "15400"],
            ["15-20 GW", "-6500", "弱中", "13000"],
            ["> 20 GW", "-3000", "弱", "6000"],
        ], col_widths=[3,3.5,2.5,3.5], font_size=9)

    # ===== 第四章：机制验证 =====
    add_heading(doc, "四、储能削峰填谷机制验证", 1)
    add_para(doc, "验证假设：调度用储能+抽蓄把竞价空间的峰谷削平，使火电出力变成稳定直线。")
    add_heading(doc, "4.1 削峰填谷统计", 2)
    add_table(doc,
        ["指标", "结果"],
        [
            ["火电平均CV（变异系数）", "0.28（平稳）"],
            ["竞价空间平均CV", "0.99（波动剧烈）"],
            ["火电比bs更平稳的天数", "77/80 天（96%）"],
            ["储能总功率 ↔ bs日内偏差", "r=0.81（强相关）"],
            ["填谷天数（bs最低点处储能充电）", "79/80 天（98.75%）"],
            ["削峰天数（bs最高点处储能放电）", "73/80 天（91.25%）"],
            ["bs波幅 → 隐含火电波幅", "36 GW → 27 GW（压缩27%）"],
        ], col_widths=[9,5], font_size=9)
    add_para(doc, "")
    add_para(doc, "结论：削峰填谷机制成立但「部分削平」——火电仍保留28%波动，储能容量有限。", bold=True)

    add_heading(doc, "4.2 充电来源验证", 2)
    add_para(doc, "日充电总量与午间（11-14点）光伏能量 r=0.75（强正相关），与风电 r=−0.18（弱）。")
    add_para(doc, "运营逻辑验证：光伏预测→预期午间bs低谷→安排充电。")
    add_heading(doc, "4.3 充放效率验证", 2)
    add_para(doc, "放电/充电中位数 = 0.89（综合效率89%），符合充放转换损耗。「充电先定、放电=充电×0.89」逻辑成立。")

    add_heading(doc, "4.4 火电vs储能替代关系", 2)
    add_para(doc, "火电开机台数 ↔ 储能最大功率 r=−0.66（负相关）。")
    add_para(doc, "保供日火电大量开机（>100台）→ 储能功率普遍低（500-2700MW）；非保供日火电少开（<85台）→ 储能高投运（5000-7800MW）。")

    # ===== 第五章：双变量判据 =====
    add_heading(doc, "五、双变量判据：bs谷值 × 火电峰值台数", 1)
    add_para(doc, "引入辅判据的动机：开停机有费用，为保证峰值供应减少开停机，峰值台数影响谷段最小出力——这是单变量谷值法在中间区间（10-20GW）的盲区。")
    add_heading(doc, "5.1 峰值台数 → 谷段最小出力地板线（核心约束）", 2)
    add_table(doc,
        ["火电峰值台数", "天数", "谷段最小出力(MW)", "触地板率"],
        [
            ["< 60", "1", "7856", "100%"],
            ["60-70", "9", "9573", "100%"],
            ["70-80", "53", "11193", "96%"],
            ["80-90", "112", "12733", "96%"],
            ["90-100", "122", "17035", "70%"],
            ["> 100", "476", "22421", "56%"],
        ], col_widths=[3,2,4,3], font_size=9)
    add_para(doc, "")
    add_para(doc, "规律：峰值台数越多→谷段最小出力被抬高→火电压不到地板→触地板概率下降。", bold=True, color=(0xd1,0x34,0x38))

    add_heading(doc, "5.2 触地板概率矩阵（bs谷值 × 峰值台数）", 2)
    add_table(doc,
        ["bs谷值 \\ 峰值台数", "<60", "60-70", "70-80", "80-90", "90-100", ">100"],
        [
            ["< 0", "100%", "100%", "100%", "100%", "100%", "100%"],
            ["0-5 GW", "—", "—", "100%", "95%", "94%", "93%"],
            ["5-10 GW", "—", "—", "100%", "100%", "100%", "97%"],
            ["10-15 GW", "—", "—", "—", "88%", "83%", "96%"],
            ["15-20 GW", "—", "—", "0%", "75%", "70%", "84%"],
            ["> 20 GW", "—", "—", "0%", "50%", "29%", "34%"],
        ], col_widths=[3,2,2,2,2,2,2], font_size=8.5)
    add_para(doc, "")
    add_para(doc, "谷值<0无论台数100%触地板；谷值>20GW且台数>90仅29-34%；中间区间靠峰值台数修正。")

    add_heading(doc, "5.3 回归公式", 2)
    add_table(doc,
        ["回归", "公式", "R²"],
        [
            ["bs峰值 → 火电峰值台数", "peak_units = 0.0019 × bs_peak + 13.12", "0.65"],
            ["bs谷值 → 火电谷值台数", "valley_units = 0.0011 × bs_valley + 79.88", "0.55"],
        ], col_widths=[5,7,2], font_size=9)

    add_heading(doc, "5.4 中间区间（10-20GW）修正规则", 2)
    add_para(doc, "• 峰值台数 > 100（保供多开机）：充电功率降一档（+1500MW向0靠），谷段压不下去")
    add_para(doc, "• 峰值台数 ≤ 80（少开机可深压）：充电功率升一档（−1500MW远离0），谷段可深压")

    # ===== 第六章：地板价时刻特征 =====
    add_heading(doc, "六、地板价时刻特征统计", 1)
    add_para(doc, "历史 13437 个触地板时刻（522天，占67.5%），典型画像：")
    add_table(doc,
        ["指标", "地板时刻", "非地板时刻", "差异"],
        [
            ["竞价空间(MW)", "11844", "36729", "−24885"],
            ["火电出清(MW)", "15746", "29588", "−13842"],
            ["火电开机台数", "89", "104", "−15"],
            ["独立储能功率(MW)", "−1254（充电）", "+238", "−1491"],
            ["抽蓄功率(MW)", "−1323（抽水）", "+204", "−1528"],
        ], col_widths=[4,3.5,3.5,3], font_size=9)
    add_para(doc, "")
    add_para(doc, "地板时刻=bs低+火电低+台数少+储能+抽蓄深度充电。")

    add_heading(doc, "6.1 地板时刻按月分布", 2)
    add_table(doc,
        ["月份", "地板点数", "bs均值", "火电均值", "台数", "储能MW", "抽蓄MW"],
        [
            ["3-5月（过渡季）", "5022", "0~12800", "12000-15000", "66-86", "-1300", "-1400"],
            ["6月（初夏）", "1563", "6148", "13760", "79", "-1400", "-1640"],
            ["7-8月（保供）", "909", "18800-22300", "18700-19700", "102-106", "-1150", "-1140"],
            ["9-11月", "2242", "13000-18000", "14000-16800", "83-98", "-1200", "-1050"],
            ["12-2月（供暖）", "3701", "14000-24000", "18200-20900", "105-115", "-1000", "-1000"],
        ], col_widths=[3.5,2,2.5,2.5,2,2,2], font_size=8.5)
    add_para(doc, "")
    add_para(doc, "5月是地板价最频繁月（bs谷值为负，火电压到11000-12000MW）；7-8月地板少（保供负荷高）。")

    add_heading(doc, "6.2 火电年度最低出力", 2)
    add_para(doc, "历史最低火电出清：7821 MW（2026-05-09 12:30），5月极值。限电临界点。")
    add_table(doc,
        ["日期", "火电日最低(MW)", "当日峰值(MW)", "新能源峰值(MW)"],
        [
            ["2026-05-09", "7821", "19683", "24188"],
            ["2026-05-05", "7856", "14916", "26114"],
            ["2026-05-06", "8257", "22879", "24219"],
            ["2026-05-01", "8467", "27345", "21388"],
        ], col_widths=[3.5,3.5,3.5,3.5], font_size=9)
    add_para(doc, "")
    add_para(doc, "05-09 12:30 限电临界：火电7821MW（压到最低）+ 储能-7755MW（满充）+ 抽蓄-2840MW，新能源13940MW仍未消纳→限电。")

    # ===== 第七章：完整逻辑链与决策规则 =====
    add_heading(doc, "七、完整逻辑链与决策规则", 1)
    add_heading(doc, "7.1 逻辑链", 2)
    add_para(doc, "次日预测（10:15天机库发布日前负荷预测）→ 计算bs 96点 → 找2h谷值/峰值 → bs峰值回归峰值台数 → 查最小出力地板线 → bs谷值vs地板线 → 是否触地板 → 储能投运强度。")
    add_note(doc, "谷值<地板线 → 火电必压到最小出力 → 触-80地板价 → 储能强投充电；谷值>地板线 → 火电无需压到最小 → 无地板价 → 储能弱投。")

    add_heading(doc, "7.2 投运判断三档决策表", 2)
    add_table(doc,
        ["谷值", "峰值台数", "触地板概率", "储能投运", "充电功率"],
        [
            ["< 0", "任意", "98-100%", "必投", "-9000 MW"],
            ["0-10", "任意", "62-100%", "必投", "-8400~-9600 MW"],
            ["10-15", "≤80", "83-100%", "投", "-7700~-9600（升档）"],
            ["10-15", ">100", "96%", "投", "-7700 MW"],
            ["15-20", "≤80", "0-75%", "中等", "-6500 MW"],
            ["15-20", ">100", "84%", "中等", "-3000（降档）"],
            ["> 20", ">90", "11-34%", "不投", "-3000 MW"],
        ], col_widths=[2.5,2.5,2.5,2,3.5], font_size=8.5)

    add_heading(doc, "7.3 季节修正", 2)
    add_table(doc,
        ["季节", "月份", "bs谷值", "火电最小出力", "投运倾向"],
        [
            ["春过渡季", "4-5", "谷值最低（可<0）", "8000-12000 MW", "最强"],
            ["初夏", "6", "谷值中等", "13000-16000 MW", "强"],
            ["夏保供", "7-8", "谷值高", "18000-29000 MW", "弱（保供挤占）"],
            ["秋过渡", "9-10", "谷值中等", "13000-19000 MW", "中"],
            ["供暖季", "11-3", "谷值偏高", "16000-22000 MW", "中弱"],
        ], col_widths=[2.5,2,3,4,2.5], font_size=9)
    add_para(doc, "")
    add_para(doc, "节假日修正：负荷低即使光伏正常投运也骤降（如05-19光伏7-8GW但充电仅0.7GWh），判断时降一档。")

    # ===== 第八章：案例验证 =====
    add_heading(doc, "八、案例验证：2026-07-22", 1)
    add_para(doc, "以0722为例验证双变量判据模型。")
    add_table(doc,
        ["指标", "值", "说明"],
        [
            ["2h谷值", "5217 MW", "11:30 中午谷"],
            ["2h峰值", "42965 MW", "19:45 晚间峰"],
            ["预测峰值台数", "95台", "0.0019×42965+13.12"],
            ["预测谷值台数", "86台", "0.0011×5217+79.88"],
            ["谷段最小出力地板线", "17035 MW", "峰值95台对应"],
            ["触地板概率", "100%", "谷值5217<地板线17035"],
            ["★ 谷段充电推荐", "-8400 MW（中强）", "16800 MWh(2h)"],
            ["★ 峰段放电推荐", "+4500 MW", "14952 MWh(2h)"],
        ], col_widths=[4,4,5], font_size=9)
    add_para(doc, "")
    add_para(doc, "0722判定：谷值5217远低于地板线17035 → 火电必压到最小出力 → 100%触地板 → 储能强投。", bold=True, color=(0x52,0xc4,0x1a))

    add_heading(doc, "8.1 典型场景对比", 2)
    add_table(doc,
        ["场景", "峰值", "谷值", "峰台", "地板线", "概率", "谷充"],
        [
            ["5月谷值负", "25000", "-3000", "61", "9573", "100%", "-9000(极强)"],
            ["5月谷值低", "30000", "3000", "70", "11193", "100%", "-9600(强)"],
            ["中间区少开机", "30000", "12000", "70", "11193", "—", "-9600(中强,升档)"],
            ["中间区保供", "55000", "12000", "118", "22421", "96%", "-3000(弱中,降档)"],
            ["7月保供高谷值", "55000", "25000", "118", "22421", "34%", "-3000(弱)"],
        ], col_widths=[3,2,2,1.5,2,2,3.5], font_size=8.5)
    add_para(doc, "")
    add_para(doc, "中间区（谷值12000）修正效果：少开机→升档-9600MW；保供多开机→降档-3000MW。")

    # ===== 第九章：相似日参考机制 =====
    add_heading(doc, "九、相似日参考机制", 1)
    add_para(doc, "当判断无十足把握时，可用相似日历史实际投运作参照。")
    add_heading(doc, "9.1 相似度算法（5维度加权）", 2)
    add_table(doc,
        ["维度", "权重", "计算方式"],
        [
            ["2h谷值", "30%", "1−|候选谷值−目标谷值|/max(所有谷值)"],
            ["2h峰值", "25%", "1−|候选峰值−目标峰值|/max(所有峰值)"],
            ["谷值时段", "15%", "同段=1.0，邻段=0.5，跨段=0.0"],
            ["峰值时段", "10%", "同上"],
            ["曲线形状", "20%", "Pearson相关系数"],
        ], col_widths=[3,2,8], font_size=9)
    add_para(doc, "")
    add_para(doc, "季节Bonus：保供月（7-8/12-2）本年同保供+0.12、去年保供+0.10；过渡季去年同季+0.08。")
    add_heading(doc, "9.2 0722 Top10 相似日", 2)
    add_table(doc,
        ["排名", "日期", "得分", "峰谷差(MW)", "谷值时段", "相关系数"],
        [
            ["1", "2026-07-10", "1.0904", "29975", "11:00", "0.9940"],
            ["2", "2026-07-18", "1.0702", "41892", "11:45", "0.9951"],
            ["3", "2026-07-05", "1.0678", "28137", "10:30", "0.9673"],
            ["4", "2026-07-09", "1.0542", "28293", "11:45", "0.9943"],
            ["5", "2026-07-12", "1.0311", "22212", "09:15", "0.9666"],
        ], col_widths=[1.5,3,2.5,3,2.5,2.5], font_size=9)

    # ===== 第十章：实施与产出 =====
    add_heading(doc, "十、实施路径与产出文件", 1)
    add_heading(doc, "10.1 实施步骤", 2)
    add_para(doc, "1. 10:15 天机库发布次日日前负荷预测（shandong_px_spot_dayahead_load_info）")
    add_para(doc, "2. local_db.py sync 同步到本地库 → 计算 bs 96点（5项公式）")
    add_para(doc, "3. similar_day_analysis.py compute 重算所有日期特征（2h谷值/峰值/时段）")
    add_para(doc, "4. similar_day_analysis.py YYYY-MM-DD 生成含储能充放推荐面板的HTML")
    add_para(doc, "5. 推荐面板含9张卡片：2h谷值/谷台数/谷充推荐/2h峰值/峰台数/峰放推荐/触地板概率/最小出力地板线/谷值vs地板线")

    add_heading(doc, "10.2 产出文件清单", 2)
    add_table(doc,
        ["文件", "说明"],
        [
            ["06 DataMining/similar_day_analysis.py", "相似日分析+储能推荐主脚本"],
            ["06 DataMining/local_db.py", "本地库同步（5项bs公式）"],
            ["07 Price_Forcast/储能充放业务分析框架.md", "业务框架+判断手册附录（单一文档）"],
            ["竞价空间相似日分析.md", "相似日算法文档"],
            ["output/竞价空间分析结果/相似日分析_2026-07-22.html", "案例HTML（含推荐面板）"],
            ["output/竞价空间分析结果/储能出清功率分析.html", "储能出清基础分析"],
            ["output/竞价空间分析结果/储能削峰填谷验证.html", "削峰填谷机制验证"],
            ["output/竞价空间分析结果/储能两步逻辑验证.html", "两步逻辑（总量+分布）"],
            ["output/竞价空间分析结果/光伏阈值_储能投运意愿.html", "光伏最大值法"],
            ["output/竞价空间分析结果/2h谷值_储能投运意愿.html", "2h谷值法"],
            ["output/竞价空间分析结果/谷值阈值_分峰值水平.html", "分峰值水平阈值"],
        ], col_widths=[8,7], font_size=9)

    # ===== 附录 =====
    add_heading(doc, "附录：地板价触发机制", 1)
    add_para(doc, "储能投运的根本动力是低价充电获利。当火电被迫压到最小出力运行方式时，现货电价触及-80元/MWh地板价。")
    add_para(doc, "触地板充要条件：bs谷值 < 当日开机火电最小出力总功率估算值 → 火电压到最小出力 → -80地板价 → 储能低价充电获利窗口。")
    add_para(doc, "限电临界：新能源出力 > 负荷 − 火电最小出力 − 储能充电上限 − 抽蓄充电上限 → 启动限电（弃风弃光）。")
    add_para(doc, "历史触地板时刻522天（67.5%），bs均值11844MW，火电15746MW，台数89台，储能-1254MW+抽蓄-1323MW深度充电。")

    # 保存
    doc.save(OUT_PATH)
    print(f"Saved: {OUT_PATH}")
    print(f"Size: {OUT_PATH.stat().st_size:,} bytes")

if __name__ == "__main__":
    main()
