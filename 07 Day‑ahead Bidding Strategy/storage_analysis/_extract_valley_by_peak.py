"""分析：在不同竞价空间最大值（峰值）水平下，2h谷值→储能投运的阈值是否变化。

核心问题：
  - 7-8月保供季节负荷大，竞价空间最大值高→开机台数多→储能投运的2h谷值阈值是否更高？
  - 即：分峰值水平看2h谷值阈值的变化趋势

输出 _tmp_valley_by_peak.json
"""
import os, json
from pathlib import Path
import pymysql, pandas as pd, numpy as np

def _find_root(start):
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        if (cand / ".env").exists():
            return cand
    return Path(__file__).parent.parent.parent

ROOT = _find_root(__file__)
for line in open(ROOT / ".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

HOST = os.getenv("DB_TIANJI_HOST"); PORT = int(os.getenv("DB_TIANJI_PORT", 3306))
USER = os.getenv("DB_TIANJI_USER"); PWD = os.getenv("DB_TIANJI_PASSWORD"); DB = os.getenv("DB_TIANJI_DATABASE")
START, END = "2026-05-01", "2026-07-22"

def main():
    feat = json.load(open(ROOT / "_tmp_similar_features.json", encoding="utf-8"))

    conn = pymysql.connect(host=HOST, port=PORT, user=USER, password=PWD, database=DB,
                           charset="utf8mb4", connect_timeout=10, read_timeout=120)
    sql_q = """SELECT date, time_point, independent_clearing, draw_clearing, independent_number, draw_number, thermal_number
               FROM shandong_px_dayahead_clearing_quantity_number
               WHERE date BETWEEN %s AND %s ORDER BY date, time_point"""
    sql_l = """SELECT date, time_order, dispatched_load_forecast, tie_line_load_forecast,
               wind_power_forecast, photovoltaic_power_forecast, nuclear_power_forecast,
               local_power_forecast, self_power_forecast
               FROM shandong_px_spot_dayahead_load_info
               WHERE date BETWEEN %s AND %s ORDER BY date, time_order"""
    df_q = pd.read_sql(sql_q, conn, params=(START, END))
    df_l = pd.read_sql(sql_l, conn, params=(START, END))
    conn.close()

    df_q["time_order"] = df_q["time_point"].map(lambda tp: int(tp.split(":")[0])*4 + int(tp.split(":")[1])//15)
    df = pd.merge(df_q, df_l, on=["date","time_order"], how="inner")
    df["date"] = pd.to_datetime(df["date"])
    for c in ["independent_clearing","draw_clearing","independent_number","draw_number","thermal_number"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    for c in ["dispatched_load_forecast","tie_line_load_forecast","wind_power_forecast","photovoltaic_power_forecast","nuclear_power_forecast","local_power_forecast","self_power_forecast"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["ind_p"] = df["independent_clearing"]*4
    df["draw_p"] = df["draw_clearing"]*4
    df["bs"] = df["dispatched_load_forecast"] - df["tie_line_load_forecast"] - df["wind_power_forecast"] - df["photovoltaic_power_forecast"] - df["nuclear_power_forecast"] - df["self_power_forecast"]

    daily = df.groupby(df["date"].dt.date).apply(lambda g: pd.Series({
        "bs_max": g["bs"].max(),
        "bs_mean": g["bs"].mean(),
        "ind_max_p": g["ind_p"].abs().max(),
        "ind_avg_p": g["ind_p"].abs().mean(),
        "draw_max_p": g["draw_p"].abs().max(),
        "thermal_num": g["thermal_number"].max(),
        "ind_num": g["independent_number"].max(),
    })).reset_index()
    daily["date_str"] = daily["date"].astype(str)
    daily["month"] = pd.to_datetime(daily["date_str"]).dt.month
    daily["valley_2h"] = daily["date_str"].map(lambda d: feat.get(d, {}).get("valley"))
    daily["peak_2h"] = daily["date_str"].map(lambda d: feat.get(d, {}).get("peak"))
    daily = daily.dropna(subset=["valley_2h"])

    # 按竞价空间最大值（峰值）分箱 —— 反映保供水平/开机台数水平
    # 7-8月保供季节 bs_max 高（30+GW），5-6月较低
    bs_bins = [0, 25000, 28000, 30000, 32000, 999999]
    bs_labels = ["<25GW","25-28GW","28-30GW","30-32GW",">32GW"]
    daily["bs_max_bin"] = pd.cut(daily["bs_max"], bins=bs_bins, labels=bs_labels, include_lowest=True)

    # 按峰值分箱：每个箱内的 valley 阈值（最佳分割点）
    # 储能高意愿 = ind_max_p > 3000
    daily["high_willing"] = daily["ind_max_p"] > 3000

    by_peak = []
    for label in bs_labels:
        sub = daily[daily["bs_max_bin"] == label]
        if len(sub) < 2:
            continue
        # 该箱内 valley 最佳阈值
        best_split = None; best_acc = -1
        val_arr = sub["valley_2h"].values
        for split in np.arange(-10000, 25000, 250):
            pred_high = val_arr < split
            actual_high = sub["high_willing"].values
            acc = (pred_high == actual_high).mean()
            if acc > best_acc:
                best_acc = acc; best_split = float(split)
        by_peak.append({
            "bs_max_bin": label,
            "days": int(len(sub)),
            "bs_max_avg": round(float(sub["bs_max"].mean()),0),
            "thermal_num_avg": round(float(sub["thermal_num"].mean()),0),
            "valley_avg": round(float(sub["valley_2h"].mean()),0),
            "valley_min": round(float(sub["valley_2h"].min()),0),
            "valley_max": round(float(sub["valley_2h"].max()),0),
            "ind_max_avg": round(float(sub["ind_max_p"].mean()),0),
            "ind_avg_avg": round(float(sub["ind_avg_p"].mean()),0),
            "high_willing_days": int(sub["high_willing"].sum()),
            "best_split": round(best_split,0),
            "best_acc": round(float(best_acc),4),
            "corr_valley_ind": round(float(sub["valley_2h"].corr(sub["ind_max_p"])),3) if sub["valley_2h"].std()>0 else None,
        })

    # 按月份分箱
    by_month = []
    for m in sorted(daily["month"].unique()):
        sub = daily[daily["month"] == m]
        if len(sub) < 2:
            continue
        best_split = None; best_acc = -1
        val_arr = sub["valley_2h"].values
        for split in np.arange(-10000, 25000, 250):
            pred_high = val_arr < split
            actual_high = sub["high_willing"].values
            acc = (pred_high == actual_high).mean()
            if acc > best_acc:
                best_acc = acc; best_split = float(split)
        by_month.append({
            "month": int(m),
            "days": int(len(sub)),
            "bs_max_avg": round(float(sub["bs_max"].mean()),0),
            "thermal_num_avg": round(float(sub["thermal_num"].mean()),0),
            "valley_avg": round(float(sub["valley_2h"].mean()),0),
            "ind_max_avg": round(float(sub["ind_max_p"].mean()),0),
            "ind_avg_avg": round(float(sub["ind_avg_p"].mean()),0),
            "high_willing_days": int(sub["high_willing"].sum()),
            "best_split": round(best_split,0),
            "best_acc": round(float(best_acc),4),
            "corr_valley_ind": round(float(sub["valley_2h"].corr(sub["ind_max_p"])),3) if sub["valley_2h"].std()>0 else None,
        })

    # 整体相关：bs_max vs thermal_num
    corr_overall = {
        "bs_max_vs_thermal_num": round(float(daily["bs_max"].corr(daily["thermal_num"])),3),
        "bs_max_vs_ind_max": round(float(daily["bs_max"].corr(daily["ind_max_p"])),3),
        "thermal_num_vs_ind_max": round(float(daily["thermal_num"].corr(daily["ind_max_p"])),3),
        "valley_vs_ind_max": round(float(daily["valley_2h"].corr(daily["ind_max_p"])),3),
    }

    out = {
        "date_range": {"start": START, "end": END, "n_dates": int(len(daily))},
        "by_peak": by_peak,
        "by_month": by_month,
        "corr_overall": corr_overall,
        "daily": daily[["date_str","month","bs_max","bs_max_bin","valley_2h","thermal_num","ind_num","ind_max_p","ind_avg_p","draw_max_p"]].round(1).to_dict(orient="records"),
    }
    out_path = ROOT / "_tmp_valley_by_peak.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"Saved: {out_path}\n")

    print("="*70)
    print("整体相关性:")
    for k,v in corr_overall.items(): print(f"  {k}: {v}")
    print()
    print("按竞价空间峰值分箱（保供水平）:")
    print(f'{"峰值区间":<12}{"天数":>5}{"峰值均":>8}{"火电台数":>8}{"谷值均":>8}{"谷值范围":>16}{"储能最大均":>10}{"高意愿天":>8}{"最佳阈值":>10}{"准确率":>7}')
    for r in by_peak:
        print(f'{r["bs_max_bin"]:<12}{r["days"]:>5}{r["bs_max_avg"]:>8.0f}{r["thermal_num_avg"]:>8.0f}{r["valley_avg"]:>8.0f}{str(r["valley_min"])+"~"+str(r["valley_max"]):>16}{r["ind_max_avg"]:>10.0f}{r["high_willing_days"]:>8}{r["best_split"]:>10.0f}{r["best_acc"]:>7.2f}')
    print()
    print("按月份:")
    print(f'{"月":>4}{"天数":>5}{"峰值均":>8}{"火电台数":>8}{"谷值均":>8}{"储能最大均":>10}{"高意愿天":>8}{"最佳阈值":>10}{"准确率":>7}')
    for r in by_month:
        print(f'{r["month"]:>4}{r["days"]:>5}{r["bs_max_avg"]:>8.0f}{r["thermal_num_avg"]:>8.0f}{r["valley_avg"]:>8.0f}{r["ind_max_avg"]:>10.0f}{r["high_willing_days"]:>8}{r["best_split"]:>10.0f}{r["best_acc"]:>7.2f}')

if __name__ == "__main__":
    main()
