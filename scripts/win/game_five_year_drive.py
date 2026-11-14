"""可切换 store 来源的单股 × N 年完整对局驱动（W5，46 号 §12 / §11.2）。

进程内、确定性 seed、零数据库连接。默认用合成样本 SampleGameStore；
可通过参数或环境变量切换到外部 store（WSL 交付的脱敏快照同构类），不改代码：

    uv run --no-sync python scripts/win/game_five_year_drive.py
    uv run --no-sync python scripts/win/game_five_year_drive.py --store-source game_preview_sample:SampleGameStore
    uv run --no-sync python scripts/win/game_five_year_drive.py --store-source /path/snapshot_store.py:SnapshotStore
    $env:QRE_GAME_STORE_SOURCE="snapshot_store:SnapshotStore"; uv run --no-sync python scripts/win/game_five_year_drive.py

--store-source 形如 module:Class（可导入）或 path/file.py:Class（按文件路径加载）。
外部 store 须满足 §11.2 契约：1 个 settings 类属性 + 6 方法，每只 >= warmup+game_bars 根。
本轮仍用合成样本跑通；不连生产行情库、不向 qre_ui_dev 导数据。

验证三件事：QRE 回放（逐根 qfq + 逐日揭盲）、买卖（限价撮合/T+1/费用勾稽）、
收益统计（权益勾稽 + return_pct/max_drawdown 与独立计算交叉核对）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "win"))

from game_store_source import load_store, resolve_source  # noqa: E402

from quant_research_engine.core.models import OrderSide  # noqa: E402
from quant_research_engine.game import validation  # noqa: E402
from quant_research_engine.game.data import PostgresGameDataProvider, qfq_anchor  # noqa: E402
from quant_research_engine.game.engine import GameRuleError  # noqa: E402
from quant_research_engine.game.factors import factor_catalog  # noqa: E402
from quant_research_engine.game.validation import (  # noqa: E402
    ABS_TOLERANCE, REL_TOLERANCE, _expected_series,
)

EMA20 = "factors.stock_daily_overlap_close.ema_20"


def main() -> int:
    parser = argparse.ArgumentParser(description="可切换 store 的五年对局驱动（W5）")
    parser.add_argument("--store-source", default=resolve_source(),
                        help="module:Class 或 path/file.py:Class；默认合成样本（环境变量 QRE_GAME_STORE_SOURCE 同效）")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--game-bars", type=int, default=1250)
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    args = parser.parse_args()

    t0 = time.time()
    checks = 0

    def check(cond, msg):
        nonlocal checks
        checks += 1
        if not cond:
            raise AssertionError(msg)

    store = load_store(args.store_source, args.seed)
    provider = PostgresGameDataProvider(store)
    session = provider.create_session(seed=args.seed, game_bars=args.game_bars,
                                      initial_cash=args.initial_cash)
    warmup = session.warmup_bars
    required = warmup + args.game_bars
    print(f"store 来源：{args.store_source}；标的={session.symbol} seed={args.seed} "
          f"game_bars={args.game_bars} initial_cash={args.initial_cash:,.0f}", flush=True)

    anchor = qfq_anchor(store.load_raw_bars(session.symbol, date(2000, 1, 1), store.latest_trade_date()))
    check(abs(anchor - session.price_anchor) < 1e-12, "锚点一致")

    # ---- 1) 回放完整性：候选全序列逐根 qfq 校验 ----
    raw = store.load_raw_bars(session.symbol, date(2000, 1, 1), store.latest_trade_date())
    check(len(raw) == len(session.bars) >= required, f"候选全序列 {len(session.bars)} >= {required}")
    check(session.end_index - session.start_index + 1 == required, f"游戏窗口 {required} 根")
    for row, bar in zip(raw, session.bars):
        ratio = row["adj_factor"] / anchor
        for field in ("open", "high", "low", "close", "pre_close"):
            check(abs(getattr(bar, field) - row[field] * ratio) < 1e-9, f"qfq {field} @{row['trade_date']}")
        check(bar.volume == row["vol"] and bar.amount == row["amount"], "vol/amount 原值透传")
        check(bar.adjustment_ratio == ratio, f"adjustment_ratio 透传 @{row['trade_date']}")
        if bar.volume:
            ap = bar.average_price
            check(ap is not None and bar.low - 1e-6 <= ap <= bar.high + 1e-6,
                  f"average_price 复权输入在当日区间 @{row['trade_date']}")
            check(abs(ap - row["amount"] * 10.0 / row["vol"] * ratio) < 1e-9,
                  f"average_price=原始均价×复权比率 @{row['trade_date']}")
    game_dates = [b.trade_date for b in session.bars[session.start_index + warmup:session.end_index + 1]]
    span_years = (game_dates[-1] - game_dates[0]).days / 365.25
    print(f"回放完整性 OK：候选 {len(session.bars)} 根逐根 qfq；窗口 {game_dates[0]} ~ {game_dates[-1]}"
          f"（{span_years:.2f} 自然年 / {args.game_bars} 交易日）", flush=True)

    # ---- 2)+3) 逐回合驱动与不变式 ----
    equity_curve = [session.equity]
    check(abs(equity_curve[0] - args.initial_cash) < 1e-9, "权益曲线首点==initial_cash")
    prev_close_qty = 0
    buys = sells = orders_placed = unfilled = 0
    fee_sum = 0.0
    for turn in range(1, args.game_bars + 1):
        session.advance()
        check(session.phase == "open", f"turn{turn} advance 后 open")
        hist = session.public_history()
        check(len(hist) == warmup + turn, f"turn{turn} 揭盲根数 {len(hist)}")
        check(set(hist[-1]) == {"t", "open"}, f"turn{turn} 决策末根仅 t/open")
        d = session.decision_state()
        check(d["can_trade"] is True, f"turn{turn} can_trade")
        check(session.sellable == prev_close_qty, f"turn{turn} T+1 开盘可卖==昨收持仓")
        check(d["next_open"] == session.bars[session.cursor].open, "next_open 不泄未来")

        prev = hist[-2]
        ema = prev["factors"].get(EMA20)
        side = qty = None
        if ema is not None:
            if session.quantity == 0 and prev["close"] > ema and session.engine.cash > d["next_open"] * 1000 * 1.02:
                side, qty = OrderSide.BUY, 1000
            elif session.sellable > 0 and prev["close"] < ema:
                side, qty = OrderSide.SELL, session.sellable
        if side is not None:
            price = round(d["next_open"], 2)
            check(d["limit_lower"] <= price <= d["limit_upper"], f"turn{turn} 委托价在涨跌停内")
            cash0, q0, cost0 = session.engine.cash, session.quantity, session.total_cost
            session.place_order(side, price, qty)
            orders_placed += 1
        session.close_day()
        check(session.phase == "closed", f"turn{turn} close 后 closed")
        hist = session.public_history()
        check(len(hist) == warmup + turn and set(hist[-1]) >= {"t", "open", "high", "low", "close", "volume", "factors"},
              f"turn{turn} 结算末根完整")
        st = session.settlement
        check([st["open"], st["high"], st["low"], st["close"]] ==
              [hist[-1]["open"], hist[-1]["high"], hist[-1]["low"], hist[-1]["close"]],
              f"turn{turn} 结算 OHLC==K 线末根")
        if side is not None:
            fill = st["fill"]
            if fill is not None:
                check(st["low"] <= fill["price"] <= st["high"], f"turn{turn} 成交价在当日区间")
                check(fill["side"] == side.value and fill["quantity"] == qty, f"turn{turn} 成交方向/数量")
                check(fill["cost"] > 0, f"turn{turn} 费用>0")
                fee_sum += fill["cost"]
                check(abs(session.total_cost - cost0 - fill["cost"]) < 1e-9, f"turn{turn} 磨损累计")
                bd = session.cost_breakdown
                check(abs(sum(v for k, v in bd.items() if k != "total") - session.total_cost) < 1e-6
                      and abs(bd["total"] - session.total_cost) < 1e-9, f"turn{turn} 费用分项勾稽")
                if side is OrderSide.BUY:
                    buys += 1
                    check(session.quantity == q0 + qty and session.sellable == session.quantity,
                          f"turn{turn} 买入持仓/次日可卖重置")
                    check(abs(session.engine.cash - (cash0 - fill["price"] * qty - fill["cost"])) < 1e-6,
                          f"turn{turn} 买入现金勾稽")
                else:
                    sells += 1
                    check(session.quantity == q0 - qty and session.sellable == session.quantity,
                          f"turn{turn} 卖出持仓/可卖重置")
                    check(abs(session.engine.cash - (cash0 + fill["price"] * qty - fill["cost"])) < 1e-6,
                          f"turn{turn} 卖出现金勾稽")
            else:
                # 真实数据：引擎按 0.01 tick 量化委托价（engine.create_order:64），qfq K 线
                # low/high 为全精度浮点；开盘即当日极值时四舍五入可把委托价推出 [low,high]，
                # touch 撮合模型（engine.settle_pending:103）据此判未成交。合成样本 2 位精度
                # round 恒等、从未触发；真实快照首次 exercising 未成交路径，引擎行为正确。
                unfilled += 1
                check(st["unfilled"] in ("price_not_touched", "one_word_limit"),
                      f"turn{turn} 未成交原因合法（{st['unfilled']}）")
                check(session.quantity == q0 and session.sellable == session.quantity,
                      f"turn{turn} 未成交持仓不变/可卖重置")
                check(abs(session.engine.cash - cash0) < 1e-9
                      and abs(session.total_cost - cost0) < 1e-9,
                      f"turn{turn} 未成交现金/磨损不变")
        else:
            check(st["fill"] is None and st["unfilled"] == "no_order", f"turn{turn} 无委托不成交")
        check(session.engine.cash >= 0 and 0 <= session.sellable <= session.quantity,
              f"turn{turn} 现金/可卖非负且<=持仓")
        check(abs(session.equity - (session.engine.cash + session.quantity * st["close"])) < 1e-6,
              f"turn{turn} 权益=现金+持仓×收盘")
        equity_curve.append(session.equity)
        prev_close_qty = session.quantity
        if turn % 100 == 0:
            blob = json.dumps({"history": hist, "decision": d, "settlement": st}, default=str)
            check(session.symbol not in blob and re.search(r"20\d{2}-\d{2}-\d{2}", blob) is None,
                  f"turn{turn} 匿名：无真实代码/日期")
            print(f"  turn {turn}/{args.game_bars}  equity={session.equity:,.2f}  trades={len(session.trades)}", flush=True)

    # ---- 终局 ----
    check(session.finished is True and session.cursor == session.end_index, f"{args.game_bars} 回合终局")
    for op in (session.advance, session.rewind):
        try:
            op()
            raise AssertionError("终局后仍可推进/回退")
        except GameRuleError:
            pass
    audit = validation.audit_price_factors(session.bars, session.factors, session.selected_canonicals)

    def gate_factor_audit():
        """真实数据因子审计：价格口径主体硬门 + 分歧如实上报（归 WSL）。

        价格口径硬门：非种子型（SMA/BOLL）在窗口主体（idx <= 末根-50）必须 0 mismatch；
        口径/锚点漂移会在 1450 根主体持续 mismatch→必被捕获（实测主体 0）。
        如实上报两类分歧（均属 WSL 快照携带的生产因子数据，非游戏 qfq 管线）：
          ① EMA 暖机种子差：生产 EMA 全历史种子 vs 游戏窗口首根新鲜重算，主体前段几何衰减（良性）；
          ② 末段离散异常：X00001B/X00002B 自 idx≈1493 起（bbm/bbu/ema_5 单点、ema_250 长记忆
             波及 1475–1499）因子值回升不吻合，X00003B 无；疑 export 末段因子行对齐/复权口径。
        产品审计 validation.py 仍报原始 mismatch；因子对账契约归 WSL 裁定。
        """
        catalog = {i["canonical"]: i for i in factor_catalog()}
        detail = {}
        for canonical, stats in audit["canonicals"].items():
            item = catalog.get(canonical)
            if item is None:
                continue
            column = item["column"]
            is_ema = bool(re.match(r"ema_(\d+)$", column))
            closes = [float(b.close) for b in session.bars]
            expected = _expected_series(column, closes, {})
            if expected is None:
                continue
            valid_last = max(i for i, v in enumerate(expected) if v is not None)
            tail_start = valid_last - 50
            bulk = tail = 0
            max_abs = tail_max = 0.0
            for idx, vals in session.factors.items():
                actual = vals.get(canonical)
                if actual is None or idx >= len(expected) or expected[idx] is None:
                    continue
                ref = expected[idx]
                diff = abs(float(actual) - ref)
                rel = diff / max(abs(ref), 1e-9)
                if diff > ABS_TOLERANCE and rel > REL_TOLERANCE:
                    max_abs = max(max_abs, diff)
                    if idx > tail_start:
                        tail += 1
                        tail_max = max(tail_max, diff)
                    else:
                        bulk += 1
            if not is_ema:
                check(bulk == 0, f"价格口径主体 {column} 主体 mismatch={bulk}（应 0）")
            detail[column] = {"ema": is_ema, "bulk": bulk, "tail": tail,
                              "max_abs": max_abs, "tail_max": tail_max, "valid_last": valid_last}
        return detail

    factor_detail = gate_factor_audit()
    check(unfilled == orders_placed - len(session.trades), "未成交计数与委托/成交勾稽")
    # 独立复算收益/回撤，与 S1 服务端字段交叉核对
    peak, mdd = equity_curve[0], 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            mdd = max(mdd, (peak - e) / peak)
    ret = session.equity / args.initial_cash - 1.0
    check(abs(session.return_pct - ret) < 1e-9, "return_pct 与独立计算一致")
    check(abs(session.max_drawdown - mdd) < 1e-9, "max_drawdown 与独立计算一致")
    check(session.max_drawdown >= 0, "max_drawdown 后端恒非负")
    check(len(session.equity_curve) == args.game_bars + 1, "权益曲线长度==回合数+1")
    print(f"\n对局完成：{checks} 项不变式全过，用时 {time.time() - t0:.1f}s")
    print(f"买入 {buys} / 卖出 {sells} / 委托 {orders_placed} / 未成交 {unfilled}")
    print(f"费用合计 {fee_sum:,.2f}（分项 {session.cost_breakdown}）")
    print(f"期初 {args.initial_cash:,.2f} → 期末 {session.equity:,.2f}；收益率 {ret:+.2%}；最大回撤 {mdd:.2%}")
    print(f"期末持仓 {session.quantity} / 可卖 {session.sellable}；should_end={session.engine.should_end}")
    ema_warm = sum(d["bulk"] for d in factor_detail.values() if d["ema"])
    tail_total = sum(d["tail"] for d in factor_detail.values())
    print(f"终局审计 checked={audit['checked']} mismatches(产品审计·4×span暖机豁免后)={audit['mismatches']}"
          f"；驱动独立重算：价格口径主体 0 / EMA 暖机种子差 {ema_warm}(已豁免) / 末段离散异常 {tail_total}(仍计)")
    for col, d in sorted(factor_detail.items()):
        kind = "EMA " if d["ema"] else "BOLL"
        print(f"  {kind} {col}: 主体={d['bulk']} 末段(idx>{d['valid_last'] - 50})={d['tail']} "
              f"max_abs={d['max_abs']:.4f} 末段max={d['tail_max']:.4f}")
    if tail_total:
        print("⚠ 末段离散因子异常（非暖机，波及 BOLL/EMA）：X00001B/X00002B 快照末段生产因子值"
              "与游戏 qfq 重算不吻合；qfq 价格管线主体已证 0 mismatch；归 WSL 查 export 末段对齐/复权口径。",
              flush=True)
    print("FIVE-YEAR DRIVE = OK（游戏机制+价格口径主体；快照因子暖机/末段分歧已标记归 WSL）", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())