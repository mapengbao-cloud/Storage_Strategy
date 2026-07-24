# shandong_pmos_spot_dayahead_supply_demand 表探索报告

## 表结构

| 字段名 | 类型 | 说明 |
|--------|------|------|
| data_id | int(11) | 主键 |
| date | date | 日期 |
| time_order | int(11) | 时段序号 (1-96) |
| dayahead_provincial_load | decimal(20,4) | 日前省内负荷预测 (MW) |
| dayahead_transprovincial_load | decimal(20,4) | 日前跨省联络线负荷预测 (MW) |
| dayahead_wind_power | decimal(20,4) | 日前风电出力预测 (MW) |
| dayahead_photovoltaic_power | decimal(20,4) | 日前光伏出力预测 (MW) |
| creator | varchar(255) | 创建人 |
| creation_time | datetime | 创建时间 |
| modifier | varchar(255) | 修改人 |
| modification_time | datetime | 修改时间 |

## 数据概览

- **总行数**: 1,248 行
- **日期范围**: 2020-08-01 ~ 2020-08-13 (仅 13 天)
- **时间分辨率**: 每日 96 个时段 (15 分钟间隔)
- **数据状态**: 历史测试数据，非最新

## 数值范围统计

| 指标 | 最小值 (MW) | 最大值 (MW) |
|------|------------|------------|
| 省内负荷 | 0.00 | 75,886.00 |
| 跨省联络线 | 14,320.00 | 19,236.00 |
| 风电出力 | 291.37 | 7,852.21 |
| 光伏出力 | 0.00 | 4,295.45 |

## 竞价空间计算

**标准公式**（5 项）：`竞价空间 = 直调负荷 − (联络线受电 + 风电 + 光伏 + 核电 + 自备)`
**本表简化版**（4 项，因 shandong_pmos_spot_dayahead_supply_demand 仅含 4 个字段）：`竞价空间 = 省内负荷 - 跨省联络线 - 风电 - 光伏`

### 示例 (2020-08-01)

| 时段 | 省内负荷 | 跨省联络线 | 风电 | 光伏 | 竞价空间 |
|------|---------|-----------|------|------|---------|
| 00:00-00:15 | 56,465.81 | 14,848.00 | 3,157.62 | 0.00 | 38,460.19 |
| 02:00-02:15 | 53,349.85 | 14,848.00 | 2,781.44 | 0.00 | 35,720.41 |
| 04:00-04:15 | 51,494.55 | 14,848.00 | 2,333.86 | 0.00 | 34,312.69 |
| 06:00-06:15 | 54,015.86 | 14,848.00 | 2,070.27 | 195.35 | 36,902.24 |
| 08:00-08:15 | 56,227.95 | 17,652.00 | 1,895.79 | 1,562.70 | 35,117.46 |
| 10:00-10:15 | 60,723.49 | 18,614.00 | 1,504.97 | 2,961.14 | 37,643.38 |
| 12:00-12:15 | 60,628.34 | 17,335.00 | 1,415.80 | 3,507.84 | 38,369.70 |
| 14:00-14:15 | 63,458.87 | 17,335.00 | 1,439.50 | 3,081.98 | 41,602.39 |
| 16:00-16:15 | 64,172.45 | 17,335.00 | 1,581.65 | 1,801.35 | 43,454.45 |
| 18:00-18:15 | 62,935.58 | 18,614.00 | 1,867.36 | 317.70 | 42,136.52 |
| 20:00-20:15 | 62,769.08 | 18,614.00 | 2,442.15 | 0.68 | 41,712.25 |
| 22:00-22:15 | 61,484.64 | 15,810.00 | 2,863.08 | 0.00 | 42,811.56 |

**观察**:
- 光伏出力仅在白天 (约 06:00-18:00) 有值，夜间为 0
- 竞价空间在午间 (12:00-14:00) 因光伏大发而相对较低
- 晚高峰 (16:00-22:00) 竞价空间较大，火电需求高

## 相关表对比

| 表名 | 日期范围 | 行数 | 说明 |
|------|---------|------|------|
| shandong_pmos_spot_dayahead_supply_demand | 2020-08-01 ~ 2020-08-13 | 1,248 | 日前供需预测 |
| shandong_pmos_spot_actual_supply_demand | 2020-06-01 ~ 2020-08-12 | 7,008 | 实际供需数据 |
| shandong_px_release_constraint_dayahead_load_forecast | 2021-05-07 ~ 2021-11-11 | 16,896 | 日前负荷预测 |

## 常用查询

### 1. 查看某日的完整 96 点数据

```sql
SELECT 
    time_order,
    dayahead_provincial_load,
    dayahead_transprovincial_load,
    dayahead_wind_power,
    dayahead_photovoltaic_power,
    (dayahead_provincial_load - dayahead_transprovincial_load 
     - dayahead_wind_power - dayahead_photovoltaic_power) as bidding_space
FROM shandong_pmos_spot_dayahead_supply_demand
WHERE date = '2020-08-01'
ORDER BY time_order;
```

### 2. 计算连续 2 小时峰谷差

```sql
WITH hourly AS (
    SELECT 
        date,
        FLOOR((time_order - 1) / 8) as hour_group,
        AVG(dayahead_provincial_load - dayahead_transprovincial_load 
            - dayahead_wind_power - dayahead_photovoltaic_power) as avg_bs
    FROM shandong_pmos_spot_dayahead_supply_demand
    WHERE date = '2020-08-01'
    GROUP BY date, FLOOR((time_order - 1) / 8)
)
SELECT 
    date,
    MAX(avg_bs) as peak_2h,
    MIN(avg_bs) as valley_2h,
    MAX(avg_bs) - MIN(avg_bs) as diff
FROM hourly;
```

### 3. 查看光伏出力最高的时段

```sql
SELECT 
    date, time_order,
    dayahead_photovoltaic_power,
    (dayahead_provincial_load - dayahead_transprovincial_load 
     - dayahead_wind_power - dayahead_photovoltaic_power) as bidding_space
FROM shandong_pmos_spot_dayahead_supply_demand
WHERE dayahead_photovoltaic_power > 3000
ORDER BY dayahead_photovoltaic_power DESC
LIMIT 10;
```

## 与本地竞价空间文件的对比

| 数据来源 | 时间范围 | 更新频率 | 数据内容 |
|---------|---------|---------|---------|
| 天机数据库 (本表) | 2020-08 (历史) | 无更新 | 预测数据 |
| 本地 Excel 文件 | 2026-05-18 ~ 05-29 | 每日更新 | 预测 + 实际 |

**结论**: 本地文件数据更新、更完整，天机数据库此表仅包含历史测试数据，不建议用于实际分析。

## 注意事项

1. **数据陈旧**: 该表数据为 2020 年 8 月，距今已近 6 年
2. **数据量小**: 仅 13 天，无法做长期趋势分析
3. **建议**: 如需最新数据，应查询其他表或使用本地 Excel 文件
