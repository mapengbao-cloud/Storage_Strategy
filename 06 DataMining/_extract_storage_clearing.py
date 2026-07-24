"""提取储能+抽蓄+虚拟电厂出清数据 + 日前负荷预测数据，做关联分析。

数据源：
  - shandong_px_dayahead_clearing_quantity_number (96点/天, 电量MWh)
  - shandong_px_spot_dayahead_load_info (96点/天, 负荷预测MW)

功率换算：电量(MWh) × 4 = 功率(MW)  （15分钟一个点，÷0.25h = ×4）

输出：_tmp_storage_clearing.json  供 gen HTML 使用
"""
import os
import json
from pathlib import Path

# 加载 .env
for line in open(Path(__file__).parent.parent / ".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import pymysql
import pandas as pd
import numpy as np

HOST = os.getenv("DB_TIANJI_HOST")
PORT = int(os.getenv("DB_TIANJI_PORT", 3306))
USER = os.getenv("DB_TIANJI_USER")
PWD = os.getenv("DB_TIANJI_PASSWORD")
DB = os.getenv("DB_TIANJI_DATABASE")

START = "2026-05-01"
END = "2026-07-22"


def to_time_point(time_order: int) -> str:
    """time_order 1-96 → '00:15'-'24:00'"""
    m = time_order * 15
    return f"{m // 60:02d}:{m % 60:02d}"


def main():
    conn = pymysql.connect(host=HOST, port=PORT, user=USER, password=PWD,
                           database=DB, charset="utf8mb4",
                           connect_timeout=10, read_timeout=120)
    cur = conn.cursor()

    # 1. 出清电量数据
    print(f"[1] Fetching clearing_quantity {START} ~ {END} ...")
    sql_q = """
        SELECT date, time_point,
               thermal_clearing, new_energy_clearing, public_clearing,
               independent_clearing, draw_clearing, virtual_clearing
        FROM shandong_px_dayahead_clearing_quantity_number
        WHERE date BETWEEN %s AND %s
        ORDER BY date, time_point
    """
    df_q = pd.read_sql(sql_q, conn, params=(START, END))
    print(f"    rows={len(df_q)}, dates={df_q['date'].nunique()}")
    # time_point '00:15' → time_order 1-96
    def tp_to_to(tp):
        h, mm = tp.split(":")
        return int(h) * 4 + (int(mm) // 15)
    df_q["time_order"] = df_q["time_point"].map(tp_to_to)

    # 2. 日前负荷预测
    print(f"[2] Fetching dayahead_load_info {START} ~ {END} ...")
    sql_l = """
        SELECT date, time_order,
               dispatched_load_forecast, tie_line_load_forecast,
               wind_power_forecast, photovoltaic_power_forecast,
               nuclear_power_forecast, local_power_forecast, self_power_forecast
        FROM shandong_px_spot_dayahead_load_info
        WHERE date BETWEEN %s AND %s
        ORDER BY date, time_order
    """
    df_l = pd.read_sql(sql_l, conn, params=(START, END))
    print(f"    rows={len(df_l)}, dates={df_l['date'].nunique()}")

    cur.close()
    conn.close()

    # 3. 合并
    df = pd.merge(df_q, df_l, on=["date", "time_order"], how="inner")
    df["date"] = pd.to_datetime(df["date"])
    print(f"[3] Merged rows={len(df)}, dates={df['date'].nunique()}")

    # 4. 数值化 + 功率换算（电量×4=功率MW）
    for c in ["thermal_clearing", "new_energy_clearing", "public_clearing",
              "independent_clearing", "draw_clearing", "virtual_clearing"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    for c in ["dispatched_load_forecast", "tie_line_load_forecast",
              "wind_power_forecast", "photovoltaic_power_forecast",
              "nuclear_power_forecast", "local_power_forecast", "self_power_forecast"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # 功率 (MW) = 电量 (MWh) × 4
    df["thermal_p"] = df["thermal_clearing"] * 4
    df["new_energy_p"] = df["new_energy_clearing"] * 4
    df["public_p"] = df["public_clearing"] * 4
    df["independent_p"] = df["independent_clearing"] * 4      # 独立储能
    df["draw_p"] = df["draw_clearing"] * 4                    # 抽蓄
    df["virtual_p"] = df["virtual_clearing"] * 4              # 虚拟电厂

    # 储能+抽蓄+虚拟电厂 净出清功率（正=放电，负=充电）
    df["storage_total_p"] = df["independent_p"] + df["draw_p"] + df["virtual_p"]
    # 放电功率（只取正） / 充电功率（只取负的绝对值）
    df["discharge_p"] = df["storage_total_p"].clip(lower=0)
    df["charge_p"] = (-df["storage_total_p"]).clip(lower=0)

    # 竞价空间 = 直调负荷 - (联络线受电 + 风电 + 光伏 + 核电 + 自备)  # 地方电厂不参与bs
    df["bidding_space"] = (
        df["dispatched_load_forecast"]
        - df["tie_line_load_forecast"]
        - df["wind_power_forecast"]
        - df["photovoltaic_power_forecast"]
        - df["nuclear_power_forecast"]
        - df["local_power_forecast"]
        - df["self_power_forecast"]
    )
    df["wind_pv"] = df["wind_power_forecast"] + df["photovoltaic_power_forecast"]

    # 5. 每日统计
    daily = df.groupby(df["date"].dt.date).agg(
        storage_net_sum=("storage_total_p", "sum"),              # 净能量积分（÷4 回到 MWh）
        discharge_sum=("discharge_p", "sum"),
        charge_sum=("charge_p", "sum"),
        storage_peak=("storage_total_p", "max"),
        storage_min=("storage_total_p", "min"),
        bs_mean=("bidding_space", "mean"),
        bs_min=("bidding_space", "min"),
        bs_max=("bidding_space", "max"),
        wind_sum=("wind_power_forecast", "sum"),
        pv_sum=("photovoltaic_power_forecast", "sum"),
        wind_pv_sum=("wind_pv", "sum"),
        load_mean=("dispatched_load_forecast", "mean"),
    ).reset_index()
    daily["date"] = daily["date"].astype(str)
    # 净能量 MWh = Σ(P_MW × 0.25h) = sum × 0.25
    daily["discharge_mwh"] = daily["discharge_sum"] * 0.25
    daily["charge_mwh"] = daily["charge_sum"] * 0.25
    daily["net_mwh"] = daily["storage_net_sum"] * 0.25

    # 6. 相关性（基于96点数据）
    cols_corr = ["storage_total_p", "bidding_space", "wind_power_forecast",
                 "photovoltaic_power_forecast", "wind_pv", "dispatched_load_forecast",
                 "independent_p", "draw_p", "virtual_p"]
    corr = df[cols_corr].corr().round(4)

    # 7. 分时段均值（96点平均曲线）
    hourly = df.groupby("time_order").agg(
        storage_total=("storage_total_p", "mean"),
        independent=("independent_p", "mean"),
        draw=("draw_p", "mean"),
        virtual=("virtual_p", "mean"),
        bidding_space=("bidding_space", "mean"),
        wind=("wind_power_forecast", "mean"),
        pv=("photovoltaic_power_forecast", "mean"),
    ).reset_index()
    # time_order → 时间标签
    hourly["label"] = hourly["time_order"].map(to_time_point)

    # 8. 每日96点曲线（用于热力图/叠加图，取若干代表日）
    sample_dates = daily["date"].tolist()
    curves = {}
    for d in sample_dates:
        sub = df[df["date"].dt.strftime("%Y-%m-%d") == d].sort_values("time_order")
        curves[d] = {
            "storage": sub["storage_total_p"].round(1).tolist(),
            "bs": sub["bidding_space"].round(1).tolist(),
            "wind_pv": sub["wind_pv"].round(1).tolist(),
        }

    out = {
        "date_range": {"start": START, "end": END, "n_dates": int(daily.shape[0])},
        "daily": daily.to_dict(orient="records"),
        "corr": corr.to_dict(),
        "corr_cols": cols_corr,
        "hourly": hourly.to_dict(orient="records"),
        "curves": curves,
        "time_labels": [to_time_point(i) for i in range(1, 97)],
        "sample_dates": sample_dates,
    }
    out_path = Path(__file__).parent.parent / "_tmp_storage_clearing.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"[4] Saved: {out_path} ({out_path.stat().st_size} bytes)")

    # 打印关键统计
    print("\n=== 每日储能净出清能量 (MWh) 概览 ===")
    print(daily[["date", "discharge_mwh", "charge_mwh", "net_mwh", "bs_mean"]].round(1).to_string(index=False))

    print("\n=== 相关性矩阵（96点级）===")
    print(corr.to_string())

    print("\n=== 分时段均值（前12个点）===")
    print(hourly[["label", "storage_total", "independent", "draw", "virtual", "bidding_space", "wind", "pv"]].round(1).head(12).to_string(index=False))


if __name__ == "__main__":
    main()
