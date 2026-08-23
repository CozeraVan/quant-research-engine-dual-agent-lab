"""衍生品行情只读适配层（CR docs/frm/CR_2026-08-23_derivatives_market_data.md，D1.5/D2.2/D3.2）。

QRE 对业务库只读；本模块是唯一直接读 `derivatives` schema 的代码，
把库内数据适配成 risk 内核（rates/bonds/options）的入参契约。

口径披露（与 CR §6 验收一致）：

- 零息曲线：`derivatives.yc_curve` 中债国债收益率曲线（即期，curve_type='1'），
  yield 为百分数年化（如 2.35 = 2.35%），视为 1 年一期复利，
  经 `rates.periodic_to_continuous(rate, 1)` 转连续复利——**该转换为近似**
  （中债即期收益率本身非年复利口径）；曲线仅 8 个期限节点
  （0.25/0.5/1/3/5/7/10/30 年），节点间期限由内核插值（linear/log_linear）补齐。
  请求的 trade_date 当日无数据时，取 ≤ trade_date 的最近有数据日
  （`latest_curve_date` 可查实际使用日期）。
- 转债债底：cb_basic 票面利率为累进票息的参考值，债底现金流按常数票息近似；
  付息时点沿用 `bonds.coupon_schedule` 的「估值日=付息日」口径，
  剩余期限取整到付息网格。债底对比 `cb_daily.bond_value` 的差异可解释
  （信用利差假设、票息近似、应计利息口径），见示例脚本输出。
- 期权链：`opt_daily.settle` 为期权市价（结算价口径，比 close 稳），
  到期时间 T = (maturity_date − trade_date)/365（actual/365，近似）；
  无风险利率取当日曲线 0.25 年节点。标的价格优先读 `public.stock_daily`，
  其次 `reference.index_daily`；库内暂无 ETF 日线（510050.SH 不在两表中），
  此时须由调用方传入 `underlying_price`（示例脚本用平值合约 put-call parity
  反推标的价格，已在结果中披露）。
"""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from quant_research_engine.data.settings import DatabaseSettings
from quant_research_engine.risk import bonds, options, rates

YC_CURVE_TABLE = "derivatives.yc_curve"
YC_CURVE_NAME = "中债国债收益率曲线"
YC_CURVE_TYPE = "1"  # 即期
CB_BASIC_TABLE = "derivatives.cb_basic"
CB_DAILY_TABLE = "derivatives.cb_daily"
OPT_BASIC_TABLE = "derivatives.opt_basic"
OPT_DAILY_TABLE = "derivatives.opt_daily"

# 平值隐波健全性区间（CR D3 验收：1%–150%）
ATM_IV_BOUNDS = (0.01, 1.5)
# 示例默认信用利差（连续复利，小数）；CR 不做评级映射，由调用方给定
DEFAULT_CREDIT_SPREAD = 0.01


@lru_cache(maxsize=1)
def _default_engine() -> Engine:
    """按 QRE_MARKET_DB_URL（或 SR_MARKET_DB_URL）建默认引擎（进程内单例）。"""
    return create_engine(DatabaseSettings.from_env().market_db_url)


def _resolve_engine(engine: Engine | None) -> Engine:
    return engine if engine is not None else _default_engine()


def _as_date(value: date | datetime | str) -> date:
    """接受 date / datetime / 'YYYY-MM-DD' 或 'YYYYMMDD' 字符串。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text_value = value.strip()
    fmt = "%Y-%m-%d" if "-" in text_value else "%Y%m%d"
    return datetime.strptime(text_value, fmt).date()


def yield_percent_to_continuous(yield_percent: float) -> float:
    """yc_curve 的 yield（百分数年化）→ 连续复利零息率（小数）。

    口径：÷100 后视为 1 年一期复利，经式 16.4 Rc = ln(1+Rm) 转连续——
    近似口径，见模块 docstring 披露。
    """
    return float(rates.periodic_to_continuous(float(yield_percent) / 100.0, 1)["rate_out"])


def latest_curve_date(trade_date: date | str, engine: Engine | None = None) -> date | None:
    """≤ trade_date 的最近有「中债国债收益率曲线（即期）」数据的交易日；无则 None。"""
    query = text(
        f"""
        SELECT MAX(trade_date)
        FROM {YC_CURVE_TABLE}
        WHERE curve_name = :curve_name AND curve_type = :curve_type AND trade_date <= :trade_date
        """
    )
    with _resolve_engine(engine).begin() as conn:
        value = conn.execute(
            query, {"curve_name": YC_CURVE_NAME, "curve_type": YC_CURVE_TYPE, "trade_date": _as_date(trade_date)}
        ).scalar_one_or_none()
    return value


def load_zero_curve(trade_date: date | str, engine: Engine | None = None) -> dict[float, float]:
    """当日（或 ≤ trade_date 最近有数据日）零息曲线 {期限年: 连续复利零息率}。

    读 derivatives.yc_curve 即期曲线；实际使用的日期可用
    `latest_curve_date(trade_date)` 查询。转换与插值近似见模块 docstring。
    """
    actual_date = latest_curve_date(trade_date, engine)
    if actual_date is None:
        raise ValueError(f"yc_curve 在 {_as_date(trade_date)} 及之前无数据")
    query = text(
        f"""
        SELECT curve_term, yield
        FROM {YC_CURVE_TABLE}
        WHERE curve_name = :curve_name AND curve_type = :curve_type AND trade_date = :trade_date
        ORDER BY curve_term
        """
    )
    with _resolve_engine(engine).begin() as conn:
        rows = conn.execute(
            query, {"curve_name": YC_CURVE_NAME, "curve_type": YC_CURVE_TYPE, "trade_date": actual_date}
        ).fetchall()
    curve = {
        float(row[0]): yield_percent_to_continuous(row[1])
        for row in rows
        if row[0] is not None and row[1] is not None and float(row[0]) > 0
    }
    if len(curve) < 2:
        raise ValueError(f"yc_curve {actual_date} 有效节点不足 2 个")
    return curve


def load_cb_terms(ts_code: str, engine: Engine | None = None) -> dict[str, object]:
    """转债条款（cb_basic）：票面利率（%）、面值、付息频率、到期日等。

    coupon_rate 为累进票息的参考值（tushare cb_basic 口径），
    精确逐年票息需 cb_coupon（本 CR 不接入，见模块 docstring 披露）。
    """
    query = text(
        f"""
        SELECT ts_code, bond_short_name, stk_code, coupon_rate, par, maturity,
               pay_per_year, value_date, maturity_date, list_date, delist_date, conv_price
        FROM {CB_BASIC_TABLE}
        WHERE ts_code = :ts_code
        """
    )
    with _resolve_engine(engine).begin() as conn:
        row = conn.execute(query, {"ts_code": ts_code}).mappings().one_or_none()
    if row is None:
        raise ValueError(f"cb_basic 无 {ts_code} 条款")
    return dict(row)


def cb_cashflows(terms: dict[str, object], as_of: date | str) -> dict[str, object]:
    """由转债条款生成债底现金流 (times, amounts)（纯函数，近似口径）。

    用 `bonds.coupon_schedule`：剩余期限 = (maturity_date − as_of)/365
    取整到 1/pay_per_year 付息网格（kernel 要求期限落在网格上，
    「估值日=付息日」口径，无应计利息），票息按常数 coupon_rate 近似。
    """
    as_of_date = _as_date(as_of)
    maturity_date = terms.get("maturity_date")
    if maturity_date is None:
        raise ValueError("cb_basic.maturity_date 为空，无法构建现金流")
    if isinstance(maturity_date, str):
        maturity_date = _as_date(maturity_date)
    face = float(terms.get("par") or 100.0)
    coupon_rate = float(terms.get("coupon_rate") or 0.0) / 100.0
    frequency = int(terms.get("pay_per_year") or 1)
    if frequency < 1:
        frequency = 1  # pay_per_year=0 为异常值，按年付处理（披露）
    remaining = (maturity_date - as_of_date).days / 365.0
    if remaining <= 0:
        raise ValueError(f"{terms.get('ts_code')} 已于 {maturity_date} 到期")
    # 取整到付息网格，至少一期（近似，披露于结果 note）
    grid_maturity = max(round(remaining * frequency), 1) / frequency
    schedule = bonds.coupon_schedule(face, coupon_rate, grid_maturity, frequency)
    return {
        "ts_code": terms.get("ts_code"),
        "as_of": as_of_date,
        "times": schedule["times"],
        "amounts": schedule["amounts"],
        "face": face,
        "coupon_rate": coupon_rate,
        "frequency": frequency,
        "remaining_years": remaining,
        "grid_maturity": grid_maturity,
        "note": "近似：累进票息按常数 coupon_rate；剩余期限取整到付息网格、"
        "估值日=付息日（无应计）——与 cb_daily.bond_value 差异由此可解释",
    }


def cb_bond_floor(
    ts_code: str,
    trade_date: date | str,
    credit_spread: float = DEFAULT_CREDIT_SPREAD,
    engine: Engine | None = None,
) -> dict[str, object]:
    """转债债底示例管道：cb_basic 现金流 + 当日零息曲线 → convertible_bond_floor。

    返回内核结果 + 同日 cb_daily.bond_value 对比（验证用，不求一致，
    差异口径：信用利差假设、票息近似、应计利息，见模块 docstring）。
    """
    resolved = _resolve_engine(engine)
    as_of = _as_date(trade_date)
    terms = load_cb_terms(ts_code, resolved)
    cashflows = cb_cashflows(terms, as_of)
    curve = load_zero_curve(as_of, resolved)
    floor = bonds.convertible_bond_floor(cashflows["times"], cashflows["amounts"], curve, credit_spread)

    bond_value = None
    value_date = None
    query = text(
        f"""
        SELECT trade_date, bond_value
        FROM {CB_DAILY_TABLE}
        WHERE ts_code = :ts_code AND trade_date <= :trade_date AND bond_value IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT 1
        """
    )
    with resolved.begin() as conn:
        row = conn.execute(query, {"ts_code": ts_code, "trade_date": as_of}).one_or_none()
    if row is not None:
        value_date, bond_value = row[0], float(row[1])

    diff = None if bond_value is None else float(floor["pure_bond_value"]) - bond_value
    return {
        **floor,
        "ts_code": ts_code,
        "as_of": as_of,
        "curve_date": latest_curve_date(as_of, resolved),
        "cashflows": cashflows,
        "cb_daily_bond_value": bond_value,
        "cb_daily_value_date": value_date,
        "diff_vs_cb_daily": diff,
        "note": floor["note"] + "；" + str(cashflows["note"]),
    }


def load_underlying_close(
    underlying: str,
    trade_date: date | str,
    engine: Engine | None = None,
) -> dict[str, object]:
    """标的当日（或 ≤ trade_date 最近）收盘价：先 public.stock_daily，后 reference.index_daily。

    库内暂无 ETF 日线时抛 ValueError，由调用方改用 underlying_price 传参。
    """
    resolved = _resolve_engine(engine)
    as_of = _as_date(trade_date)
    for table in ("public.stock_daily", "reference.index_daily"):
        query = text(
            f"""
            SELECT trade_date, close
            FROM {table}
            WHERE ts_code = :ts_code AND trade_date <= :trade_date
            ORDER BY trade_date DESC
            LIMIT 1
            """
        )
        with resolved.begin() as conn:
            row = conn.execute(query, {"ts_code": underlying, "trade_date": as_of}).one_or_none()
        if row is not None:
            return {"underlying": underlying, "price": float(row[1]), "price_date": row[0], "source": table}
    raise ValueError(f"{underlying} 在 stock_daily / index_daily 均无收盘价，请用 underlying_price 传参")


def estimate_spot_from_parity(
    call_price: float,
    put_price: float,
    strike: float,
    r: float,
    T: float,
) -> float:
    """put-call parity 反推标的价格 S = (C − P) + K·e^{−rT}（纯函数，欧式近似）。

    供库内缺 ETF 日线时估计 50ETF/300ETF 现货价；差异口径：忽略股息、
    买卖价差与结算价时点差，仅作冒烟/示例用途（披露于示例输出）。
    """
    if T <= 0:
        raise ValueError("T must be > 0")
    return float(call_price - put_price + strike * np.exp(-r * T))


def _load_chain_frame(trade_date: date, underlying: str, engine: Engine) -> pd.DataFrame:
    """opt_daily(settle) JOIN opt_basic 取期权链（opt_code 前缀匹配标的），附 T（actual/365）。"""
    prefix = underlying.split(".", maxsplit=1)[0]
    query = text(
        f"""
        SELECT d.ts_code, d.trade_date, b.call_put, b.exercise_price, b.maturity_date,
               d.settle, d.close, d.vol, d.oi
        FROM {OPT_DAILY_TABLE} d
        JOIN {OPT_BASIC_TABLE} b ON b.ts_code = d.ts_code
        WHERE d.trade_date = :trade_date AND b.opt_code LIKE :prefix
        ORDER BY b.maturity_date, b.exercise_price, b.call_put
        """
    )
    frame = pd.read_sql_query(sql=query, con=engine, params={"trade_date": trade_date, "prefix": f"{prefix}%"})
    if frame.empty:
        raise ValueError(f"{trade_date} 无 {underlying} 期权行情（opt_daily/opt_basic join 为空）")
    frame["call_put"] = frame["call_put"].map({"C": "call", "P": "put"})
    frame["T"] = (pd.to_datetime(frame["maturity_date"]) - pd.Timestamp(trade_date)).dt.days / 365.0
    return frame[frame["T"] > 0].reset_index(drop=True)


def load_option_chain(
    trade_date: date | str,
    underlying: str = "510050.SH",
    engine: Engine | None = None,
    underlying_price: float | None = None,
) -> dict[str, object]:
    """期权链适配：opt_daily(settle) JOIN opt_basic + 标的价 + 短端无风险利率 → 平值隐波。

    - opt_code 前缀匹配标的（510050.SH → '510050%'）。
    - T = (maturity_date − trade_date)/365（actual/365 近似，披露）。
    - 无风险利率取当日曲线 0.25 年节点（缺失时取曲线最短端节点）。
    - 逐合约用 options.implied_vol 反解隐波（不可定价的合约 iv 记 None）。
    - 平值 = 行权价最接近标的价格的合约对；健全性断言：平值 call/put
      隐波均在 (1%, 150%)（CR D3 验收），越界抛 AssertionError。
    """
    resolved = _resolve_engine(engine)
    as_of = _as_date(trade_date)

    if underlying_price is not None:
        spot, spot_source, spot_date = float(underlying_price), "caller_provided", as_of
    else:
        spot_info = load_underlying_close(underlying, as_of, resolved)
        spot = float(spot_info["price"])
        spot_source = str(spot_info["source"])
        spot_date = spot_info["price_date"]

    curve = load_zero_curve(as_of, resolved)
    r = curve[0.25] if 0.25 in curve else curve[min(curve)]

    frame = _load_chain_frame(as_of, underlying, resolved)

    ivs: list[float | None] = []
    for row in frame.itertuples():
        try:
            iv = options.implied_vol(
                float(row.settle), spot, float(row.exercise_price), r, float(row.T), row.call_put
            )["implied_vol"]
        except ValueError:
            iv = None  # 深实/虚值结算价超出 BSM 可定价区间，记 None 不阻塞
        ivs.append(iv)
    frame["implied_vol"] = ivs

    # 平值合约对：行权价最接近标的价格、取最近到期月
    first_maturity = frame["maturity_date"].min()
    near = frame[frame["maturity_date"] == first_maturity]
    atm_strike = float(near.iloc[(near["exercise_price"] - spot).abs().argmin()]["exercise_price"])
    atm_rows = near[near["exercise_price"] == atm_strike]
    atm: dict[str, float | None] = {"strike": atm_strike}
    for option_type in ("call", "put"):
        match = atm_rows[atm_rows["call_put"] == option_type]
        atm[f"{option_type}_iv"] = None if match.empty else match.iloc[0]["implied_vol"]
    for option_type in ("call", "put"):
        iv = atm[f"{option_type}_iv"]
        if iv is not None:
            assert ATM_IV_BOUNDS[0] <= iv <= ATM_IV_BOUNDS[1], (
                f"{as_of} {underlying} 平值 {option_type} 隐波 {iv:.2%} 越出 {ATM_IV_BOUNDS} 健全区间"
            )
    return {
        "trade_date": as_of,
        "underlying": underlying,
        "spot": spot,
        "spot_source": spot_source,
        "spot_date": spot_date,
        "risk_free_rate": r,
        "curve_date": latest_curve_date(as_of, resolved),
        "atm": atm,
        "chain": frame,
        "note": "市价=settle（结算价）；T=actual/365；r=0.25 年节点（连续复利近似）；"
        "隐波 brentq 反解，越界合约记 None；平值隐波健全区间 (1%, 150%)",
    }
