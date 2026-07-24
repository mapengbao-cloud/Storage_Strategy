"""验证两步逻辑：
  步骤1（总量）：次日储能+抽蓄充电总量 = f(光伏总出力)？看每日光伏总出力 vs 储能+抽蓄充电总量
  步骤2（分布）：总量怎么分布到每个时点？储能+抽蓄是否填掉 bs 最深的谷、削掉最高的峰

输出 _tmp_two_step.json
"""
import os, json
from pathlib import Path
import pymysql, pandas as pd, numpy as np

for line in open(Path(__file__).parent.parent / ".env", encoding="utf-8"):
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
    sql_q = """SELECT date, time_point, thermal_clearing, new_energy_clearing, public_clearing,
               independent_clearing, draw_clearing, virtual_clearing
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
    for c in ["thermal_clearing","new_energy_clearing","public_clearing","independent_clearing","draw_clearing","virtual_clearing"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    for c in ["dispatched_load_forecast","tie_line_load_forecast","wind_power_forecast","photovoltaic_power_forecast","nuclear_power_forecast","local_power_forecast","self_power_forecast"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # 功率 MW
    df["thermal_p"] = df["thermal_clearing"]*4
    df["new_energy_p"] = df["new_energy_clearing"]*4
    df["independent_p"] = df["independent_clearing"]*4
    df["draw_p"] = df["draw_clearing"]*4
    df["virtual_p"] = df["virtual_clearing"]*4
    # 储能+抽蓄（不含虚拟电厂，按用户要求）
    df["storage_ps_p"] = df["independent_p"] + df["draw_p"]
    df["storage_ps_charge"] = (-df["storage_ps_p"]).clip(lower=0)   # 充电功率（正）
    df["storage_ps_discharge"] = df["storage_ps_p"].clip(lower=0)   # 放电功率（正）
    df["bs"] = df["dispatched_load_forecast"] - df["tie_line_load_forecast"] - df["wind_power_forecast"] - df["photovoltaic_power_forecast"] - df["nuclear_power_forecast"] - df["self_power_forecast"]
    df["wind_pv"] = df["wind_power_forecast"] + df["photovoltaic_power_forecast"]

    # ============ 步骤1：每日总量 ============
    daily = df.groupby(df["date"].dt.date).apply(lambda g: pd.Series({
        # 总能量 MWh = MW × 0.25 × 96 / 1000 → GWh；这里用 MWh
        "pv_mwh": g["photovoltaic_power_forecast"].sum() * 0.25,
        "wind_mwh": g["wind_power_forecast"].sum() * 0.25,
        "newenergy_mwh": g["new_energy_p"].sum() * 0.25,
        "charge_mwh": g["storage_ps_charge"].sum() * 0.25,
        "discharge_mwh": g["storage_ps_discharge"].sum() * 0.25,
        "bs_mean_mw": g["bs"].mean(),
        "bs_min_mw": g["bs"].min(),
        "bs_max_mw": g["bs"].max(),
        "bs_range_mw": g["bs"].max() - g["bs"].min(),
        # 充电是否覆盖午间光伏：11-14点（time_order 45-57）
        "noon_pv_mwh": g[(g["time_order"]>=45)&(g["time_order"]<=57)]["photovoltaic_power_forecast"].sum()*0.25,
        "noon_charge_mwh": g[(g["time_order"]>=45)&(g["time_order"]<=57)]["storage_ps_charge"].sum()*0.25,
        # 充电时段数（storage_ps_charge>0 的点数）
        "charge_points": int((g["storage_ps_charge"]>0.1).sum()),
        "discharge_points": int((g["storage_ps_discharge"]>0.1).sum()),
    })).reset_index()
    daily["date"] = daily["date"].astype(str)

    # 相关性（日级）
    corr1 = {
        "charge_vs_pv": daily["charge_mwh"].corr(daily["pv_mwh"]),
        "charge_vs_wind": daily["charge_mwh"].corr(daily["wind_mwh"]),
        "charge_vs_newenergy": daily["charge_mwh"].corr(daily["newenergy_mwh"]),
        "charge_vs_noon_pv": daily["charge_mwh"].corr(daily["noon_pv_mwh"]),
        "discharge_vs_bs_max": daily["discharge_mwh"].corr(daily["bs_max_mw"]),
        "discharge_vs_bs_mean": daily["discharge_mwh"].corr(daily["bs_mean_mw"]),
        "charge_vs_bs_min": daily["charge_mwh"].corr(daily["bs_min_mw"]),
        "charge_vs_bs_range": daily["charge_mwh"].corr(daily["bs_range_mw"]),
    }

    # 线性回归：charge = a*pv + b （用于预测日总量）
    from numpy.polynomial import polynomial as Pp
    x = daily["pv_mwh"].values.astype(float)
    y = daily["charge_mwh"].values.astype(float)
    mask = ~np.isnan(x) & ~np.isnan(y)
    coeffs = np.polyfit(x[mask], y[mask], 1)  # [slope, intercept]
    pred_charge = np.polyval(coeffs, x[mask])
    ss_res = np.sum((y[mask] - pred_charge)**2)
    ss_tot = np.sum((y[mask] - y[mask].mean())**2)
    r2_charge = 1 - ss_res/ss_tot
    linreg = {"slope": round(float(coeffs[0]),4), "intercept": round(float(coeffs[1]),2),
              "r2": round(float(r2_charge),4)}

    # ============ 步骤2：时点分布——是否填谷削峰 ============
    # 对每天：找出 bs 最深的谷（最低点）和最高的峰（最高点）
    # 看这些点上的 storage_ps_p 是不是正的（谷处充电=负出力，吸收过剩）
    # bs 最高点：storage_ps_p 应该是正的（放电补峰）
    # bs 最低点：storage_ps_p 应该是负的（充电填谷）
    day_list = []
    peak_fill_stats = {"filled_valley": 0, "shaved_peak": 0, "total": 0}
    # 记录每天 bs 最高/最低点的 storage_ps_p 值，以及对应的 bs 值
    peak_storage = []   # bs最高点处storage_ps_p
    valley_storage = []  # bs最低点处storage_ps_p
    for d, g in df.groupby(df["date"].dt.date):
        g = g.sort_values("time_order")
        bs = g["bs"].values
        sp = g["storage_ps_p"].values
        ind = g["independent_p"].values
        dr = g["draw_p"].values
        pv = g["photovoltaic_power_forecast"].values
        th = g["thermal_p"].values
        # bs 最低点（谷）
        vidx = np.argmin(bs)
        bs_valley = bs[vidx]
        sp_valley = sp[vidx]
        # bs 最高点（峰）
        pidx = np.argmax(bs)
        bs_peak = bs[pidx]
        sp_peak = sp[pidx]
        # 谷处是否充电（sp < 0 即充电）
        filled_valley = sp_valley < -1
        # 峰处是否放电（sp > 0 即放电）
        shaved_peak = sp_peak > 1
        peak_fill_stats["total"] += 1
        if filled_valley: peak_fill_stats["filled_valley"] += 1
        if shaved_peak: peak_fill_stats["shaved_peak"] += 1
        peak_storage.append({"date": str(d), "bs_peak": round(float(bs_peak),0), "sp_at_peak": round(float(sp_peak),0), "shaved": bool(shaved_peak)})
        valley_storage.append({"date": str(d), "bs_valley": round(float(bs_valley),0), "sp_at_valley": round(float(sp_valley),0), "filled": bool(filled_valley)})

    # ============ 时点级相关性：storage_ps vs bs（当日）============
    # 每天 storage_ps_p 和 bs 的相关性
    daily_pt_corr = []
    for d, g in df.groupby(df["date"].dt.date):
        g = g.sort_values("time_order")
        bs = g["bs"].values; sp = g["storage_ps_p"].values
        if bs.std()>0 and sp.std()>0:
            r = np.corrcoef(bs, sp)[0,1]
        else:
            r = None
        daily_pt_corr.append({"date": str(d), "corr_bs_sp": round(float(r),3) if r is not None else None})

    # ============ 削峰填谷的量化：bs 有/无储能时火电需要的波动 ============
    # "无储能时火电出力" = bs - 其他可调度（简化为 bs 本身，因为 bs 是火电的市场空间）
    # 有储能时火电 = bs - storage_ps_p（储能充电使火电出力↑，放电使火电↓）
    # 即 thermal_actual ≈ bs - storage_ps_p （符号：storage 正=放电→减少火电需求；负=充电→增加火电需求）
    # 注意符号：bs - storage_ps_p
    df["thermal_implied"] = df["bs"] - df["storage_ps_p"]
    flatten_stats = df.groupby(df["date"].dt.date).apply(lambda g: pd.Series({
        "bs_range": g["bs"].max() - g["bs"].min(),
        "th_implied_range": g["thermal_implied"].max() - g["thermal_implied"].min(),
        "bs_std": g["bs"].std(),
        "th_implied_std": g["thermal_implied"].std(),
        "actual_th_range": g["thermal_p"].max() - g["thermal_p"].min(),
        "actual_th_std": g["thermal_p"].std(),
    })).reset_index()
    flatten_stats["date"] = flatten_stats["date"].astype(str)
    flatten_summary = {
        "bs_range_mean": round(float(flatten_stats["bs_range"].mean()),0),
        "th_implied_range_mean": round(float(flatten_stats["th_implied_range"].mean()),0),
        "actual_th_range_mean": round(float(flatten_stats["actual_th_range"].mean()),0),
        "bs_std_mean": round(float(flatten_stats["bs_std"].mean()),0),
        "th_implied_std_mean": round(float(flatten_stats["th_implied_std"].mean()),0),
        "actual_th_std_mean": round(float(flatten_stats["actual_th_std"].mean()),0),
        "range_reduction_pct": round(float((flatten_stats["bs_range"].mean() - flatten_stats["th_implied_range"].mean()) / flatten_stats["bs_range"].mean() * 100),1),
    }

    # ============ 分时段均值 ============
    hourly = df.groupby("time_order").agg(
        bs=("bs","mean"), storage_ps=("storage_ps_p","mean"),
        independent=("independent_p","mean"), draw=("draw_p","mean"),
        thermal=("thermal_p","mean"), pv=("photovoltaic_power_forecast","mean"),
        wind=("wind_power_forecast","mean"), thermal_implied=("thermal_implied","mean"),
    ).reset_index()
    hourly["label"] = hourly["time_order"].map(to_tp)

    # ============ 代表日 ============
    sample_dates = daily["date"].tolist()
    pick_idx = [0, len(sample_dates)//5, len(sample_dates)//2, len(sample_dates)*3//4, len(sample_dates)-1]
    pick_dates = []
    seen = set()
    for i in pick_idx:
        if 0<=i<len(sample_dates):
            d = sample_dates[i]
            if d not in seen: seen.add(d); pick_dates.append(d)
    pick_dates = pick_dates[:5]
    curves = {}
    for d in pick_dates:
        sub = df[df["date"].dt.strftime("%Y-%m-%d")==d].sort_values("time_order")
        curves[d] = {
            "bs": sub["bs"].round(0).tolist(),
            "storage_ps": sub["storage_ps_p"].round(1).tolist(),
            "thermal_implied": sub["thermal_implied"].round(0).tolist(),
            "thermal": sub["thermal_p"].round(0).tolist(),
            "independent": sub["independent_p"].round(1).tolist(),
            "draw": sub["draw_p"].round(1).tolist(),
            "pv": sub["photovoltaic_power_forecast"].round(0).tolist(),
        }

    out = {
        "date_range": {"start": START, "end": END, "n_dates": int(len(daily))},
        "daily": daily.round(1).to_dict(orient="records"),
        "corr1": {k: round(float(v),4) for k,v in corr1.items() if not pd.isna(v)},
        "linreg": linreg,
        "peak_fill_stats": peak_fill_stats,
        "peak_storage": peak_storage,
        "valley_storage": valley_storage,
        "daily_pt_corr": daily_pt_corr,
        "flatten_stats": flatten_stats.round(1).to_dict(orient="records"),
        "flatten_summary": flatten_summary,
        "hourly": [{**{k:(round(float(v),2) if isinstance(v,(int,float,np.floating)) else v) for k,v in r.items() if k!="label"}, "label": r["label"]} for r in hourly.to_dict(orient="records")],
        "time_labels": [to_tp(i) for i in range(1,97)],
        "pick_dates": pick_dates,
        "curves": curves,
    }
    out_path = Path(__file__).parent.parent / "_tmp_two_step.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"Saved: {out_path} ({out_path.stat().st_size} bytes)\n")

    print("="*60)
    print("步骤1 相关性（日级总量）：")
    for k,v in corr1.items():
        if not pd.isna(v): print(f"  {k}: {round(float(v),4)}")
    print(f"  线性回归 charge={linreg['slope']}*pv + {linreg['intercept']}  R²={linreg['r2']}")
    print()
    print("步骤2 削峰填谷：")
    print(f"  填谷天数(bs最低点处储能充电): {peak_fill_stats['filled_valley']}/{peak_fill_stats['total']}")
    print(f"  削峰天数(bs最高点处储能放电): {peak_fill_stats['shaved_peak']}/{peak_fill_stats['total']}")
    print(f"  {flatten_summary}")
    print()
    print("分时段(关键点):")
    for r in out["hourly"]:
        if r["label"] in ["03:00","06:00","09:00","12:00","13:00","15:00","18:00","20:00","22:00"]:
            print(f"  {r['label']} bs={r['bs']} storage_ps={r['storage_ps']} th_imp={r['thermal_implied']} pv={r['pv']}")

if __name__ == "__main__":
    main()
