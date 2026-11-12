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
import importlib
import importlib.util
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "win"))

from quant_research_engine.core.models import OrderSide  # noqa: E402
from quant_research_engine.game import validation  # noqa: E402
from quant_research_engine.game.data import PostgresGameDataProvider, qfq_anchor  # noqa: E402
from quant_research_engine.game.engine import GameRuleError  # noqa: E402

EMA20 = "factors.stock_daily_overlap_close.ema_20"


def load_store(source: str, seed: int):
    """按 module:Class 或 path/file.py:Class 加载 store；零数据库连接。"""
    if ":" not in source:
        raise SystemExit("--store-source 须为 module:Class 或 path/file.py:Class")
    mod_part, cls_name = source.rsplit(":", 1)
    if mod_part.endswith(".py") or "/" in mod_part or os.path.sep in mod_part:
        path = Path(mod_part).resolve()
        spec = importlib.util.spec_from_file_location("_qre_game_ext_store", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(mod_part)
    cls = getattr(module, cls_name)
    try:
        return cls(seed=seed)
    except TypeError:
        return cls()


def main() -> int:
    parser = argparse.ArgumentParser(description="可切换 store 的五年对局驱动（W5）")
    parser.add_argument("--store-source",
                        default=os.environ.get("QRE_GAME_STORE_SOURCE", "game_preview_sample:SampleGameStore"),
                        help="module:Class 或 path/file.py:Class；默认合成样本")
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
    print(f"store 来源：{args.store_source}；seed={args.seed} game_bars={args.game_bars} "
          f"initial_cash={args.initial_cash:,.0f}", flush=True)

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
    game_dates = [b.trade_date for b in session.bars[session.start_index + warmup:session.end_index + 1]]
    span_years = (game_dates[-1] - game_dates[0]).days / 365.25
    print(f"回放完整性 OK：候选 {len(session.bars)} 根逐根 qfq；窗口 {game_dates[0]} ~ {game_dates[-1]}"
          f"（{span_years:.2f} 自然年 / {args.game_bars} 交易日）", flush=True)

    # ---- 2)+3) 逐回合驱动与不变式 ----
    equity_curve = [session.equity]
    check(abs(equity_curve[0] - args.initial_cash) < 1e-9, "权益曲线首点==initial_cash")
    prev_close_qty = 0
    buys = sells = orders_placed = 0
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
            check(fill is not None, f"turn{turn} 开盘价委托必成交（unfilled={st['unfilled']}）")
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
    check(audit["mismatches"] == 0, f"终局审计 {audit['mismatches']}")
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
    print(f"买入 {buys} / 卖出 {sells} / 委托 {orders_placed} / 未成交 {orders_placed - len(session.trades)}")
    print(f"费用合计 {fee_sum:,.2f}（分项 {session.cost_breakdown}）")
    print(f"期初 {args.initial_cash:,.2f} → 期末 {session.equity:,.2f}；收益率 {ret:+.2%}；最大回撤 {mdd:.2%}")
    print(f"期末持仓 {session.quantity} / 可卖 {session.sellable}；should_end={session.engine.should_end}")
    print(f"终局审计 checked={audit['checked']} mismatches=0")
    print("FIVE-YEAR DRIVE = OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())