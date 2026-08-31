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
            ["symbol", "entry_date", "exit_date", "holding_days", "net_return", "net_pnl", "exit_reason"],
            [["000001.SZ", "2024-01-02", "2024-01-04", 5, 0.02, 100, "holding_period"],
             ["000001.SZ", "2024-01-02", "2024-01-04", 3, 0.005, 100, "holding_period"],
             ["000001.SZ", "2024-01-02", "2024-01-04", 7, 0.015, 100, "holding_period"]],
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
    assert "chart-data" in html
    assert "dataZoom" in html
    assert "回撤" in html and "赚钱效应归因" in html and "treemap" in html
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
    # 基准：测试环境 DB 可用则 5 指数，不可用则 None + note，两者都合法
    if d["benchmarks"] is not None:
        assert set(d["benchmarks"]) == {"000001.SH", "000300.SH", "000905.SH", "000852.SH", "399006.SZ"}
        for v in d["benchmarks"].values():
            assert len(v["closes"]) == 5
    else:
        assert d["benchmark_note"]


def test_lab_chart_data_404(lab_client):
    assert lab_client.get("/api/lab/runs/ghost/chart-data").status_code == 404


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
        ("S1", "中信L1:电子", "A"),          # QRE-GUI-LAB-RESULT-026：也收，去前缀后与申万L1重名 → 同股只计一次
        ("S3", "申万L1:银行", "A"),
        ("S1", "人工智能", "B"), ("S2", "人工智能", "B"),
        ("S1", "动量20日:偏强(5-20%)", "C"),
        ("S9", "无交易股票", "B"),            # 不在 stats 中 → 忽略
    ]
    names = {"S1": "股票一", "S2": "股票二", "S3": "股票三"}
    layers = _aggregate_tag_layers(stats, tag_rows, names)

    # A 层：电子(S1+S2，S1 双前缀去重只计一次) 与 银行(S3)，按 |total_pnl| 降序
    assert [t["tag"] for t in layers["A"]] == ["电子", "银行"]
    elec = layers["A"][0]
    assert elec["total_pnl"] == 200.0
    assert elec["trades"] == 3          # 若未去重会是 5（S1 被两个前缀计两次）
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
                       ("000001.SZ", "国际", "A")],  # A 层不计入
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
