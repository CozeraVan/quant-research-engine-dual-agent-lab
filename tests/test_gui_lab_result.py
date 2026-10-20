"""8081 回测结果可视化页测试（QRE-GUI-LAB-RESULT-023）。

覆盖：/lab/runs/<id> 页面 200、/api/lab/runs/<id>/chart-data 结构与空态容错、
8080 不挂新路由。基准指数直接读本地 reference.index_daily（测试环境 DB 可用）；
DB 不可用或表为空时 benchmarks 降级为 None 而非报错。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest


RUN_ID = "20260101T000000000001"


def _make_run(tmp_path: Path, with_files: bool = True) -> Path:
    """构造一个最小 run 目录 + 产物，返回 run_dir。"""
    run_dir = tmp_path / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    out = tmp_path / "out"
    out.mkdir()
    status = {
        "run_id": RUN_ID,
        "mode": "batch",
        "status": "completed",
        "output_dir": str(out),
        "artifacts": {},
        "start": "2024-01-02",
        "end": "2024-02-02",
        "codes": ["000001.SZ", "000002.SZ", "600000.SH"],
        "initial_cash": None,
        "max_positions": None,
        "engine_impl": "vectorized",
    }
    if with_files:
        dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-02-01", "2024-02-02"]
        equity = [100.0, 101.0, 99.0, 102.0, 103.0]
        _write_csv(
            out / "equity_curve.csv",
            ["trade_date", "cash", "market_value", "total_equity"],
            [[d, 0, 0, e] for d, e in zip(dates, equity)],
        )
        _write_csv(
            out / "drawdown_curve.csv",
            ["trade_date", "total_equity", "running_peak", "drawdown", "drawdown_pct"],
            [[d, e, 100.0, e - 100.0, e / 100.0 - 1] for d, e in zip(dates, equity)],
        )
        _write_csv(
            out / "round_trips.csv",
            ["symbol", "entry_date", "exit_date", "holding_days", "net_return", "net_pnl", "exit_reason",
             "gross_pnl", "commission", "stamp_tax", "transfer_fee", "total_cost", "entry_notional"],
            [["000001.SZ", "2024-01-02", "2024-01-04", 5, 0.02, 100, "holding_period",
              105, 3.0, 1.5, 0.5, 5.0, 1000],
             ["000001.SZ", "2024-01-02", "2024-01-04", 3, 0.005, 100, "holding_period",
              103, 2.0, 0.8, 0.2, 3.0, 1000],
             ["000001.SZ", "2024-01-02", "2024-01-04", 7, 0.015, 100, "holding_period",
              102, 1.5, 0.4, 0.1, 2.0, 1000]],
        )
        _write_csv(
            out / "symbol_performance.csv",
            ["symbol", "strategy_total_return"],
            [["000001.SZ", 0.1], ["000002.SZ", -0.2]],
        )
        (out / "strategy_performance.json").write_text(
            json.dumps(
                {
                    "strategy_name": "test_strategy",
                    "strategy_total_return": 0.03,
                    "excess_return_vs_buy_hold": 0.01,
                    "sharpe": 0.5,
                    "max_drawdown": -0.02,
                    "win_rate": 0.6,
                    "date_start": "2024-01-02",
                    "date_end": "2024-02-02",
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "strategy.yaml").write_text(
            "# 策略名称: 测试策略\n# 说明:     测试用一句话描述。\nexperiment:\n  name: t\n",
            encoding="utf-8",
        )
        # 个股产物目录（QRE-GUI-LAB-RESULT-026 个股详情）
        sym_dir = out / "000001.SZ"
        sym_dir.mkdir()
        _write_csv(
            sym_dir / "trades.csv",
            ["symbol", "entry_date", "exit_date", "quantity", "entry_price", "exit_price",
             "gross_pnl", "cost", "net_pnl", "exit_reason"],
            [["000001.SZ", "2024-01-02", "2024-01-04", 100, 10.0, 10.5, 50, 5.5, 44.5, "holding_period"]],
        )
        _write_csv(
            sym_dir / "orders.csv",
            ["symbol", "trade_date", "side", "quantity", "price", "notional", "cost",
             "commission", "stamp_tax", "transfer_fee"],
            [["000001.SZ", "2024-01-02", "buy", 100, 10.0, 1000, 3.0, 3.0, 0, 0],
             ["000001.SZ", "2024-01-04", "sell", 100, 10.5, 1050, 2.5, 2.0, 0.5, 0]],
        )
        _write_csv(
            sym_dir / "equity_curve.csv",
            ["trade_date", "total_equity"],
            [[d, e] for d, e in zip(dates, equity)],
        )
        for name in ("equity_curve.csv", "drawdown_curve.csv", "round_trips.csv",
                     "symbol_performance.csv", "strategy_performance.json"):
            status["artifacts"][name] = str(out / name)
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    return run_dir


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


@pytest.fixture
def lab_client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "quant_research_engine.gui.app.TEMPLATE_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates",
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.app.STATIC_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "static",
    )
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)
    _make_run(tmp_path)

    from quant_research_engine.gui.lab import create_lab_app

    app = create_lab_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_lab_result_page_200(lab_client):
    resp = lab_client.get(f"/lab/runs/{RUN_ID}")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "/static/echarts.min.js" in html
    assert "/static/lab-theme.css" in html
    assert "chart-data" in html
    assert "dataZoom" in html
    assert "回撤" in html and "赚钱效应归因" in html and "treemap" in html
    # QRE-LAB-UI-LANDING：模块顺序 概述→收益曲线→交易磨损→FRM→归因→个股明细入口
    assert 'id="box-fees"' in html and "交易磨损" in html
    assert 'id="big-symbols"' in html and "/symbols" in html
    assert html.index('id="metric-strip"') < html.index('id="box-main"') \
        < html.index('id="box-fees"') < html.index('id="box-risk"') \
        < html.index('id="box-tags"') < html.index('id="big-symbols"')
    # 滑块重算 rAF 节流（性能顺手项）
    assert "requestAnimationFrame" in html
    # treemap 三级显隐（面积分档 labelText）+ tooltip 贡献居前个股（1:1 移植设计稿）
    assert "labelText" in html and "贡献居前" in html
    # QRE-GUI-LAB-RESULT-025：月度热力图与个股 Top10 区块已删除
    assert "chart-monthly" not in html and "chart-symbols" not in html
    assert lab_client.get("/lab/runs/ghost").status_code == 404


def test_lab_chart_data_ok(lab_client):
    resp = lab_client.get(f"/api/lab/runs/{RUN_ID}/chart-data")
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["ok"] is True
    assert d["dates"] == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-02-01", "2024-02-02"]
    assert d["equity"] == [100.0, 101.0, 99.0, 102.0, 103.0]
    # fixture 的 equity_curve.csv 无 cumulative_return 列：不落 cumret 键（旧产物兼容）
    assert "cumret" not in d
    assert len(d["drawdown_pct"]) == 5
    # 指标卡
    m = d["metrics"]
    assert m["total_return"] == 0.03
    assert m["sharpe"] == 0.5
    assert m["max_drawdown"] == -0.02
    assert m["win_rate"] == 0.6
    assert m["annual_return"] is not None
    # 策略简介
    assert d["brief"]["name"] == "test_strategy"
    assert d["brief"]["desc"] == "测试用一句话描述。"
    # 交易买卖点
    assert d["trades"]["sampled"] is False
    assert len(d["trades"]["points"]) == 3
    assert d["trades"]["points"][0]["symbol"] == "000001.SZ"
    # QRE-GUI-LAB-RESULT-025：monthly/symbols 字段已随区块删除一并移除
    assert "monthly" not in d and "symbols" not in d
    # QRE-LAB-UI-LANDING：交易磨损汇总（round_trips 真实费用列聚合）
    fs = d["fees_summary"]
    assert fs is not None
    assert fs["commission"] == 6.5          # 3.0 + 2.0 + 1.5
    assert fs["stamp_tax"] == 2.7           # 1.5 + 0.8 + 0.4
    assert fs["transfer_fee"] == 0.8        # 0.5 + 0.2 + 0.1
    assert fs["total_cost"] == 10.0         # 5 + 3 + 2
    assert fs["gross_pnl"] == 310.0 and fs["net_pnl"] == 300.0
    assert fs["invested"] == 3000.0
    assert fs["trades"] == 3
    assert fs["other_cost"] == round(10.0 - 6.5 - 2.7, 2)
    # 基准：测试环境 DB 可用则 5 指数，不可用则 None + note，两者都合法
    if d["benchmarks"] is not None:
        assert set(d["benchmarks"]) == {"000001.SH", "000300.SH", "000905.SH", "000852.SH", "399006.SZ"}
        for v in d["benchmarks"].values():
            assert len(v["closes"]) == 5
    else:
        assert d["benchmark_note"]


def test_lab_chart_data_404(lab_client):
    assert lab_client.get("/api/lab/runs/ghost/chart-data").status_code == 404


def test_chart_data_cumret_from_cumulative_return(tmp_path, monkeypatch):
    """equity_curve.csv 带 cumulative_return 列（faf9629 起）→ chart_data.cumret 直取列值。

    cumret 为交集口径日收益累乘的小数（与 dates 等长），前端 ×100 转百分比，
    不再用 equity/首日−1 水平值口径（全市场回测会被新股注资扭曲）。
    """
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    run_dir = _make_run(tmp_path)
    out = tmp_path / "out"
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-02-01", "2024-02-02"]
    equity = [100.0, 101.0, 99.0, 102.0, 103.0]
    cumret = [0.0, 0.01, -0.01, 0.02, 0.03]
    _write_csv(
        out / "equity_curve.csv",
        ["trade_date", "cash", "market_value", "total_equity", "daily_return", "cumulative_return"],
        [[d, 0, 0, e, "", c] for d, e, c in zip(dates, equity, cumret)],
    )
    (run_dir / "status.json").write_text(
        json.dumps({
            "run_id": RUN_ID, "output_dir": str(out),
            "artifacts": {"equity_curve.csv": str(out / "equity_curve.csv")},
        }),
        encoding="utf-8",
    )
    from quant_research_engine.gui.lab_result import build_lab_chart_data

    import json as _json
    record = _json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    d = build_lab_chart_data(record)
    assert d["equity"] == equity
    assert d["cumret"] == cumret


# --- QRE-LAB-UI-LANDING：个股明细列表页 ---


def test_lab_symbols_page_200(lab_client):
    resp = lab_client.get(f"/lab/runs/{RUN_ID}/symbols")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "/static/lab-theme.css" in html
    assert 'id="sym-table"' in html and 'id="syms-filter"' in html
    assert "tag-analysis" in html          # 数据源复用归因端点
    assert "赚钱效应分位" in html and "总净盈亏" in html
    assert "Enter" in html                 # 完整代码回车直跳
    assert lab_client.get("/lab/runs/ghost/symbols").status_code == 404


def test_lab_symbol_page_ui_landing(lab_client):
    resp = lab_client.get(f"/lab/runs/{RUN_ID}/symbol/000001.SZ")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "/static/lab-theme.css" in html
    # 模块顺序：概述 → 收益曲线（含区间卡） → 交易磨损 → K线 → 交易明细 → 下单记录
    assert 'id="box-wear"' in html and "交易磨损" in html
    assert 'id="range-strip"' in html and "区间超额" in html
    assert html.index('id="sum-strip"') < html.index('id="chart-equity"') \
        < html.index('id="box-wear"') < html.index('id="chart-kline"') \
        < html.index('id="tbl-trades"') < html.index('id="tbl-orders"')


def test_lab_chart_data_empty_run(monkeypatch, tmp_path):
    """产物全缺时：各字段为 None，端点仍 200（前端显示「暂无数据」）。"""
    monkeypatch.setattr(
        "quant_research_engine.gui.app.TEMPLATE_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates",
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.app.STATIC_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "static",
    )
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)
    _make_run(tmp_path, with_files=False)

    from quant_research_engine.gui.lab import create_lab_app

    app = create_lab_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        assert client.get(f"/lab/runs/{RUN_ID}").status_code == 200
        d = client.get(f"/api/lab/runs/{RUN_ID}/chart-data").get_json()
    assert d["ok"] is True
    assert d["dates"] is None and d["equity"] is None
    assert d["cumret"] is None
    assert d["drawdown_pct"] is None and d["benchmarks"] is None
    assert d["trades"] is None
    assert d["metrics"] is None


def test_trade_points_sampling():
    """round_trips 超 500 笔时按 |net_return| 保留 top 500 并标注 sampled。"""
    from quant_research_engine.gui.lab_result import TRADE_SCATTER_LIMIT, _trade_points

    rows = [["s", "2024-01-02", "2024-01-03", (i % 7) * 0.01 + 0.001, 0, "x"] for i in range(600)]
    csv_path = None
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "round_trips.csv"
        _write_csv(csv_path, ["symbol", "entry_date", "exit_date", "net_return", "net_pnl", "exit_reason"], rows)
        record = {"artifacts": {"round_trips.csv": str(csv_path)}}
        result = _trade_points(record)
    assert result["sampled"] is True
    assert result["total"] == 600
    assert len(result["points"]) == TRADE_SCATTER_LIMIT
    rets = sorted(abs(p["net_return"]) for p in result["points"])
    assert rets[0] >= 0.01  # 保留的是绝对值最大的


def test_admin_console_not_affected():
    """8080 主控制台不挂 lab 专属路由；共享的 /runs/<id> 行为不变。"""
    from quant_research_engine.gui.app import create_app

    rules = {r.rule for r in create_app().url_map.iter_rules()}
    assert "/lab/runs/<run_id>" not in rules
    assert "/api/lab/runs/<run_id>/chart-data" not in rules
    assert "/runs/<run_id>" in rules


# --- 赚钱效应归因（QRE-GUI-LAB-RESULT-024） ---


def test_tag_analysis_endpoint(lab_client):
    """tag-analysis 端点结构：layers A/B/C + notes；DB 可用时有真实标签，不可用时降级 note。"""
    resp = lab_client.get(f"/api/lab/runs/{RUN_ID}/tag-analysis")
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["ok"] is True
    assert set(d["layers"]) == {"A", "B", "C"}
    for layer, items in d["layers"].items():
        assert isinstance(items, list)
        if items:
            t = items[0]
            assert {"tag", "total_pnl", "avg_ret", "trades", "win_rate", "symbols"} <= set(t)
            s = t["symbols"][0]
            assert {"ts_code", "name", "total_pnl", "avg_ret", "trades", "win_rate", "percentile"} <= set(s)
            assert 0 < s["percentile"] <= 1
        else:
            assert d["notes"].get(layer)  # 空层必有说明
    # 本测试 run 只有 000001.SZ 产生交易；DB 可用时 A 层应有其申万 L1（无「申万L1:」前缀）
    if d["layers"]["A"]:
        assert all(not t["tag"].startswith("申万L1:") for t in d["layers"]["A"])
        syms = {s["ts_code"] for t in d["layers"]["A"] for s in t["symbols"]}
        assert syms == {"000001.SZ"}
    assert lab_client.get("/api/lab/runs/ghost/tag-analysis").status_code == 404


def test_tag_analysis_empty_run(monkeypatch, tmp_path):
    """无 round_trips 产物：三层空数组 + 「无交易记录」note，端点仍 200。"""
    monkeypatch.setattr(
        "quant_research_engine.gui.app.TEMPLATE_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates",
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.app.STATIC_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "static",
    )
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)
    _make_run(tmp_path, with_files=False)

    from quant_research_engine.gui.lab import create_lab_app

    app = create_lab_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        d = client.get(f"/api/lab/runs/{RUN_ID}/tag-analysis").get_json()
    assert d["ok"] is True
    assert d["layers"] == {"A": [], "B": [], "C": []}
    assert d["notes"] == {"A": "无交易记录", "B": "无交易记录", "C": "无交易记录"}


def test_tag_aggregate_and_percentile():
    """纯函数：tag 聚合数值 + 分位计算 + A 层全收（去前缀+去重）+ 未标记块 + |pnl| 降序。"""
    from quant_research_engine.gui.lab_result import _aggregate_tag_layers

    stats = {
        # total_pnl / trades / sum_ret / wins
        "S1": {"total_pnl": 300.0, "trades": 2, "sum_ret": 0.06, "wins": 2},
        "S2": {"total_pnl": -100.0, "trades": 1, "sum_ret": -0.02, "wins": 0},
        "S3": {"total_pnl": 100.0, "trades": 1, "sum_ret": 0.01, "wins": 1},
    }
    tag_rows = [
        ("S1", "申万L1:电子", "A"), ("S2", "申万L1:电子", "A"),
        ("S1", "中信L1:电子", "A"),          # QRE-GUI-LAB-RESULT-029：非申万L1前缀 → A 层丢弃
        ("S2", "申万L2:消费电子", "A"),      # QRE-GUI-LAB-RESULT-029：L2 → A 层丢弃
        ("S3", "申万L1:银行", "A"),
        ("S1", "人工智能", "B"), ("S2", "人工智能", "B"),
        ("S1", "动量20日:偏强(5-20%)", "C"),
        ("S9", "无交易股票", "B"),            # 不在 stats 中 → 忽略
    ]
    names = {"S1": "股票一", "S2": "股票二", "S3": "股票三"}
    layers = _aggregate_tag_layers(stats, tag_rows, names)

    # A 层：电子(S1+S2，只计申万L1) 与 银行(S3)，按 |total_pnl| 降序
    assert [t["tag"] for t in layers["A"]] == ["电子", "银行"]
    elec = layers["A"][0]
    assert elec["total_pnl"] == 200.0
    assert elec["trades"] == 3          # 中信L1 / 申万L2 不再计入
    assert elec["win_rate"] == round(2 / 3, 6)
    assert elec["avg_ret"] == round(0.04 / 3, 6)
    # 个股按 total_pnl 降序，分位 = rank/N（N=3）
    assert [s["ts_code"] for s in elec["symbols"]] == ["S1", "S2"]
    s1, s2 = elec["symbols"]
    assert s1["percentile"] == round(1 / 3, 4)   # 全 run 最赚 → 前 33.3%
    assert s2["percentile"] == 1.0               # 最亏 → 前 100%
    assert s1["name"] == "股票一"
    bank = layers["A"][1]
    assert bank["symbols"][0]["percentile"] == round(2 / 3, 4)
    # B 层：人工智能(S1,S2) + 未标记(S3 无 B 层 tag)
    assert [t["tag"] for t in layers["B"]] == ["人工智能", "未标记"]
    assert layers["B"][0]["trades"] == 3
    unmarked_b = layers["B"][1]
    assert [s["ts_code"] for s in unmarked_b["symbols"]] == ["S3"]
    assert unmarked_b["total_pnl"] == 100.0
    # C 层：动量(S1) + 未标记(S2,S3)
    assert [t["tag"] for t in layers["C"]] == ["动量20日:偏强(5-20%)", "未标记"]
    assert layers["C"][1]["trades"] == 2


def test_tag_aggregate_layer_a_industry_fallback():
    """A 层兜底：无申万L1标签的个股（北交所等）按 stock_basic 通用行业入块，
    显示名加 ·通用 后缀；无通用行业的仍归「未标记」（QRE-GUI-CONSOL-045）。"""
    from quant_research_engine.gui.lab_result import _aggregate_tag_layers

    stats = {
        "S1": {"total_pnl": 300.0, "trades": 2, "sum_ret": 0.06, "wins": 2},
        "BJ1": {"total_pnl": 50.0, "trades": 1, "sum_ret": 0.01, "wins": 1},   # 北交所，无申万标签
        "BJ2": {"total_pnl": 20.0, "trades": 1, "sum_ret": 0.02, "wins": 0},   # 北交所，无申万且无通用行业
    }
    tag_rows = [("S1", "申万L1:电子", "A")]
    industries = {"S1": "电子", "BJ1": "半导体"}
    layers = _aggregate_tag_layers(stats, tag_rows, {}, industries=industries)
    tags = [t["tag"] for t in layers["A"]]
    assert "半导体·通用" in tags          # BJ1 兜底入通用行业块
    assert "未标记" in tags               # BJ2 仍归未标记
    fallback = next(t for t in layers["A"] if t["tag"] == "半导体·通用")
    assert fallback["total_pnl"] == 50.0
    assert [s["ts_code"] for s in fallback["symbols"]] == ["BJ1"]
    unmarked = next(t for t in layers["A"] if t["tag"] == "未标记")
    assert [s["ts_code"] for s in unmarked["symbols"]] == ["BJ2"]
    # 不传 industries：BJ1/BJ2 都归未标记（向后兼容旧调用）
    layers2 = _aggregate_tag_layers(stats, tag_rows, {})
    unmarked2 = next(t for t in layers2["A"] if t["tag"] == "未标记")
    assert sorted(s["ts_code"] for s in unmarked2["symbols"]) == ["BJ1", "BJ2"]


def test_tag_aggregate_layer_b_top_n_truncate():
    """B 层 >20 个 tag：只保留前 LAYER_B_TOP_N 个，无合并块（QRE-GUI-LAB-RESULT-028）。"""
    from quant_research_engine.gui.lab_result import LAYER_B_TOP_N, _aggregate_tag_layers

    stats = {"S1": {"total_pnl": 100.0, "trades": 1, "sum_ret": 0.01, "wins": 1}}
    tag_rows = [("S1", f"关键词{i:02d}", "B") for i in range(25)]  # 25 个 B 层 tag
    layers = _aggregate_tag_layers(stats, tag_rows, {})
    b = layers["B"]
    assert len(b) == LAYER_B_TOP_N
    assert all(not t.get("merged_tags") for t in b)
    assert all(t["tag"] not in ("其他", "其余关键词") for t in b)
    # 「未标记」在 B 层不存在（S1 有 B tag）
    assert all(t["tag"] != "未标记" for t in b)


def test_tag_analysis_admin_console_absent():
    """8080 主控制台不挂 tag-analysis 路由。"""
    from quant_research_engine.gui.app import create_app

    rules = {r.rule for r in create_app().url_map.iter_rules()}
    assert "/api/lab/runs/<run_id>/tag-analysis" not in rules


# --- 个股回测详情（QRE-GUI-LAB-RESULT-026） ---


def test_symbol_detail_page_and_endpoint(lab_client):
    resp = lab_client.get(f"/lab/runs/{RUN_ID}/symbol/000001.SZ")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "candlestick" in html and "chart-kline" in html and "个股回测详情" in html
    # RESULT-035：防溢出样式（长文本/宽表格不出框）
    assert "word-break: break-all" in html and "overflow: hidden" in html

    d = lab_client.get(f"/api/lab/runs/{RUN_ID}/symbol/000001.SZ/detail").get_json()
    assert d["ok"] is True
    s = d["summary"]
    assert s["ts_code"] == "000001.SZ"
    assert s["total_pnl"] == 300.0 and s["trades"] == 3 and s["win_rate"] == 1.0
    assert s["percentile"] == 1.0  # 仅一只交易个股
    # 个股产物 trades.csv 优先
    assert d["trades_source"] == "trades_csv"
    assert d["trades"][0]["net_pnl"] == 44.5
    assert len(d["orders"]) == 2
    assert d["orders"][0]["side"] == "buy" and d["orders"][1]["side"] == "sell"
    assert d["equity"]["dates"] == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-02-01", "2024-02-02"]
    assert d["failed_orders"] is None  # 文件不存在 → None 不报错
    # 日 K：测试库有 000001.SZ 2024 年数据则校验结构，无则带 note
    if d["kline"] is not None:
        assert len(d["kline"]["dates"]) == len(d["kline"]["ohlc"]) == len(d["kline"]["vols"])
        assert len(d["kline"]["ohlc"][0]) == 4  # [open, close, low, high]
    else:
        assert d["kline_note"]


def test_symbol_detail_404(lab_client):
    assert lab_client.get(f"/api/lab/runs/{RUN_ID}/symbol/000002.SZ/detail").status_code == 404  # 无交易
    assert lab_client.get("/api/lab/runs/ghost/symbol/000001.SZ/detail").status_code == 404
    assert lab_client.get("/lab/runs/ghost/symbol/000001.SZ").status_code == 404


def test_symbol_detail_fallback_round_trips(monkeypatch, tmp_path):
    """无个股产物目录：trades 退到 round_trips 过滤，orders/equity 为 None。"""
    import shutil

    monkeypatch.setattr(
        "quant_research_engine.gui.app.TEMPLATE_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates",
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.app.STATIC_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "static",
    )
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)
    _make_run(tmp_path)
    shutil.rmtree(tmp_path / "out" / "000001.SZ")

    from quant_research_engine.gui.lab import create_lab_app

    app = create_lab_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get(f"/api/lab/runs/{RUN_ID}/symbol/000001.SZ/detail")
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["trades_source"] == "round_trips"
    assert len(d["trades"]) == 3
    assert d["orders"] is None and d["equity"] is None and d["failed_orders"] is None


def test_symbol_detail_admin_console_absent():
    """8080 主控制台不挂个股详情路由。"""
    from quant_research_engine.gui.app import create_app

    rules = {r.rule for r in create_app().url_map.iter_rules()}
    assert "/lab/runs/<run_id>/symbol/<ts_code>" not in rules
    assert "/api/lab/runs/<run_id>/symbol/<ts_code>/detail" not in rules


# --- 板块下钻增强 + B 层关键词净化（QRE-GUI-LAB-RESULT-027） ---


def test_is_noise_keyword():
    """停用词/单字/超长/纯数字/短英文丢弃；真概念词放行。"""
    from quant_research_engine.gui.lab_result import is_noise_keyword

    for bad in ("国际", "有关", "其他", "相关", "公司", "集团", "股份", "科技",
                "发展", "投资", "控股", "中国", "企业", "业务", "产品", "项目",
                "服务", "技术", "产业", "行业", "市场", "系统", "设备", "材料",
                "电",                # 单字
                "专注于提供一体化解决方案的公司",  # 句子型 >12 字
                "12345",             # 纯数字
                "abc", "xy",         # 无意义短英文
                "", "   "):
        assert is_noise_keyword(bad), bad
    for good in ("固态电池", "氧化铬", "人形机器人", "人工智能", "低空经济",
                 "AI", "5G", "CPO", "HBM"):  # 真概念词 / 白名单缩写
        assert not is_noise_keyword(good), good


def test_tag_aggregate_b_layer_noise_filtered():
    """B 层噪声 tag 被过滤（原生「其他」也不留），A/C 层同名 tag 不过滤。"""
    from quant_research_engine.gui.lab_result import _aggregate_tag_layers

    stats = {
        "S1": {"total_pnl": 100.0, "trades": 1, "sum_ret": 0.01, "wins": 1,
               "best_ret": 0.01, "worst_ret": 0.01, "sum_hold": 5.0, "hold_n": 1},
    }
    tag_rows = [
        ("S1", "申万L1:国际", "A"),      # A 层不过滤（去前缀后显示「国际」）
        ("S1", "固态电池", "B"),
        ("S1", "国际", "B"),            # 噪声 → 滤
        ("S1", "其他", "B"),            # 原生「其他」必须滤掉，避免与合并块歧义
        ("S1", "12345", "B"),           # 纯数字 → 滤
        ("S1", "国际", "C"),            # C 层不过滤
    ]
    layers = _aggregate_tag_layers(stats, tag_rows, {})
    assert [t["tag"] for t in layers["A"]] == ["国际"]
    assert [t["tag"] for t in layers["B"]] == ["固态电池"]
    assert [t["tag"] for t in layers["C"]] == ["国际"]


def test_tag_analysis_filtered_count(lab_client, monkeypatch):
    """tag-analysis JSON 带 filtered_count（B 层去重后无效关键词个数）。"""
    from quant_research_engine.gui import lab_result

    monkeypatch.setattr(
        lab_result, "_fetch_company_tags",
        lambda syms: ([("000001.SZ", "固态电池", "B"),
                       ("000001.SZ", "国际", "B"),
                       ("000001.SZ", "国际", "B"),   # 重复只计一次
                       ("000001.SZ", "其他", "B"),
                       ("000001.SZ", "申万L1:国际", "A")],  # A 层不计入 filtered_count
                      {"000001.SZ": "测试股"}, None),
    )
    d = lab_client.get(f"/api/lab/runs/{RUN_ID}/tag-analysis").get_json()
    assert d["ok"] is True
    assert d["filtered_count"] == 2  # 国际 + 其他
    assert [t["tag"] for t in d["layers"]["B"]] == ["固态电池"]
    assert [t["tag"] for t in d["layers"]["A"]] == ["国际"]


def test_drilldown_symbol_extra_fields(lab_client, monkeypatch):
    """下钻个股新字段数值核对：best/worst/avg_hold_days（_make_run 的 3 笔 round_trips）。"""
    from quant_research_engine.gui import lab_result

    monkeypatch.setattr(
        lab_result, "_fetch_company_tags",
        lambda syms: ([("000001.SZ", "固态电池", "B")], {"000001.SZ": "测试股"}, None),
    )
    d = lab_client.get(f"/api/lab/runs/{RUN_ID}/tag-analysis").get_json()
    s = d["layers"]["B"][0]["symbols"][0]
    assert s["ts_code"] == "000001.SZ" and s["name"] == "测试股"
    assert s["trades"] == 3 and s["total_pnl"] == 300.0
    assert s["best_ret"] == 0.02 and s["worst_ret"] == 0.005
    assert s["avg_hold_days"] == 5.0  # (5+3+7)/3


def test_symbol_stats_extra_fields_pure(tmp_path):
    """纯函数层：holding_days 列缺失时新字段为 None，不报错。"""
    from quant_research_engine.gui.lab_result import _aggregate_tag_layers, _symbol_trade_stats

    csv_path = tmp_path / "round_trips.csv"
    _write_csv(csv_path, ["symbol", "entry_date", "exit_date", "net_return", "net_pnl"],
               [["AAA", "2024-01-02", "2024-01-04", 0.03, 50],
                ["AAA", "2024-01-05", "2024-01-08", -0.01, -20]])
    stats = _symbol_trade_stats({"artifacts": {"round_trips.csv": str(csv_path)}})
    layers = _aggregate_tag_layers(stats, [("AAA", "固态电池", "B")], {})
    s = layers["B"][0]["symbols"][0]
    assert s["best_ret"] == 0.03 and s["worst_ret"] == -0.01
    assert s["avg_hold_days"] is None


# --- K 线买卖信号修复 + A 层只留申万 L1 + 板块自然涨幅基准（QRE-GUI-LAB-RESULT-029） ---


def test_scatter_marker_uses_value_not_coord():
    """K 线页买卖散点必须用 value（scatter series data 不认 coord，
    coord 是 markPoint 的属性 —— RESULT-029 K 线信号缺失的根因）。
    RESULT-034 起主结果页不再显示买卖点散点，仅 K 线页保留。"""
    tpl_dir = Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates"
    text = (tpl_dir / "lab_symbol.html").read_text(encoding="utf-8")
    assert "coord: [" not in text, "lab_symbol.html 买卖散点仍在用 coord（不会被渲染）"
    assert "value: [" in text
    main = (tpl_dir / "lab_result.html").read_text(encoding="utf-8")
    assert "coord: [" not in main


def test_kline_factor_grids_scale_with_factor_count():
    """多因子策略（如 MACD 双因子）个股 K 线页：grid 必须按面板数动态生成，
    否则 gridIndex 2+i 越界、ECharts setOption 抛 coordinateSystem undefined，
    被 catch 后整页（K线/买卖点/下单表/交易明细）全部空白 —— CONSOL-041 根因。
    CR-2026-10-20 起面板数来自 QREFactorLayout 分组（overlay/MACD 合并不占面板）。"""
    tpl_dir = Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates"
    text = (tpl_dir / "lab_symbol.html").read_text(encoding="utf-8")
    assert "grids.push" in text, "lab_symbol.html 因子 grid 不是动态生成的"
    assert "panes.length * 160" in text, "K 线图高度未随面板个数扩展"
    assert "factor-layout.js" in text and "QREFactorLayout.plan" in text


def test_main_chart_series_have_stable_ids():
    """主结果页净值图系列必须带稳定 id（strategy/dd/bench）——否则 applyBench 的
    setOption 按索引合并会把「策略」系列冲掉，基准与策略无法同图重叠（CONSOL-042）。"""
    tpl_dir = Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates"
    text = (tpl_dir / "lab_result.html").read_text(encoding="utf-8")
    assert "id: 'strategy'" in text
    assert "id: 'dd'" in text
    assert "id: 'bench'" in text


def test_tag_aggregate_layer_a_only_sw_l1():
    """A 层只保留 `申万L1:` 前缀；只有 L2/L3/中信等标签的个股归入「未标记」。"""
    from quant_research_engine.gui.lab_result import _aggregate_tag_layers

    stats = {
        "S1": {"total_pnl": 100.0, "trades": 1, "sum_ret": 0.01, "wins": 1},
        "S2": {"total_pnl": 50.0, "trades": 1, "sum_ret": 0.02, "wins": 1},
    }
    tag_rows = [
        ("S1", "申万L1:电子", "A"),
        ("S1", "申万L2:消费电子", "A"),   # L2 丢
        ("S1", "申万L3:品牌消费电子", "A"),  # L3 丢
        ("S2", "中信L1:电子", "A"),       # 中信丢
        ("S2", "申万L2:其他电子", "A"),   # L2 丢
    ]
    layers = _aggregate_tag_layers(stats, tag_rows, {})
    tags = [t["tag"] for t in layers["A"]]
    assert "电子" in tags and "未标记" in tags
    assert len(tags) == 2  # 消费电子/品牌消费电子/其他电子均不出现
    unmarked = next(t for t in layers["A"] if t["tag"] == "未标记")
    assert [s["ts_code"] for s in unmarked["symbols"]] == ["S2"]


def test_tag_analysis_bench_ret(lab_client, monkeypatch):
    """tag-analysis 每个 tag 带 bench_ret：板块内个股区间收益的等权平均（人造样本核对数值）。"""
    from quant_research_engine.gui import lab_result

    monkeypatch.setattr(
        lab_result, "_fetch_company_tags",
        lambda syms: ([("000001.SZ", "申万L1:银行", "A")], {"000001.SZ": "测试股"}, None),
    )
    # 该 run 只有 000001.SZ 产生交易：bench_ret = 该股区间收益
    monkeypatch.setattr(
        lab_result, "_fetch_symbol_range_returns",
        lambda syms, d0, d1: {"000001.SZ": 0.25},
    )
    d = lab_client.get(f"/api/lab/runs/{RUN_ID}/tag-analysis").get_json()
    assert d["ok"] is True
    a0 = d["layers"]["A"][0]
    assert a0["tag"] == "银行" and a0["bench_ret"] == 0.25
    # QRE-GUI-LAB-RESULT-032：bench_ret 下沉到个股级
    assert a0["symbols"][0]["bench_ret"] == 0.25
    # 无行情的 tag → None 不报错
    monkeypatch.setattr(lab_result, "_fetch_symbol_range_returns", lambda syms, d0, d1: None)
    d2 = lab_client.get(f"/api/lab/runs/{RUN_ID}/tag-analysis").get_json()
    assert d2["layers"]["A"][0]["bench_ret"] is None
    assert d2["layers"]["A"][0]["symbols"][0]["bench_ret"] is None


def test_symbol_detail_benchmarks(lab_client, monkeypatch):
    """个股详情带 benchmarks（按净值交易日对齐）+ 无净值时降级 None（QRE-GUI-LAB-RESULT-033）。"""
    from quant_research_engine.gui import lab_result

    fake = {"000001.SH": {"name": "上证指数", "closes": [1.0, 2.0]}}
    monkeypatch.setattr(lab_result, "_benchmark_series", lambda dates: (fake, None))
    d = lab_client.get(f"/api/lab/runs/{RUN_ID}/symbol/000001.SZ/detail").get_json()
    if d["equity"]:
        assert d["benchmarks"] == fake
    else:  # 无净值曲线 → benchmarks None 不报错
        assert d["benchmarks"] is None


def test_factor_thresholds_pure():
    """出入场表达式阈值提取（QRE-GUI-LAB-RESULT-036）。"""
    from quant_research_engine.gui.lab_result import _factor_thresholds

    assert _factor_thresholds("rsi_14", "rsi_14 > 30", "rsi_14 > 60") == [30.0, 60.0]
    assert _factor_thresholds("rsi_14", "30 < rsi_14", "") == [30.0]
    assert _factor_thresholds("rsi_14", "close > ema_20", "ema_20 < close") == []


# --- 因子面板 col 元数据 + MACD 柱自动补全（CR-2026-10-20 因子图表 TV 布局） ---


def test_macd_hist_candidates_pure():
    """同表 macd_<P>+macds_<P> 成对且 macdh_<P> 未引用 → 候选；单线/已引用/跨表不成对。"""
    from quant_research_engine.gui.lab_result import _macd_hist_candidates

    specs = {"macd": ("factors.t", "macd_12_26_9"), "macd_sig": ("factors.t", "macds_12_26_9")}
    assert _macd_hist_candidates(specs) == [("factors.t", "macdh_12_26_9")]
    # 已引用 hist → 不补
    specs2 = dict(specs, hist=("factors.t", "macdh_12_26_9"))
    assert _macd_hist_candidates(specs2) == []
    # 只有 macd 单线 → 不补
    assert _macd_hist_candidates({"macd": ("factors.t", "macd_12_26_9")}) == []
    # 跨表不算同参数对
    cross = {"a": ("factors.t1", "macd_12_26_9"), "b": ("factors.t2", "macds_12_26_9")}
    assert _macd_hist_candidates(cross) == []
    # 不同后缀各自独立
    multi = {
        "m1": ("factors.t", "macd_12_26_9"), "s1": ("factors.t", "macds_12_26_9"),
        "m2": ("factors.t", "macd_8_21_5"), "s2": ("factors.t", "macds_8_21_5"),
    }
    assert sorted(_macd_hist_candidates(multi)) == [
        ("factors.t", "macdh_12_26_9"), ("factors.t", "macdh_8_21_5")]


class _FakeRes:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


def _fake_factor_store(monkeypatch, values, existing_cols):
    """构造假 store：information_schema 按 existing_cols 应答，因子查询按 values 应答。"""
    import re as _re

    class _Conn:
        def execute(self, stmt, params=None):
            sql = str(stmt)
            if "information_schema.columns" in sql:
                return _FakeRes([(1,)] if params.get("c") in existing_cols else [])
            col = _re.search(r'"(\w+)" FROM', sql).group(1)
            return _FakeRes([(d, values[col]) for d in ("2024-01-02", "2024-01-03") if col in values])

    class _Begin:
        def __enter__(self):
            return _Conn()

        def __exit__(self, *a):
            return False

    class _Engine:
        def begin(self):
            return _Begin()

    class _Store:
        market_engine = _Engine()

    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda *a, **k: _Store())


def test_fetch_factor_panels_col_and_macdh_backfill(monkeypatch, tmp_path):
    """panel 带真实列名 col；macd/macds 同后缀成对且 macdh 存在时自动补 MACD柱 panel。"""
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "strategy.yaml").write_text(
        "data:\n  factor_fields:\n"
        "    macd: factors.stock_daily_tech.macd_12_26_9\n"
        "    macd_signal: factors.stock_daily_tech.macds_12_26_9\n"
        "signal:\n  entry: macd > 0\n  exit: macd < 0\n",
        encoding="utf-8",
    )
    values = {"macd_12_26_9": 1.0, "macds_12_26_9": 0.5, "macdh_12_26_9": 0.5}
    _fake_factor_store(monkeypatch, values, existing_cols={"macdh_12_26_9"})

    from quant_research_engine.gui.lab_result import _fetch_factor_panels

    panels, note = _fetch_factor_panels({"run_id": "r1"}, "000001.SZ", ["2024-01-02", "2024-01-03"])
    assert note is None
    assert [p["name"] for p in panels] == ["macd", "macd_signal", "MACD柱"]
    assert panels[0]["col"] == "macd_12_26_9" and panels[1]["col"] == "macds_12_26_9"
    assert panels[2]["col"] == "macdh_12_26_9" and panels[2]["thresholds"] == []
    assert panels[0]["values"] == [1.0, 1.0] and panels[0]["thresholds"] == [0.0, 0.0]


def test_fetch_factor_panels_macdh_missing_column(monkeypatch, tmp_path):
    """macdh 列不存在 / 只引用 macd 单线：不补 panel，原功能不受影响。"""
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "strategy.yaml").write_text(
        "data:\n  factor_fields:\n"
        "    macd: factors.stock_daily_tech.macd_12_26_9\n"
        "    macd_signal: factors.stock_daily_tech.macds_12_26_9\n",
        encoding="utf-8",
    )
    values = {"macd_12_26_9": 1.0, "macds_12_26_9": 0.5}
    _fake_factor_store(monkeypatch, values, existing_cols=set())  # macdh 不存在

    from quant_research_engine.gui.lab_result import _fetch_factor_panels

    panels, note = _fetch_factor_panels({"run_id": "r1"}, "000001.SZ", ["2024-01-02", "2024-01-03"])
    assert note is None
    assert [p["name"] for p in panels] == ["macd", "macd_signal"]
    assert all("col" in p for p in panels)


def test_symbol_detail_total_ret_pct(lab_client):
    """个股详情 summary 带 total_ret_pct（净值末/初-1），与自然涨幅同口径（QRE-GUI-LAB-RESULT-034）。"""
    d = lab_client.get(f"/api/lab/runs/{RUN_ID}/symbol/000001.SZ/detail").get_json()
    assert "total_ret_pct" in d["summary"]
    eq = d.get("equity")
    if eq and len(eq["values"]) >= 2 and eq["values"][0]:
        assert d["summary"]["total_ret_pct"] == round(eq["values"][-1] / eq["values"][0] - 1, 6)
    else:
        assert d["summary"]["total_ret_pct"] is None


def test_symbol_detail_bench_ret(lab_client, monkeypatch):
    """个股详情 summary 带 bench_ret（区间买入持有自然收益）；缺数据降级 None。"""
    from quant_research_engine.gui import lab_result

    monkeypatch.setattr(
        lab_result, "_fetch_symbol_range_returns",
        lambda syms, d0, d1: {syms[0]: 0.42},
    )
    d = lab_client.get(f"/api/lab/runs/{RUN_ID}/symbol/000001.SZ/detail").get_json()
    assert d["summary"]["bench_ret"] == 0.42
    monkeypatch.setattr(lab_result, "_fetch_symbol_range_returns", lambda syms, d0, d1: None)
    d2 = lab_client.get(f"/api/lab/runs/{RUN_ID}/symbol/000001.SZ/detail").get_json()
    assert d2["summary"]["bench_ret"] is None


def test_tag_bench_ret_pure():
    """纯函数：等权平均只算有数据的个股；全缺 / rets None → None。"""
    from quant_research_engine.gui.lab_result import _tag_bench_ret

    assert _tag_bench_ret(["A", "B", "C"], {"A": 0.1, "B": -0.2}) == round((0.1 - 0.2) / 2, 6)
    assert _tag_bench_ret(["A"], {"X": 0.5}) is None
    assert _tag_bench_ret(["A"], None) is None


# --- 回测参数信息条 + FRM 风险区块（QRE-GUI-LAB-RESULT-031） ---


def test_chart_data_meta_block(lab_client):
    """chart-data 带 meta 块：区间/标的/默认资金持仓/引擎/默认费率。"""
    d = lab_client.get(f"/api/lab/runs/{RUN_ID}/chart-data").get_json()
    meta = d["meta"]
    assert meta["strategy_name"] == "test_strategy"
    assert meta["date_start"] == "2024-01-02" and meta["date_end"] == "2024-02-02"
    assert meta["mode"] == "batch" and meta["whole_market"] is False
    assert meta["n_codes"] == 3 and meta["codes_sample"] == ["000001.SZ", "000002.SZ", "600000.SH"]
    assert meta["initial_cash"] == 100_000.0 and meta["max_positions"] == 10  # 缺省默认
    assert meta["engine_impl"] == "vectorized"
    fees = meta["fees"]
    assert fees["commission_rate"] == 0.0003 and fees["stamp_tax_sell"] == 0.0005
    assert fees["min_commission"] == 5.0 and fees["overridden"] is False


def test_run_meta_pure():
    """纯函数：profile_overrides 覆盖费率；空 codes → 全 A 股；字符串 codes 兼容。"""
    from quant_research_engine.gui.lab_result import _run_meta

    meta = _run_meta(
        {"mode": "batch", "start": "2025-01-01", "end": "2025-06-30",
         "codes": "600519.SH 000001.SZ", "initial_cash": "500000",
         "max_positions": "20", "engine_impl": "simulator",
         "profile_overrides": {"commission_rate": 0.0001}},
        {"name": "x"},
    )
    assert meta["n_codes"] == 2 and meta["codes_sample"] == ["600519.SH", "000001.SZ"]
    assert meta["initial_cash"] == 500_000.0 and meta["max_positions"] == 20
    assert meta["fees"]["commission_rate"] == 0.0001 and meta["fees"]["overridden"] is True
    assert meta["fees"]["stamp_tax_sell"] == 0.0005  # 未覆盖的仍为默认
    full = _run_meta({"mode": "batch", "codes": []}, {})
    assert full["whole_market"] is True and full["n_codes"] == 0


def test_histogram_normal_data_pure():
    """纯函数：分箱数/计数守恒/正态曲线形状；退化输入返回 None。"""
    from quant_research_engine.gui.lab_result import histogram_normal_data

    rets = [(-0.02 + 0.001 * i) for i in range(41)]  # 41 个均匀样本
    h = histogram_normal_data(rets, 0.0, 0.01, n_bins=10)
    assert h is not None
    assert len(h["edges"]) == 11 and len(h["counts"]) == 10 and len(h["normal"]) == 10
    assert sum(h["counts"]) == 41
    assert h["edges"][0] == pytest.approx(-0.02) and h["edges"][-1] == pytest.approx(0.02)
    # 正态拟合峰值在均值 0 附近
    peak_x = max(h["normal"], key=lambda p: p[1])[0]
    assert abs(peak_x) < 0.005
    assert histogram_normal_data([0.01], 0.0, 0.01) is None      # 样本不足
    assert histogram_normal_data(rets, 0.0, 0.0) is None         # std=0
    assert histogram_normal_data([0.01, 0.01, 0.01], 0.01, 0.001) is None  # 无离散度


def _write_risk_report(tmp_path: Path) -> None:
    """最小 risk_report.json：覆盖五个图表节的典型结构。"""
    report = {
        "meta": {"n_obs": 100, "annualization_factor": 252},
        "distribution": {"mean": 0.001, "std": 0.01, "min": -0.03, "max": 0.03,
                         "skew_sample": 0.5, "excess_kurtosis_sample": 2.0,
                         "reject_normal_5pct": True},
        "tail": {"95pct": {"historical_simulation": {"var": 0.02, "es": 0.025}},
                 "99pct": {"historical_simulation": {"var": 0.03, "es": 0.04}}},
        "volatility": {"ewma_latest": {"volatility_forecast": 0.01},
                       "garch11": {"latest_conditional_volatility": 0.011},
                       "regime": {"counts": {"low": 40, "mid": 35, "high": 25}, "latest": "low"}},
        "var_backtest": {"enabled": True, "levels": {
            "95pct": {"reject_5pct": False, "conclusion": "不拒绝",
                      "coverage": {"violation_rate": 0.04, "expected_violation_rate": 0.05,
                                   "violations": 4, "n_obs": 100}}}},
        "stress": {"scenarios": {
            "covid_2020": {"description": "2020 疫情跳空", "error": "no observations"},
            "microcap_2024": {"description": "微盘股流动性", "window": {"start": "2024-01-01"},
                              "strategy_cumulative_loss": -0.05,
                              "strategy_peak_trough_drawdown": 0.08}}},
    }
    (tmp_path / "runs" / RUN_ID / "risk_report.json").write_text(
        json.dumps(report), encoding="utf-8")


def test_risk_analysis_endpoint(lab_client, monkeypatch, tmp_path):
    """有报告：has_report + 五节结构 + 直方图（equity_curve 提取日收益）；数值核对。"""
    from quant_research_engine.gui import risk_report as rr

    monkeypatch.setattr(rr, "RUNS_DIR", tmp_path / "runs")
    _write_risk_report(tmp_path)
    d = lab_client.get(f"/api/lab/runs/{RUN_ID}/risk-analysis").get_json()
    assert d["ok"] is True and d["has_report"] is True and d["n_obs"] == 100
    assert d["var_es"]["95pct"] == {"var": 0.02, "es": 0.025}
    assert d["var_es"]["99pct"]["var"] == 0.03
    assert d["volatility"]["ewma_annual"] == pytest.approx(0.01 * 252 ** 0.5)
    assert d["volatility"]["regime_counts"] == {"low": 40, "mid": 35, "high": 25}
    assert d["volatility"]["latest_regime"] == "low"
    st = d["stress"]
    assert len(st["scenarios"]) == 1 and st["scenarios"][0]["max_dd"] == 0.08
    assert st["skipped"] == ["2020 疫情跳空"]
    bt = d["var_backtest"]["95pct"]
    assert bt["reject"] is False and bt["violation_rate"] == 0.04 and bt["expected_rate"] == 0.05
    # 直方图来自 equity_curve.csv 日收益（4 个收益点），分箱计数守恒
    assert d["histogram"] is not None
    assert sum(d["histogram"]["counts"]) == 4
    assert lab_client.get("/api/lab/runs/ghost/risk-analysis").status_code == 404


def test_risk_analysis_no_report(lab_client, monkeypatch, tmp_path):
    """无报告 / 报告损坏：has_report False，端点仍 200（前端显示生成按钮）。"""
    from quant_research_engine.gui import risk_report as rr

    monkeypatch.setattr(rr, "RUNS_DIR", tmp_path / "runs")
    d = lab_client.get(f"/api/lab/runs/{RUN_ID}/risk-analysis").get_json()
    assert d["ok"] is True and d["has_report"] is False
    (tmp_path / "runs" / RUN_ID / "risk_report.json").write_text("{broken", encoding="utf-8")
    d2 = lab_client.get(f"/api/lab/runs/{RUN_ID}/risk-analysis").get_json()
    assert d2["ok"] is True and d2["has_report"] is False


def test_risk_view_partial_report():
    """纯函数容错：缺节的 report → 对应键 None，不抛错。"""
    from quant_research_engine.gui.lab_result import build_lab_risk_view

    v = build_lab_risk_view({})
    assert v["dist"] is None and v["var_es"] is None and v["volatility"] is None
    assert v["stress"] is None and v["var_backtest"] is None
    v2 = build_lab_risk_view({"tail": {"95pct": {"historical_simulation": {"var": 0.01, "es": 0.02}}},
                              "var_backtest": {"enabled": False}})
    assert v2["var_es"]["95pct"]["var"] == 0.01
    assert v2["var_es"].get("99pct") is None
    assert v2["var_backtest"] is None


def test_risk_analysis_admin_console_absent():
    """8080 主控制台不挂 risk-analysis 路由（共享的 POST risk-report 保持不变）。"""
    from quant_research_engine.gui.app import create_app

    rules = {r.rule for r in create_app().url_map.iter_rules()}
    assert "/api/lab/runs/<run_id>/risk-analysis" not in rules
    assert "/api/runs/<run_id>/risk-report" in rules  # 共享路由不变


# --- 回测记录列表 + 删除（QRE-GUI-CONSOL-040，8081 独占） ---


def _make_bare_run(runs_dir: Path, run_id: str, *, codes=None, created_at="2026-01-01T00:00:00",
                   strategy_yaml: str | None = None) -> Path:
    """造一个最小 run（status.json + 可选 strategy.yaml），无产物。"""
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    status = {
        "run_id": run_id,
        "mode": "batch",
        "status": "completed",
        "output_dir": str(runs_dir.parent / "out" / run_id),
        "start": "2025-01-01",
        "end": "2025-12-31",
        "created_at": created_at,
    }
    if codes is not None:
        status["codes"] = codes
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    if strategy_yaml is not None:
        (run_dir / "strategy.yaml").write_text(strategy_yaml, encoding="utf-8")
    return run_dir


def _make_running_run(runs_dir: Path, run_id: str, *, gui_pid=None) -> Path:
    """造一个 status=running 的 run（用于僵尸自愈测试）。"""
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    status = {
        "run_id": run_id, "mode": "batch", "status": "running",
        "output_dir": str(runs_dir.parent / "out" / run_id),
        "start": "2025-01-01", "end": "2025-12-31",
        "created_at": "2026-01-04T00:00:00", "executor": "module",
    }
    if gui_pid is not None:
        status["gui_pid"] = gui_pid
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    return run_dir


def test_random_universe_sample(monkeypatch):
    """QRE-LAB-RANDOM-UNIVERSE：抽样数量正确、同种子可复现、不越界。"""
    import pandas as pd
    import quant_research_engine.gui.engine as engine

    class _FakeStore:
        def __init__(self, settings):
            pass

        def load_security_metadata(self, ts_codes=None):
            return pd.DataFrame({"ts_code": [f"{i:06d}.SZ" for i in range(100)]})

    monkeypatch.setattr(
        "quant_research_engine.data.postgres.PostgresDataStore", _FakeStore
    )
    from quant_research_engine.gui.engine import _sample_random_universe

    a = _sample_random_universe(10, "rid1", db_url="postgresql+psycopg:///dummy")
    b = _sample_random_universe(10, "rid1", db_url="postgresql+psycopg:///dummy")
    c = _sample_random_universe(10, "rid2", db_url="postgresql+psycopg:///dummy")
    assert len(a) == 10 and len(set(a)) == 10          # 数量正确且不重复
    assert a == b                                       # 同 run_id 可复现
    assert a != c or len(set(a) & set(c)) < 10          # 不同种子不同抽样（极大概率）
    assert len(_sample_random_universe(5000, "rid1", db_url="postgresql+psycopg:///dummy")) == 100  # 超池子截断不越界


def test_api_run_random_n_validation(lab_client):
    """random_n 非法值 400；合法值放行到执行层（本用例只到校验/提交失败边界）。"""
    base = {"yaml": "experiment:\n  name: t\nsignal:\n  entry: close > 0\n",
            "mode": "batch", "start": "2025-01-01", "end": "2025-02-01"}
    for bad in (0, -1, 2001, "abc"):
        resp = lab_client.post("/api/run", json={**base, "random_n": bad})
        assert resp.status_code == 400, bad
        assert "random_n" in resp.get_json()["error"]


def test_api_run_max_positions_validation(lab_client):
    """max_positions 非法值 400（负数/0/非整数）；合法值放行到执行层。"""
    base = {"yaml": "experiment:\n  name: t\nsignal:\n  entry: close > 0\n",
            "mode": "batch", "start": "2025-01-01", "end": "2025-02-01",
            "codes": "000001.SZ"}
    for bad in (-3, "abc", 2.5):
        resp = lab_client.post("/api/run", json={**base, "max_positions": bad})
        assert resp.status_code == 400, bad
        assert "max_positions" in resp.get_json()["error"]
    # 0 = 不限制（QRE-MAXPOS-UNLIMITED）与正整数放行（后续执行层错误可接受，只断 400 边界）
    for ok_val in (0, 20):
        resp = lab_client.post("/api/run", json={**base, "max_positions": ok_val})
        assert resp.status_code != 400, ok_val


def test_lab_runs_zombie_reap(lab_client, tmp_path):
    """QRE-LAB-UI-LANDING-R6：running 但执行器已死的 run 自动标 failed；活 run 不动。"""
    import os
    runs_dir = tmp_path / "runs"
    # 无 gui_pid 的旧 running run → 僵尸
    _make_running_run(runs_dir, "20260104T000000000004")
    # gui_pid 指向不存在的 PID（旧 GUI 进程已死）→ 僵尸
    _make_running_run(runs_dir, "20260104T000000000005", gui_pid=2_000_000_000)
    # gui_pid = 当前进程且探活通过 → 保持 running
    _make_running_run(runs_dir, "20260104T000000000006", gui_pid=os.getpid())

    resp = lab_client.get("/api/lab/runs")
    assert resp.status_code == 200
    by_id = {r["run_id"]: r for r in resp.get_json()["runs"]}
    assert by_id["20260104T000000000004"]["status"] == "failed"
    assert by_id["20260104T000000000005"]["status"] == "failed"
    assert by_id["20260104T000000000006"]["status"] == "running"
    # status.json 已写回，error 注明检测原因与时间
    for rid in ("20260104T000000000004", "20260104T000000000005"):
        st = json.loads((runs_dir / rid / "status.json").read_text(encoding="utf-8"))
        assert st["status"] == "failed"
        assert "僵尸 run 自动标记" in st["error"] and "检测时间" in st["error"]


def test_lab_runs_list_enriched(lab_client, tmp_path):
    """/api/lab/runs：增强字段 + 策略名三级 fallback + 创建时间倒序。"""
    runs_dir = tmp_path / "runs"
    # 1) 头部注释名（fixture 自带 RUN_ID 即此型：strategy.yaml 注释「测试策略」）
    # 2) 无注释 → fallback experiment.name
    _make_bare_run(runs_dir, "20260102T000000000002", codes=[], created_at="2026-01-02T00:00:00",
                   strategy_yaml="experiment:\n  name: yaml_fallback_strategy\n")
    # 3) 无 strategy.yaml → fallback run_id；codes 缺省 → symbol_count None
    _make_bare_run(runs_dir, "20260103T000000000003", created_at="2026-01-03T00:00:00")

    resp = lab_client.get("/api/lab/runs")
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["ok"] is True
    by_id = {r["run_id"]: r for r in d["runs"]}
    assert set(by_id) == {RUN_ID, "20260102T000000000002", "20260103T000000000003"}
    # 三级 fallback
    assert by_id[RUN_ID]["strategy_name"] == "测试策略"                    # 头部注释
    assert by_id["20260102T000000000002"]["strategy_name"] == "yaml_fallback_strategy"  # experiment.name
    assert by_id["20260103T000000000003"]["strategy_name"] == "20260103T000000000003"   # run_id
    # symbol_count：codes 空/缺省 → None（前端显示「全 A 股」）
    assert by_id[RUN_ID]["symbol_count"] == 3
    assert by_id["20260102T000000000002"]["symbol_count"] is None
    assert by_id["20260103T000000000003"]["symbol_count"] is None
    # 创建时间倒序（fixture 的 RUN_ID 无 created_at，视为最早）
    order = [r["run_id"] for r in d["runs"]]
    assert order.index("20260103T000000000003") < order.index("20260102T000000000002")


def test_lab_runs_delete_ok(lab_client, tmp_path):
    """删除存在的 run：目录被删，返回 ok；output_dir 产物目录不动。"""
    runs_dir = tmp_path / "runs"
    run_dir = _make_bare_run(runs_dir, "20260104T000000000004")
    out_dir = runs_dir.parent / "out" / "20260104T000000000004"
    out_dir.mkdir(parents=True)
    (out_dir / "equity_curve.csv").write_text("x", encoding="utf-8")

    resp = lab_client.post("/api/lab/runs/20260104T000000000004/delete")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    assert not run_dir.exists()
    assert (out_dir / "equity_curve.csv").exists()  # 产物目录不受影响
    # 再删一次 → 404
    assert lab_client.post("/api/lab/runs/20260104T000000000004/delete").status_code == 404


def test_lab_runs_delete_invalid_id(lab_client, tmp_path):
    """非法字符 / 路径穿越 → 400，且不删 RUNS_DIR 之外的东西。"""
    runs_dir = tmp_path / "runs"
    outside = runs_dir.parent / "evil"
    outside.mkdir()
    for bad in ("..", "bad.id", "bad id", "a" * 100 + "/x"):
        resp = lab_client.post(f"/api/lab/runs/{bad}/delete")
        assert resp.status_code in (400, 404), bad  # 含 / 的走不到路由（404），其余 400
        if resp.status_code == 400:
            assert resp.get_json()["ok"] is False
    assert outside.exists() and runs_dir.exists()


def test_lab_runs_delete_404(lab_client):
    assert lab_client.post("/api/lab/runs/20260199T000000000000/delete").status_code == 404


def test_lab_runs_routes_admin_absent():
    """8080 主控制台不挂 /api/lab/runs 与 delete 路由。"""
    from quant_research_engine.gui.app import create_app

    rules = {r.rule for r in create_app().url_map.iter_rules()}
    assert "/api/lab/runs" not in rules
    assert "/api/lab/runs/<run_id>/delete" not in rules
