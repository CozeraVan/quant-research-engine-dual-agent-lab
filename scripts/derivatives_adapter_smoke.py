"""衍生品适配层示例管道（CR D1.5/D2.2/D3.2 验收冒烟，只读业务库）。

用法：
    QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data uv run python scripts/derivatives_adapter_smoke.py [trade_date]

输出三段：
1. 零息曲线：节点数与首尾值（yield% ÷100 视为年复利 → 连续复利，近似口径披露）。
2. 转债债底：5 只存续转债 convertible_bond_floor vs cb_daily.bond_value
   （差异可解释：信用利差假设 100bp、累进票息常数近似、估值日=付息日无应计）。
3. 50ETF 期权链：平值 call/put 隐波。库内暂无 ETF 日线（510050.SH 不在
   stock_daily/index_daily），标的价格用平值合约 put-call parity 反推（欧式
   近似，忽略股息与价差，仅作示例），已在输出中披露。
"""

from __future__ import annotations

import sys

from quant_research_engine.data import derivatives

CB_SAMPLE = ["113052.SH", "113042.SH", "110085.SH", "113056.SH", "127045.SZ"]
UNDERLYING = "510050.SH"
CREDIT_SPREAD = derivatives.DEFAULT_CREDIT_SPREAD


def main(trade_date: str) -> None:
    print(f"== 衍生品适配层冒烟 @ 请求日 {trade_date} ==")

    curve_date = derivatives.latest_curve_date(trade_date)
    curve = derivatives.load_zero_curve(trade_date)
    terms = sorted(curve)
    print(f"\n[1] 零息曲线（实际使用日期 {curve_date}，{len(curve)} 节点，连续复利近似口径）")
    print(f"    首节点 {terms[0]} 年: {curve[terms[0]]:.4%}   末节点 {terms[-1]} 年: {curve[terms[-1]]:.4%}")
    print(f"    全部节点: " + ", ".join(f"{t}y={curve[t]:.3%}" for t in terms))

    print(f"\n[2] 转债债底（credit_spread={CREDIT_SPREAD:.2%} 连续复利假设）vs cb_daily.bond_value")
    for ts_code in CB_SAMPLE:
        try:
            result = derivatives.cb_bond_floor(ts_code, trade_date, credit_spread=CREDIT_SPREAD)
            diff = result["diff_vs_cb_daily"]
            diff_text = "N/A" if diff is None else f"{diff:+.2f}"
            print(
                f"    {ts_code}: 债底 {result['pure_bond_value']:.2f} vs "
                f"bond_value {result['cb_daily_bond_value']} ({result['cb_daily_value_date']}) "
                f"diff {diff_text} | spread_duration {result['spread_duration']:.2f} | "
                f"期限 {result['cashflows']['grid_maturity']:.1f}y 票息 {result['cashflows']['coupon_rate']:.2%}"
            )
        except (ValueError, KeyError) as exc:
            print(f"    {ts_code}: 跳过（{exc}）")
    print("    差异口径：信用利差假设、累进票息常数近似、估值日=付息日（无应计）、税；不求数值一致")

    print(f"\n[3] {UNDERLYING} 期权链平值隐波（T=actual/365，r=0.25y 节点）")
    # 库内暂无 ETF 日线：先用平值合约 put-call parity 反推标的价格（披露）
    r = derivatives.load_zero_curve(trade_date)[0.25]
    chain_frame = derivatives._load_chain_frame(derivatives._as_date(trade_date), UNDERLYING, derivatives._default_engine())
    first_maturity = chain_frame["maturity_date"].min()
    near = chain_frame[chain_frame["maturity_date"] == first_maturity]
    strikes = sorted(near["exercise_price"].unique())
    # 每个行权价 parity 各估一个 S，取 |C−P| 最小（最平值）者，降低价差噪声
    estimates = []
    for strike in strikes:
        pair = near[near["exercise_price"] == strike].set_index("call_put")
        if {"call", "put"} - set(pair.index):
            continue
        T = float(pair.iloc[0]["T"])
        estimates.append(
            (abs(float(pair.loc["call", "settle"]) - float(pair.loc["put", "settle"])), strike, T,
             derivatives.estimate_spot_from_parity(
                 float(pair.loc["call", "settle"]), float(pair.loc["put", "settle"]), float(strike), r, T))
        )
    assert estimates, "无 call/put 成对的行权价，无法 parity 反推"
    _, mid_strike, _, spot = min(estimates)
    print(f"    标的价格 {spot:.4f}（put-call parity 反推 K={mid_strike}，库内无 ETF 日线，披露口径）")
    chain = derivatives.load_option_chain(trade_date, UNDERLYING, underlying_price=spot)
    atm = chain["atm"]
    print(
        f"    平值 K={atm['strike']}（{first_maturity} 到期）: "
        f"call IV {atm['call_iv']:.2%} / put IV {atm['put_iv']:.2%} | "
        f"r={r:.3%}（曲线日 {chain['curve_date']}）"
    )
    lo, hi = derivatives.ATM_IV_BOUNDS
    assert lo <= atm["call_iv"] <= hi and lo <= atm["put_iv"] <= hi, "平值隐波越出健全区间"
    print("    健全性断言通过：平值隐波 ∈ (1%, 150%)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2026-08-21")
