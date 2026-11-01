"""QRE-UNIVERSE-NEEQ-LEGACY：股票池卫生规则测试。

规则：自动解析的全市场宇宙要剔除 `920%.BJ`（北交所）代码，因为它们 2021-11-15
之前的 history 是三板残留脏数据（226 个代码 / 78,423 行 / 74.7% 垃圾行）。
`stock_daily` 源数据只读不改，所以在宇宙侧设闸。事实见
`docs/agent/20_DATA_DICTIONARY_DAILY_MINUTE.md` §2.2 与
`change_requests/CR-2026-10-29_polluted_jobs_purge.md`。
"""

from __future__ import annotations

from datetime import date

from quant_research_engine.data.universe_rules import (
    BJ_MARKET_OPEN,
    filter_untrusted_symbols,
    is_neeq_legacy_code,
)

CODES = ["000001.SZ", "600519.SH", "300750.SZ", "920809.BJ", "920641.BJ", "688981.SH"]


class TestIsNeeqLegacyCode:
    def test_bj_codes_are_flagged(self):
        assert is_neeq_legacy_code("920809.BJ") is True
        assert is_neeq_legacy_code("920000.BJ") is True

    def test_other_boards_are_not(self):
        for code in ("000001.SZ", "600519.SH", "300750.SZ", "688981.SH", "430047.BJ", "830799.BJ"):
            assert is_neeq_legacy_code(code) is False, code


class TestFilterUntrustedSymbols:
    def test_window_before_bj_open_drops_bj_codes(self):
        got = filter_untrusted_symbols(CODES, load_start=date(2010, 1, 4))
        assert got == ["000001.SZ", "600519.SH", "300750.SZ", "688981.SH"]

    def test_window_after_bj_open_keeps_everything(self):
        """加载区间整体在北交所开市之后 → 这些代码的数据是真实北交所行情，没有理由排除。"""
        got = filter_untrusted_symbols(CODES, load_start=date(2022, 1, 4))
        assert got == CODES

    def test_boundary_day_itself_is_safe(self):
        got = filter_untrusted_symbols(CODES, load_start=BJ_MARKET_OPEN)
        assert "920809.BJ" in got

    def test_warmup_reaching_into_dirty_period_drops_bj_codes(self):
        """回测起点在北交所开市之后，但 warm-up 伸进脏数据 → 仍须排除。

        增量路径 load_start = last_processed - warmup_days*2（默认 150 → 300 天），
        所以起点 2022-01-04 配 warmup 300 天会加载到 2021-03 前后，正是脏区间。
        """
        got = filter_untrusted_symbols(
            CODES, load_start=date(2022, 1, 4), warmup_days=300)
        assert "920809.BJ" not in got
        assert "000001.SZ" in got

    def test_warmup_that_stays_clean_keeps_bj_codes(self):
        got = filter_untrusted_symbols(
            CODES, load_start=date(2023, 1, 4), warmup_days=300)
        assert "920809.BJ" in got

    def test_empty_and_all_bj_inputs(self):
        assert filter_untrusted_symbols([], load_start=date(2010, 1, 4)) == []
        assert filter_untrusted_symbols(["920809.BJ"], load_start=date(2010, 1, 4)) == []

    def test_input_list_is_not_mutated(self):
        original = list(CODES)
        filter_untrusted_symbols(CODES, load_start=date(2010, 1, 4))
        assert CODES == original


class TestRuleIsWiredIntoUniverseResolution:
    """规则必须真的接在宇宙解析处，否则只是躺在模块里的一纸空文。"""

    def test_every_universe_resolution_site_uses_the_rule(self):
        """穷举全部「自动解析宇宙」的代码点，逐一确认接了规则。

        2026-10-29 第一版只接了 3 处，漏了 `apps/cli.py` 的 batch 命令和
        `gui/engine.py::_run_via_module` 的 batch 分支——而这两处才是 worker
        真正跑全市场回测的路径。规则写成模块却漏接 = 一纸空文，故用穷举锁死。
        新增宇宙解析点时，这里会红。
        """
        from pathlib import Path

        repo = Path(__file__).resolve().parents[1]
        sites = (
            "src/quant_research_engine/orchestration/research_run.py",
            "src/quant_research_engine/orchestration/incremental.py",
            "src/quant_research_engine/data/assembler.py",
            "src/quant_research_engine/gui/engine.py",
            "src/quant_research_engine/apps/cli.py",
            "src/quant_research_engine/game/data.py",
        )
        for rel in sites:
            text = (repo / rel).read_text(encoding="utf-8")
            assert "filter_untrusted_symbols" in text, f"{rel} 未接股票池卫生规则"

    def test_no_unresolved_full_market_resolution_left(self):
        """反向锁：任何「解析全市场宇宙」的调用点，前后邻域内必须出现规则调用。

        两种包装形态都要认：`filter(list_symbols...)`（调用在前）与
        `symbols = list_symbols...; symbols = filter(symbols)`（调用在后）。
        `list_symbols_with_bars` 的**定义处**（data/postgres.py）不是调用点，跳过。
        """
        import re
        from pathlib import Path

        repo = Path(__file__).resolve().parents[1]
        pattern = re.compile(r"load_security_metadata\(ts_codes=None\)|(?<!def )list_symbols_with_bars\(")
        offenders = []
        for path in sorted((repo / "src").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(repo).as_posix()
            if "universe_rules" in rel:
                continue
            for m in pattern.finditer(text):
                window = text[max(0, m.start() - 900): m.start() + 900]
                if "filter_untrusted_symbols" not in window:
                    line = text[:m.start()].count(chr(10)) + 1
                    offenders.append(f"{rel}@{line}")
        assert not offenders, f"这些位置解析了宇宙但没过卫生规则：{offenders}"

    def test_explicit_codes_are_not_filtered(self):
        """用户显式点名不替他改——research_run 里 request.codes 分支必须原样使用。"""
        from pathlib import Path

        repo = Path(__file__).resolve().parents[1]
        text = (repo / "src/quant_research_engine/orchestration/research_run.py").read_text(
            encoding="utf-8")
        assert "if request.codes:" in text and "symbols = list(request.codes)" in text, (
            "显式 codes 分支被过滤了——用户点名要某只股票时引擎不该替他改"
        )


class TestRandomUniverseSamplingAlsoFiltered:
    """随机抽样也是自动解析宇宙——抽样池必须先过卫生规则。"""

    def test_precheck_passes_truncated_start_to_sampler(self, monkeypatch):
        from quant_research_engine.gui import engine as gui_engine

        seen: dict[str, object] = {}

        def fake_sample(n, seed, *, db_url=None, start=None):
            seen["start"] = start
            return ["000001.SZ"]

        monkeypatch.setattr(gui_engine, "_sample_random_universe", fake_sample)
        trimmed, start, end = gui_engine.apply_precheck(
            [], "2010-01-04", "2026-03-31", max_codes=1, seed="rid-1")
        assert trimmed == ["000001.SZ"]
        # 抽样用的是「截断后的实际加载起点」，不是用户传的 2010 年
        assert seen["start"] == "2025-10-02", seen
        assert start == "2025-10-02"
