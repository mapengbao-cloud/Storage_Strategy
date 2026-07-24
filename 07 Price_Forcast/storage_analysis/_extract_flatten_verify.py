"""验证削峰填谷假设：储能+抽蓄是否把竞价空间曲线削平成火电的稳定直线。

核心假设检验：
  H1 能量平衡：bidding_space ≈ thermal + storage_total + public（市出清恒等式）
  H2 火电削平：thermal 的 CV(变异系数) < bidding_space 的 CV（逐日比较）
  H3 逐点关系：storage_total_p ≈ (bidding_space - 当日均值)（储能吸收偏差）
  H4 充电↔午间光伏：日内充电能量 vs 11-14 光伏能量
  H5 储能灵活 vs 抽蓄稳定：independent_p 的 std > draw_p 的 std（逐日）
  H6 充放效率：日放电/日充电比例
  H7 优先级：储能先削峰填谷，抽蓄补量（看谁更贴近 bs 偏差曲线）
"""
import os, json
from pathlib import Path
import pymysql
import pandas as pd
import numpy as np

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

def to_tp(to): m = to * 15; return f"{m//60:02d}:{m%60:02d}"

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

    # 功率 MW = 电量 × 4
    df["thermal_p"] = df["thermal_clearing"]*4
    df["new_energy_p"] = df["new_energy_clearing"]*4
    df["public_p"] = df["public_clearing"]*4
    df["independent_p"] = df["independent_clearing"]*4
    df["draw_p"] = df["draw_clearing"]*4
    df["virtual_p"] = df["virtual_clearing"]*4
    df["storage_total_p"] = df["independent_p"] + df["draw_p"] + df["virtual_p"]
    df["bs"] = df["dispatched_load_forecast"] - df["tie_line_load_forecast"] - df["wind_power_forecast"] - df["photovoltaic_power_forecast"] - df["nuclear_power_forecast"] - df["self_power_forecast"]

    # ============ H1 能量平衡 ============
    # bidding_space 应 = thermal + storage_total + public + virtual? 验证
    df["recon"] = df["thermal_p"] + df["storage_total_p"] + df["public_p"]
    df["residual"] = df["bs"] - df["recon"]   # 竞价空间 - (火电+储能+抽蓄+虚拟+公用)
    h1_overall = df["residual"].describe()

    # ============ 逐日指标 ============
    def day_stats(g):
        bs = g["bs"].values; th = g["thermal_p"].values
        st = g["storage_total_p"].values
        ind = g["independent_p"].values; dr = g["draw_p"].values
        pv = g["photovoltaic_power_forecast"].values
        wind = g["wind_power_forecast"].values
        bs_mean = bs.mean()
        # CV：变异系数 = std/mean
        bs_cv = bs.std() / bs.mean() if bs.mean() != 0 else np.nan
        th_cv = th.std() / th.mean() if th.mean() != 0 else np.nan
        # 偏差相关性：储能 vs (bs - bs_mean)
        bs_dev = bs - bs_mean
        corr_st_bsdev = np.corrcoef(st, bs_dev)[0,1] if st.std()>0 and bs_dev.std()>0 else np.nan
        corr_ind_bsdev = np.corrcoef(ind, bs_dev)[0,1] if ind.std()>0 and bs_dev.std()>0 else np.nan
        corr_dr_bsdev = np.corrcoef(dr, bs_dev)[0,1] if dr.std()>0 and bs_dev.std()>0 else np.nan
        # 充放能量（MWh = MW × 0.25）
        discharge = np.clip(st, 0, None).sum() * 0.25
        charge = np.clip(-st, 0, None).sum() * 0.25
        # 午间光伏 11-14 点（time_order 45-57 大约）
        noon_mask = (g["time_order"]>=45) & (g["time_order"]<=57)
        noon_pv = pv[noon_mask.values].sum() * 0.25
        noon_wind = wind[noon_mask.values].sum() * 0.25
        # 削平度：|bs - bs_mean| 之和 vs |th - th_mean| 之和
        bs_flatness = np.abs(bs - bs.mean()).mean()
        th_flatness = np.abs(th - th.mean()).mean()
        return pd.Series({
            "bs_mean": bs_mean, "bs_cv": bs_cv, "th_cv": th_cv,
            "corr_st_bsdev": corr_st_bsdev, "corr_ind_bsdev": corr_ind_bsdev, "corr_dr_bsdev": corr_dr_bsdev,
            "discharge_mwh": discharge, "charge_mwh": charge,
            "eff_ratio": discharge/charge if charge>0 else np.nan,
            "noon_pv_mwh": noon_pv, "noon_wind_mwh": noon_wind,
            "bs_flatness": bs_flatness, "th_flatness": th_flatness,
            "flatten_ratio": th_flatness/bs_flatness if bs_flatness>0 else np.nan,
            "ind_std": ind.std(), "draw_std": dr.std(),
            "flex_ratio": ind.std()/dr.std() if dr.std()>0 else np.nan,
        })
    daily = df.groupby(df["date"].dt.date).apply(day_stats).reset_index()
    daily["date"] = daily["date"].astype(str)

    # ============ H2 削平：火电 CV < 竞价空间 CV ============
    h2_cv = daily[["date","bs_cv","th_cv","flatten_ratio"]].copy()

    # ============ H3 逐点关系汇总 ============
    h3 = daily[["date","corr_st_bsdev","corr_ind_bsdev","corr_dr_bsdev"]].copy()
    # 96点级整体相关性：storage_total vs (bs - 当日均值)
    df["bs_dev"] = df.groupby(df["date"].dt.date)["bs"].transform(lambda x: x - x.mean())
    h3_overall = {
        "corr_st_bsdev": df["storage_total_p"].corr(df["bs_dev"]),
        "corr_ind_bsdev": df["independent_p"].corr(df["bs_dev"]),
        "corr_dr_bsdev": df["draw_p"].corr(df["bs_dev"]),
        "corr_thermal_bs": df["thermal_p"].corr(df["bs"]),
    }

    # ============ H4 充电↔午间光伏 ============
    h4 = daily[["date","charge_mwh","noon_pv_mwh","noon_wind_mwh"]].copy()
    h4_corr = {
        "charge_vs_noon_pv": daily["charge_mwh"].corr(daily["noon_pv_mwh"]),
        "charge_vs_noon_wind": daily["charge_mwh"].corr(daily["noon_wind_mwh"]),
    }

    # ============ H5 储能灵活 vs 抽蓄稳定 ============
    h5 = daily[["date","ind_std","draw_std","flex_ratio"]].copy()

    # ============ H6 充放效率 ============
    h6 = daily[["date","charge_mwh","discharge_mwh","eff_ratio"]].copy()

    # ============ 分时段均值（含偏差）============
    hourly = df.groupby("time_order").agg(
        bs=("bs","mean"), bs_dev=("bs_dev","mean"),
        thermal=("thermal_p","mean"),
        storage=("storage_total_p","mean"),
        independent=("independent_p","mean"),
        draw=("draw_p","mean"),
        virtual=("virtual_p","mean"),
        pv=("photovoltaic_power_forecast","mean"),
        wind=("wind_power_forecast","mean"),
        public=("public_p","mean"),
        residual=("residual","mean"),
    ).reset_index()
    hourly["label"] = hourly["time_order"].map(to_tp)

    # ============ 代表日曲线（含 bs/thermal/storage）============
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
            "bs_dev": sub["bs_dev"].round(0).tolist(),
            "thermal": sub["thermal_p"].round(0).tolist(),
            "storage": sub["storage_total_p"].round(1).tolist(),
            "independent": sub["independent_p"].round(1).tolist(),
            "draw": sub["draw_p"].round(1).tolist(),
            "pv": sub["photovoltaic_power_forecast"].round(0).tolist(),
        }

    out = {
        "date_range": {"start": START, "end": END, "n_dates": int(len(daily))},
        "h1_residual_stats": {k: round(v,2) for k,v in h1_overall.to_dict().items() if not pd.isna(v)},
        "h2_cv": h2_cv.round(4).to_dict(orient="records"),
        "h2_summary": {
            "bs_cv_mean": round(daily["bs_cv"].mean(),4),
            "th_cv_mean": round(daily["th_cv"].mean(),4),
            "flatten_ratio_mean": round(daily["flatten_ratio"].mean(),4),
            "thermal_flatter_days": int((daily["th_cv"]<daily["bs_cv"]).sum()),
            "total_days": int(len(daily)),
        },
        "h3_daily": h3.round(4).to_dict(orient="records"),
        "h3_overall": {k: round(v,4) for k,v in h3_overall.items()},
        "h4_daily": h4.round(1).to_dict(orient="records"),
        "h4_corr": {k: round(v,4) for k,v in h4_corr.items()},
        "h5_daily": h5.round(2).to_dict(orient="records"),
        "h5_summary": {
            "ind_std_mean": round(daily["ind_std"].mean(),2),
            "draw_std_mean": round(daily["draw_std"].mean(),2),
            "flex_ratio_mean": round(daily["flex_ratio"].mean(),2),
        },
        "h6_daily": h6.round(2).to_dict(orient="records"),
        "h6_summary": {
            "eff_ratio_mean": round(daily["eff_ratio"].mean(),4),
            "eff_ratio_median": round(daily["eff_ratio"].median(),4),
        },
        "hourly": [{**{k:round(v,2) for k,v in r.items() if k!="label" and k!="time_order"}, "label": r["label"]} for r in hourly.to_dict(orient="records")],
        "time_labels": [to_tp(i) for i in range(1,97)],
        "pick_dates": pick_dates,
        "curves": curves,
    }
    out_path = ROOT / "_tmp_flatten_verify.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"Saved: {out_path} ({out_path.stat().st_size} bytes)\n")

    # 控制台摘要
    print("="*60)
    print("H1 能量平衡残差 (bs - thermal - storage - public):")
    print(h1_overall.round(1))
    print()
    print("H2 削平度（CV 比较）:")
    s = out["h2_summary"]
    print(f"  竞价空间平均CV: {s['bs_cv_mean']}  火电平均CV: {s['th_cv_mean']}  削平比: {s['flatten_ratio_mean']}")
    print(f"  火电比竞价空间更平稳的天数: {s['thermal_flatter_days']}/{s['total_days']}")
    print()
    print("H3 逐点相关性（储能 vs 竞价空间日内偏差）:")
    h = out["h3_overall"]
    print(f"  储能总 vs bs偏差: {h['corr_st_bsdev']}")
    print(f"  独立储能 vs bs偏差: {h['corr_ind_bsdev']}")
    print(f"  抽蓄 vs bs偏差: {h['corr_dr_bsdev']}")
    print(f"  火电 vs bs: {h['corr_thermal_bs']}")
    print()
    print("H4 充电vs午间光伏:")
    print(f"  充电 vs 午间光伏: {out['h4_corr']['charge_vs_noon_pv']}")
    print(f"  充电 vs 午间风电: {out['h4_corr']['charge_vs_noon_wind']}")
    print()
    print("H5 储能灵活 vs 抽蓄稳定:")
    s5 = out["h5_summary"]
    print(f"  独立储能日均std: {s5['ind_std_mean']}MW  抽蓄日均std: {s5['draw_std_mean']}MW  灵活比: {s5['flex_ratio_mean']}")
    print()
    print("H6 充放效率（放电/充电）:")
    s6 = out["h6_summary"]
    print(f"  均值: {s6['eff_ratio_mean']}  中位数: {s6['eff_ratio_median']}")
    print()
    print("分时段均值（前6点）:")
    for r in out["hourly"][:6]:
        print(f"  {r['label']} bs={r['bs']} th={r['thermal']} st={r['storage']} ind={r['independent']} dr={r['draw']} resid={r['residual']}")

if __name__ == "__main__":
    main()
