"""Revenue calculation — the SINGLE SOURCE OF TRUTH for all revenue logic.

All stages (02 day-ahead, 03 real-time, 04 settlement, 05 dashboard) call
these functions. Extracted from Excel 充放测算 row 4 formulas and the
compute_summary_values() / compute_settlement_values() functions in
05 Review_Dashboard_and _weeklyreport/process_data.py.

Formulas replicated:
    P = -M / B                          # 综合效率
    C = A * B                           # 充电收入
    D = B * I12, E = B * I13            # 各项费用
    F = B * (1-P) * I8, G = B * (1-P) * I9
    H = B * I14
    I_val = B * J_val * capacity_cost   # 容量分摊
    K = C + D + E + F + G + H + I_val   # 总成本
    N_val = L * M                       # 放电收入
    O = N_val + K                       # 净收益
    Q = L - A                           # 价差
    O6 = N_val + C                      # 放电收入 + 充电收入
"""

from dataclasses import dataclass, field
from src.data.models import DailyRevenue, ChargeDischargeData, N_POINTS
from src.config import get_parameters
from src.utils.numerics import safe_float


@dataclass
class RevenueInput:
    """All inputs needed for revenue computation.

    This is the input interface shared by both the 'summary' path
    (from 报价及预中标 raw data) and the 'settlement' path
    (from 充电/放电日清算费用 sheets).

    Attributes:
        charge_volume: B — total charging MWh (negative convention in raw data)
        charge_price: A — weighted avg charge price (yuan/MWh)
        charge_revenue: C — charge revenue (negative = cost)
        discharge_volume: M — total discharging MWh
        discharge_price: L — weighted avg discharge price (yuan/MWh)
        discharge_revenue: N — discharge revenue (positive = income)
        I8, I9, I12, I13, I14: Parameters from 充放测算 I column
        J_val: Capacity allocation coefficient (from capacity.py)
        capacity_cost: Monthly capacity cost per kW (default from config)
    """
    charge_volume: float = 0.0       # B
    charge_price: float = 0.0        # A
    charge_revenue: float = 0.0      # C
    discharge_volume: float = 0.0    # M
    discharge_price: float = 0.0     # L
    discharge_revenue: float = 0.0   # N
    I8: float = 0.0
    I9: float = 0.0
    I12: float = 0.0
    I13: float = 0.0
    I14: float = 0.0
    J_val: float = 0.0
    capacity_cost: float = field(default_factory=lambda: get_parameters()["cost"]["capacity_cost_yuan_per_kw_month"])


def compute_revenue(inp: RevenueInput) -> DailyRevenue:
    """Compute all 17 revenue values (A-Q) from base inputs.

    This is THE function that all stages must use. It replicates the
    exact Excel formula logic from 充放测算 row 4.

    Args:
        inp: RevenueInput dataclass with all base values and parameters.

    Returns:
        DailyRevenue with all 17 values computed.
    """
    B = inp.charge_volume
    A = inp.charge_price
    C = inp.charge_revenue
    L = inp.discharge_price
    M_val = inp.discharge_volume
    N_val = inp.discharge_revenue

    # P = 综合效率: -discharge / charge
    P = -M_val / B if B != 0 else 0.0

    # Cost components
    D = B * inp.I12                 # 费用1
    E_val = B * inp.I13             # 费用2
    F = B * (1 - P) * inp.I8        # 费用3 (efficiency-adjusted)
    G = B * (1 - P) * inp.I9        # 费用4 (efficiency-adjusted)
    H = B * inp.I14                 # 费用5
    I_val = B * inp.J_val * inp.capacity_cost  # 容量分摊

    # K = 总成本 = C + D + E + F + G + H + I
    K = C + D + E_val + F + G + H + I_val

    # O = 净收益 = N + K (note: K is negative, so O = income - costs)
    O_val = N_val + K

    # Q = 价差 = discharge_price - charge_price
    Q = L - A

    # O6 = 放电收入 + 充电收入 (= N + C)
    o6 = N_val + C

    return DailyRevenue(
        A=A, B=B, C=C, D=D, E=E_val, F=F, G=G, H=H,
        I=I_val, J=inp.J_val, K=K, L=L, M=M_val,
        N=N_val, O=O_val, P=P, Q=Q, O6=o6,
    )


def compute_charge_discharge_from_96point(
    data: ChargeDischargeData,
) -> tuple[float, float, float, float, float, float]:
    """From 96-point charge/discharge data, compute aggregated volumes and prices.

    Used by Stage 02/03 (day-ahead/real-time) to convert raw 96-point
    curves into the 6 base values needed by RevenueInput.

    Convention:
        power < 0 = charging (储能从电网买电)
        power > 0 = discharging (储能向电网卖电)
        Energy = power * 0.25 (MWh, since 15-min intervals)

    Args:
        data: ChargeDischargeData with power_mw and price TimeSeries96.

    Returns:
        (charge_volume_B, charge_price_A, charge_revenue_C,
         discharge_volume_M, discharge_price_L, discharge_revenue_N)
    """
    charge_vol = 0.0
    discharge_vol = 0.0
    charge_price_sum = 0.0
    discharge_price_sum = 0.0

    for p, pr in zip(data.power_mw.values, data.price.values):
        if p < 0:  # strictly negative = charging
            charge_vol += p  # p is negative
            charge_price_sum += pr * p
        elif p > 0:  # strictly positive = discharging
            discharge_vol += p
            discharge_price_sum += pr * p
        # p == 0: idle, skip

    # Convert MW * 15min → MWh (divide by 4)
    B = charge_vol / 4
    M_val = discharge_vol / 4

    # Weighted average prices
    A = charge_price_sum / charge_vol if charge_vol != 0 else 0.0
    L = discharge_price_sum / discharge_vol if discharge_vol != 0 else 0.0

    # Revenues
    C = A * B   # negative = cost
    N_val = L * M_val  # positive = income

    return B, A, C, M_val, L, N_val


def compute_revenue_from_96point(
    data: ChargeDischargeData,
    I8: float, I9: float, I12: float, I13: float, I14: float,
    J_val: float,
) -> DailyRevenue:
    """Convenience: compute full revenue from 96-point data + parameters.

    Combines compute_charge_discharge_from_96point() + compute_revenue()
    in one call. This is the primary entry point for Stage 02/03.

    Args:
        data: 96-point charge/discharge + price data.
        I8-I14: Parameters from 充放测算.
        J_val: Capacity allocation coefficient.

    Returns:
        DailyRevenue with all 17 computed values.
    """
    B, A, C, M_val, L, N_val = compute_charge_discharge_from_96point(data)
    inp = RevenueInput(
        charge_volume=B,
        charge_price=A,
        charge_revenue=C,
        discharge_volume=M_val,
        discharge_price=L,
        discharge_revenue=N_val,
        I8=I8, I9=I9, I12=I12, I13=I13, I14=I14,
        J_val=J_val,
    )
    return compute_revenue(inp)


def compute_revenue_from_settlement(
    charge_price: float,      # AC29
    charge_volume: float,     # -AB29
    charge_revenue: float,    # -AD29
    discharge_price: float,   # P101
    discharge_volume: float,  # AO101
    discharge_revenue: float, # Q101
    I8: float, I9: float, I12: float, I13: float, I14: float,
    J_val: float,
) -> DailyRevenue:
    """Compute revenue from settlement sheet base values.

    This is the primary entry point for Stage 04/05 settlement path.
    Uses the same compute_revenue() function but with inputs read
    directly from 充电/放电日清算费用 sheets.

    Args:
        charge_price: From AC29.
        charge_volume: From -AB29 (already negated).
        charge_revenue: From -AD29 (already negated).
        discharge_price: From P101.
        discharge_volume: From AO101.
        discharge_revenue: From Q101.
        I8-I14: Parameters from 充放测算 I column.
        J_val: Capacity allocation coefficient.

    Returns:
        DailyRevenue with all 17 computed values.
    """
    inp = RevenueInput(
        charge_volume=charge_volume,
        charge_price=charge_price,
        charge_revenue=charge_revenue,
        discharge_volume=discharge_volume,
        discharge_price=discharge_price,
        discharge_revenue=discharge_revenue,
        I8=I8, I9=I9, I12=I12, I13=I13, I14=I14,
        J_val=J_val,
    )
    return compute_revenue(inp)