"""对比竞价空间2h谷值均值 vs 储能投运意愿。
2h谷值 = 相似日特征中的 valley（连续8个点=2h的最低均值窗口的MW值）。
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
    # 1. 相似日特征（含2h谷值）
    feat = json.load(open(ROOT / "_tmp_similar_features.json", encoding="utf-8"))

    # 2. 储能+抽蓄投运数据
    conn = pymysql.connect(host=HOST, port=PORT, user=USER, password=PWD, database=DB,
                           charset="utf8mb4", connect_timeout=10, read_timeout=120)
    sql_q = """SELECT date, time_point, independent_clearing, draw_clearing, independent_number, draw_number
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
    df["ind_p"] = df["independent_clearing"]*4
    df["draw_p"] = df["draw_clearing"]*4
    df["storage_work"] = df["ind_p"].abs() + df["draw_p"].abs()

    # 日级统计
    daily = df.groupby(df["date"].dt.date).apply(lambda g: pd.Series({
        "pv_max": g["photovoltaic_power_forecast"].max(),
        "ind_max_p": g["ind_p"].abs().max(),
        "ind_avg_p": g["ind_p"].abs().mean(),
        "draw_max_p": g["draw_p"].abs().max(),
        "draw_avg_p": g["draw_p"].abs().mean(),
        "storage_max_p": g["storage_work"].max(),
        "storage_avg_p": g["storage_work"].mean(),
        "ind_num": g["independent_number"].max(),
        "draw_num": g["draw_number"].max(),
    })).reset_index()
    daily["date_str"] = daily["date"].astype(str)

    # 3. 合并 2h 谷值
    daily["valley_2h"] = daily["date_str"].map(lambda d: feat.get(d, {}).get("valley"))
    daily["peak_2h"] = daily["date_str"].map(lambda d: feat.get(d, {}).get("peak"))
    daily["valley_time"] = daily["date_str"].map(lambda d: feat.get(d, {}).get("valley_time"))
    daily["valley_period"] = daily["date_str"].map(lambda d: feat.get(d, {}).get("valley_period"))
    daily = daily.dropna(subset=["valley_2h"])

    # 4. 相关性
    corr = {
        "valley_vs_ind_max": daily["valley_2h"].corr(daily["ind_max_p"]),
        "valley_vs_ind_avg": daily["valley_2h"].corr(daily["ind_avg_p"]),
        "valley_vs_draw_max": daily["valley_2h"].corr(daily["draw_max_p"]),
        "valley_vs_draw_avg": daily["valley_2h"].corr(daily["draw_avg_p"]),
        "valley_vs_storage_max": daily["valley_2h"].corr(daily["storage_max_p"]),
        "valley_vs_storage_avg": daily["valley_2h"].corr(daily["storage_avg_p"]),
        "valley_vs_ind_num": daily["valley_2h"].corr(daily["ind_num"]),
        "valley_vs_draw_num": daily["valley_2h"].corr(daily["draw_num"]),
        "valley_vs_pv_max": daily["valley_2h"].corr(daily["pv_max"]),
    }

    # 5. 分箱（按2h谷值）
    bins = [-50000, 0, 5000, 10000, 15000, 20000, 999999]
    labels = ["<0(负)","0-5GW","5-10GW","10-15GW","15-20GW",">20GW"]
    daily["valley_bin"] = pd.cut(daily["valley_2h"], bins=bins, labels=labels, include_lowest=True)
    binned = daily.groupby("valley_bin", observed=True).agg(
        days=("date_str","count"),
        ind_max_avg=("ind_max_p","mean"),
        ind_avg_avg=("ind_avg_p","mean"),
        draw_max_avg=("draw_max_p","mean"),
        draw_avg_avg=("draw_avg_p","mean"),
        storage_max_avg=("storage_max_p","mean"),
        storage_avg_avg=("storage_avg_p","mean"),
        ind_num_avg=("ind_num","mean"),
        draw_num_avg=("draw_num","mean"),
    ).reset_index()
    binned["valley_bin"] = binned["valley_bin"].astype(str)

    # 6. 最佳阈值（储能高意愿 = ind_max_p > 3000）
    daily["high_willing"] = daily["ind_max_p"] > 3000
    best_split = None; best_score = -1
    val_arr = daily["valley_2h"].values
    for split in np.arange(-5000, 25000, 500):
        pred_high = val_arr < split   # 谷值越低意愿越高（负相关）
        actual_high = daily["high_willing"].values
        acc = (pred_high == actual_high).mean()
        if acc > best_score:
            best_score = acc; best_split = float(split)

    out = {
        "date_range": {"start": START, "end": END, "n_dates": int(len(daily))},
        "daily": daily[["date_str","valley_2h","peak_2h","valley_time","valley_period","pv_max","ind_max_p","ind_avg_p","draw_max_p","draw_avg_p","ind_num","draw_num"]].round(1).to_dict(orient="records"),
        "corr": {k: round(float(v),4) for k,v in corr.items() if not pd.isna(v)},
        "binned": binned.round(1).to_dict(orient="records"),
        "best_split": round(best_split,0),
        "best_split_acc": round(float(best_score),4),
    }
    out_path = ROOT / "_tmp_valley_willingness.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"Saved: {out_path}\n")

    print("="*70)
    print("相关性 (2h谷值 vs 投运指标):")
    for k,v in corr.items():
        if not pd.isna(v): print(f"  {k}: {round(float(v),3)}")
    print()
    print("分箱统计 (按2h谷值):")
    print(f'{"区间":<12}{"天数":>5}{"储能最大":>9}{"储能均值":>9}{"抽蓄最大":>9}{"抽蓄均值":>9}{"台数(储)":>9}{"台数(抽)":>9}')
    for r in out["binned"]:
        print(f'{r["valley_bin"]:<12}{r["days"]:>5}{r["ind_max_avg"]:>9.0f}{r["ind_avg_avg"]:>9.0f}{r["draw_max_avg"]:>9.0f}{r["draw_avg_avg"]:>9.0f}{r["ind_num_avg"]:>9.0f}{r["draw_num_avg"]:>9.0f}')
    print()
    print(f'最佳分割点: 2h谷值 < {out["best_split"]} MW 时预测"高意愿"准确率 {out["best_split_acc"]*100:.1f}%')

if __name__ == "__main__":
    main()
