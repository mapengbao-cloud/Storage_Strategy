"""快速规律：日前光伏最大预测功率 → 次日储能+抽蓄投运意愿。
输出 _tmp_pv_storage_willingness.json
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

def to_tp(to):
    m = to * 15
    return f"{m//60:02d}:{m%60:02d}"

def main():
    conn = pymysql.connect(host=HOST, port=PORT, user=USER, password=PWD, database=DB,
                           charset="utf8mb4", connect_timeout=10, read_timeout=120)
    sql_q = """SELECT date, time_point, independent_clearing, draw_clearing,
               independent_number, draw_number
               FROM shandong_px_dayahead_clearing_quantity_number
               WHERE date BETWEEN %s AND %s ORDER BY date, time_point"""
    sql_l = """SELECT date, time_order, photovoltaic_power_forecast
               FROM shandong_px_spot_dayahead_load_info
               WHERE date BETWEEN %s AND %s ORDER BY date, time_order"""
    df_q = pd.read_sql(sql_q, conn, params=(START, END))
    df_l = pd.read_sql(sql_l, conn, params=(START, END))
    conn.close()

    df_q["time_order"] = df_q["time_point"].map(lambda tp: int(tp.split(":")[0])*4 + int(tp.split(":")[1])//15)
    df = pd.merge(df_q, df_l, on=["date","time_order"], how="inner")
    df["date"] = pd.to_datetime(df["date"])
    for c in ["independent_clearing","draw_clearing","independent_number","draw_number","photovoltaic_power_forecast"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    df["ind_p"] = df["independent_clearing"]*4   # 独立储能功率 MW
    df["draw_p"] = df["draw_clearing"]*4          # 抽蓄功率 MW
    # 投运功率 = 充电+放电绝对值（|净功率|），表示储能/抽蓄的工作强度
    df["storage_ps_work"] = df["ind_p"].abs() + df["draw_p"].abs()
    df["ind_abs"] = df["ind_p"].abs()
    df["draw_abs"] = df["draw_p"].abs()

    # 日级统计
    daily = df.groupby(df["date"].dt.date).apply(lambda g: pd.Series({
        "pv_max": g["photovoltaic_power_forecast"].max(),       # 日前光伏预测最大值 MW
        "ind_max_p": g["ind_p"].abs().max(),                   # 独立储能最大功率(绝对值)
        "ind_avg_p": g["ind_p"].abs().mean(),                  # 独立储能平均功率(绝对值)
        "draw_max_p": g["draw_p"].abs().max(),                 # 抽蓄最大功率(绝对值)
        "draw_avg_p": g["draw_p"].abs().mean(),                # 抽蓄平均功率(绝对值)
        "storage_max_p": g["storage_ps_work"].max(),            # 储能+抽蓄最大功率
        "storage_avg_p": g["storage_ps_work"].mean(),           # 储能+抽蓄平均功率
        "ind_num": g["independent_number"].max(),              # 独立储能投运台数
        "draw_num": g["draw_number"].max(),                    # 抽蓄投运台数
        "ind_active": (g["ind_p"].abs() > 10).sum(),           # 独立储能活跃点数(>10MW)
        "draw_active": (g["draw_p"].abs() > 10).sum(),          # 抽蓄活跃点数
    })).reset_index()
    daily["date"] = daily["date"].astype(str)

    # 相关性
    corr = {
        "pv_max_vs_ind_max": daily["pv_max"].corr(daily["ind_max_p"]),
        "pv_max_vs_ind_avg": daily["pv_max"].corr(daily["ind_avg_p"]),
        "pv_max_vs_draw_max": daily["pv_max"].corr(daily["draw_max_p"]),
        "pv_max_vs_draw_avg": daily["pv_max"].corr(daily["draw_avg_p"]),
        "pv_max_vs_storage_max": daily["pv_max"].corr(daily["storage_max_p"]),
        "pv_max_vs_storage_avg": daily["pv_max"].corr(daily["storage_avg_p"]),
        "pv_max_vs_ind_num": daily["pv_max"].corr(daily["ind_num"]),
        "pv_max_vs_draw_num": daily["pv_max"].corr(daily["draw_num"]),
        "pv_max_vs_ind_active": daily["pv_max"].corr(daily["ind_active"]),
    }

    # 按光伏最大值分箱统计
    bins = [0, 5000, 10000, 15000, 18000, 20000, 22000, 999999]
    labels = ["<5GW","5-10GW","10-15GW","15-18GW","18-20GW","20-22GW",">22GW"]
    daily["pv_bin"] = pd.cut(daily["pv_max"], bins=bins, labels=labels, include_lowest=True)
    binned = daily.groupby("pv_bin", observed=True).agg(
        days=("date","count"),
        ind_max_avg=("ind_max_p","mean"),
        ind_avg_avg=("ind_avg_p","mean"),
        draw_max_avg=("draw_max_p","mean"),
        draw_avg_avg=("draw_avg_p","mean"),
        storage_max_avg=("storage_max_p","mean"),
        storage_avg_avg=("storage_avg_p","mean"),
        ind_num_avg=("ind_num","mean"),
        draw_num_avg=("draw_num","mean"),
        ind_active_avg=("ind_active","mean"),
    ).reset_index()
    binned["pv_bin"] = binned["pv_bin"].astype(str)

    # 阈值判断：光伏最大值 > X 时储能投运意愿高
    # 定义"高意愿" = 独立储能最大功率 > 3000MW（经验阈值）
    threshold_high = 3000
    daily["high_willing"] = daily["ind_max_p"] > threshold_high
    # 找最佳分割点：哪个 pv_max 阈值能最好地区分高低意愿
    best_split = None
    best_score = -1
    pv_arr = daily["pv_max"].values
    for split in np.arange(8000, 23000, 500):
        pred_high = pv_arr > split
        actual_high = daily["high_willing"].values
        # 准确率
        acc = (pred_high == actual_high).mean()
        if acc > best_score:
            best_score = acc
            best_split = float(split)

    out = {
        "date_range": {"start": START, "end": END, "n_dates": int(len(daily))},
        "daily": daily.round(1).to_dict(orient="records"),
        "corr": {k: round(float(v),4) for k,v in corr.items() if not pd.isna(v)},
        "binned": binned.round(1).to_dict(orient="records"),
        "threshold_high": threshold_high,
        "best_split": round(best_split,0),
        "best_split_acc": round(float(best_score),4),
    }
    out_path = ROOT / "_tmp_pv_storage_willingness.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"Saved: {out_path}\n")

    print("="*70)
    print("相关性 (pv_max vs 投运指标):")
    for k,v in corr.items():
        if not pd.isna(v): print(f"  {k}: {round(float(v),3)}")
    print()
    print("分箱统计 (按日前光伏预测最大值):")
    print(f'{"区间":<10}{"天数":>5}{"储能最大":>9}{"储能均值":>9}{"抽蓄最大":>9}{"抽蓄均值":>9}{"台数(储)":>9}{"台数(抽)":>9}{"活跃点":>7}')
    for r in out["binned"]:
        print(f'{r["pv_bin"]:<10}{r["days"]:>5}{r["ind_max_avg"]:>9.0f}{r["ind_avg_avg"]:>9.0f}{r["draw_max_avg"]:>9.0f}{r["draw_avg_avg"]:>9.0f}{r["ind_num_avg"]:>9.0f}{r["draw_num_avg"]:>9.0f}{r["ind_active_avg"]:>7.0f}')
    print()
    print(f'最佳分割点: pv_max > {out["best_split"]} MW 时预测"高意愿"准确率 {out["best_split_acc"]*100:.1f}%')

if __name__ == "__main__":
    main()
