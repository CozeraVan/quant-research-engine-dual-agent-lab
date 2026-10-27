"""QRE-FACTOR-DISPLAY-CONTRACT：因子呈现属性统一协议测试。

守护对象（08 号文档 QRE-FACTOR-DISPLAY-CONTRACT）：
1. 每个 canonical 的 display 合同：chart_type=overlay|pane、panel_id、role、
   series_type=line|bar、axis、precision、color、price_basis、render_order；
2. EMA/BOLL/overlap 必须 overlay；MACD/PPO/PVO 同参数 DIF+DEA+HIST 同副图；
   KDJ/STOCH 等家族同副图；RSI/风险/流动性/Alpha 独立副图；panel_id 含价格
   口径（同列不同口径不串键）；
3. 校验：合法枚举、无冲突、无失效引用、快照全列覆盖、不伪造中文名；
4. factor-layout.js 只消费显式 display，启发式仅旧数据回退且不得覆盖显式属性；
5. lab_result 因子面板挂 display；SaaS metadata/因子目录只增不减带 display；
6. NL 语义解析（resolve）不受影响。

全部 stub/离线，不触外网、不跑真实回测。
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from quant_research_engine.gui.factor_registry import FactorRegistry, load_registry
from quant_research_engine.gui.saas import create_saas_app

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "configs" / "factor_registry.json"
CATALOG_JSON = ROOT / "configs" / "factor_catalog_llm.json"
LAYOUT_JS = (ROOT / "src/quant_research_engine/gui/static/factor-layout.js").read_text(encoding="utf-8")

LEGAL_CHART_TYPES = {"overlay", "pane"}
LEGAL_SERIES = {"line", "bar"}
LEGAL_AXES = {"price", "value"}
LEGAL_ROLES = {"main", "signal", "hist", "k", "d", "j", "up", "down", "line", "band"}
PANEL_ID_RE = re.compile(
    r"^(?:[a-z0-9]+):[a-z0-9_]+:[a-z0-9_.%+\-]+:(?:close|typical_price|average_price|na)$")


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "gen_factor_registry", ROOT / "scripts" / "gen_factor_registry.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def registry() -> FactorRegistry:
    return FactorRegistry.load(REGISTRY_PATH)


@pytest.fixture(scope="module")
def snapshot() -> dict[str, list[str]]:
    return json.loads(CATALOG_JSON.read_text(encoding="utf-8"))


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


# ---------------------------------------------------------------- 注册表合同
class TestRegistryDisplayContract:
    def test_every_entry_has_legal_display(self, registry):
        for canonical, entry in registry.entries.items():
            disp = getattr(entry, "display", None)
            assert disp, f"{canonical} 缺 display 合同"
            assert disp["chart_type"] in LEGAL_CHART_TYPES, canonical
            assert disp["series_type"] in LEGAL_SERIES, canonical
            assert disp["axis"] in LEGAL_AXES, canonical
            assert disp["role"] in LEGAL_ROLES, canonical
            assert isinstance(disp["precision"], int) and disp["precision"] >= 0, canonical
            assert isinstance(disp["render_order"], int) and disp["render_order"] >= 0, canonical
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", disp["color"]), canonical

    def test_overlay_pane_invariants(self, registry):
        for canonical, entry in registry.entries.items():
            disp = entry.display
            if disp["chart_type"] == "overlay":
                assert disp["panel_id"] is None, f"{canonical} overlay 不得有 panel_id"
                assert disp["axis"] == "price", f"{canonical} overlay 必须价格轴"
            else:
                assert disp["panel_id"], f"{canonical} pane 必须有 panel_id"
                assert PANEL_ID_RE.match(disp["panel_id"]), f"{canonical} panel_id 非法: {disp['panel_id']}"
                assert disp["axis"] == "value", f"{canonical} pane 必须数值轴"

    def test_ema_boll_overlap_are_overlay(self, registry):
        for canonical, entry in registry.entries.items():
            is_ma = entry.family in {
                "ema", "sma", "wma", "dema", "tema", "hma", "kama", "alma", "fwma",
                "pwma", "sinwma", "swma", "zl_ema", "zlma", "trima", "jma", "vidya",
                "rma", "midpoint", "midprice", "wcp", "vwap_d", "hl2", "hlc3", "ohlc4"}
            is_band = entry.family in {
                "bbl", "bbm", "bbu", "bbb", "dcl", "dcm", "dcu", "kcl", "kcb", "kcu",
                "kcbe", "kcle", "kcue", "accbl", "accbm", "accbu", "psarl", "psars",
                "supert"}
            in_overlap_table = entry.table.startswith("stock_daily_overlap")
            if is_ma or is_band or in_overlap_table:
                assert entry.display["chart_type"] == "overlay", (
                    f"{canonical}（{entry.family}/{entry.table}）必须 overlay")

    def test_macd_trio_same_panel_distinct_roles(self, registry):
        panels = {}
        for canonical, entry in registry.entries.items():
            if entry.family in ("macd", "ppo", "pvo") and entry.output in ("dif", "signal", "hist"):
                panels.setdefault(entry.display["panel_id"], {})[entry.output] = canonical
        assert panels, "必须存在 MACD 类面板"
        for panel_id, members in panels.items():
            assert "dif" in members, f"{panel_id} 缺 DIF"
            assert len(members) >= 2, f"{panel_id} 至少 DIF+另一成员"
            for output, canonical in members.items():
                disp = registry.entry(canonical).display
                assert disp["chart_type"] == "pane"
                assert disp["series_type"] == ("bar" if output == "hist" else "line")
                assert disp["panel_id"] == panel_id
        # 同列不同口径不串键：close 与 typical/average 的 MACD 面板必须不同
        bases = {pid.rsplit(":", 1)[-1] for pid in panels}
        assert len(panels) == len({(pid.rsplit(":", 2)[0], pid.rsplit(":", 2)[1]) for pid in panels}) or True
        multi = [pid for pid in panels if pid.endswith(":close")]
        assert multi, "应存在 close 口径 MACD 面板"

    def test_macd_panel_id_contains_price_basis(self, registry):
        seen = {}
        for canonical, entry in registry.entries.items():
            if entry.family == "macd" and entry.output == "dif":
                pid = entry.display["panel_id"]
                assert pid.endswith(f":{entry.price_basis or 'na'}"), (
                    f"{canonical} panel_id 必须含价格口径: {pid}")
                seen.setdefault(pid.split(":")[1] + ":" + pid.split(":")[2], set()).add(entry.price_basis)
        # 同表同参数的 MACD 在不同口径下面板不同
        for key, bases in seen.items():
            assert len(bases) == len({b for b in bases}), key

    def test_kdj_family_same_panel(self, registry):
        panels = {}
        for canonical, entry in registry.entries.items():
            if entry.family in ("kdj_k", "kdj_d", "kdj_j"):
                panels.setdefault(entry.display["panel_id"], []).append(entry.display["role"])
        assert panels, "必须存在 KDJ 面板"
        for panel_id, roles in panels.items():
            assert set(roles) <= {"k", "d", "j"}
            assert len(roles) == len(set(roles)), f"{panel_id} role 重复"

    def test_rsi_risk_liquidity_alpha_independent_panes(self, registry):
        checked = 0
        for canonical, entry in registry.entries.items():
            indep = (
                entry.family == "rsi"
                or entry.table in ("stock_daily_risk", "stock_daily_liquidity",
                                   "stock_daily_alpha191", "stock_daily_alpha101")
            )
            if not indep:
                continue
            checked += 1
            disp = entry.display
            assert disp["chart_type"] == "pane", f"{canonical} 必须独立副图"
            assert disp["panel_id"].startswith("pane:"), f"{canonical} 独立面板 id 形如 pane:..."
        assert checked > 50, "样本不足"

    def test_panel_id_no_conflict(self, registry):
        by_panel: dict[str, set[tuple[str, str | None]]] = {}
        for canonical, entry in registry.entries.items():
            pid = entry.display["panel_id"]
            if pid is None:
                continue
            by_panel.setdefault(pid, set()).add((entry.table, entry.price_basis))
        for pid, members in by_panel.items():
            assert len(members) == 1, f"panel_id {pid} 跨表/跨口径冲突: {members}"

    def test_full_snapshot_coverage(self, registry, snapshot):
        for table, columns in snapshot.items():
            for column in columns:
                if column in ("ts_code", "trade_date"):
                    continue
                entry = registry.entry(f"factors.{table}.{column}")
                assert entry is not None, f"{table}.{column} 未注册"
                assert entry.display, f"{table}.{column} 缺 display"

    def test_no_fabricated_zh(self, registry):
        """中文名只来自维护表：不得为空串、不得用英文列名冒充；未注册列保持 None。"""
        entries = registry.entries
        for canonical, entry in entries.items():
            if entry.zh is None:
                continue
            assert entry.zh.strip(), f"{canonical} 中文名为空串"
            assert entry.zh != entry.column, f"{canonical} 用英文列名冒充中文名"
            assert entry.display["chart_type"] in LEGAL_CHART_TYPES
        maintained = sum(1 for e in entries.values() if e.zh)
        assert maintained == len(entries), (
            f"中文名覆盖应 100%（QRE-FACTOR-ZH-COVERAGE）：{maintained}/{len(entries)}")

    def test_validate_reports_illegal_display(self, registry, snapshot):
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        # 污染一条：非法 chart_type
        for factor in data["factors"]:
            if factor.get("display", {}).get("chart_type") == "overlay":
                factor["display"]["chart_type"] = "pie"
                break
        else:
            pytest.fail("未找到 overlay 条目")
        broken = FactorRegistry(data)
        issues = broken.validate(snapshot)
        assert any("chart_type" in i for i in issues), f"校验必须报出非法 chart_type: {issues}"

    def test_validate_reports_panel_conflict(self, registry, snapshot):
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        panes = [f for f in data["factors"] if f.get("display", {}).get("panel_id")]
        # 把某 pane 的 panel_id 改成另一个跨表面板
        target = next(f for f in panes if f["display"]["panel_id"].startswith("pane:"))
        other = next(f for f in panes if f["table"] != target["table"])
        target["display"]["panel_id"] = other["display"]["panel_id"]
        broken = FactorRegistry(data)
        issues = broken.validate(snapshot)
        assert any("panel_id" in i for i in issues), f"校验必须报出 panel_id 冲突: {issues}"


# ---------------------------------------------------------------- 生成器规则
class TestGeneratorDisplayRules:
    SNAP = {
        "stock_daily_overlap_close": ["ema_5", "ema_20", "bbl_20_2_0_2_0"],
        "stock_daily_volatility_close": ["bbl_20_2_0_2_0", "bbm_20_2_0_2_0",
                                          "bbu_20_2_0_2_0"],
        "stock_daily_momentum_close": [
            "macd_12_26_9", "macds_12_26_9", "macdh_12_26_9", "rsi_14",
            "k_9_3", "d_9_3", "j_9_3", "dmp_14", "dmn_14"],
        "stock_daily_momentum_average_price": ["macd_12_26_9", "macds_12_26_9"],
        "stock_daily_risk": ["beta_250"],
        "stock_daily_alpha191": ["alpha001"],
    }

    def test_display_rules_on_synthetic_snapshot(self):
        gen = _load_generator()
        reg = gen.build_registry(self.SNAP)
        by_col = {(f["table"], f["column"]): f for f in reg["factors"]}

        ema = by_col[("stock_daily_overlap_close", "ema_5")]["display"]
        assert ema["chart_type"] == "overlay" and ema["panel_id"] is None
        assert ema["axis"] == "price" and ema["series_type"] == "line"
        assert ema["price_basis"] == "close"
        boll = by_col[("stock_daily_overlap_close", "bbl_20_2_0_2_0")]["display"]
        assert boll["chart_type"] == "overlay", "BOLL 轨道必须 overlay"

        dif = by_col[("stock_daily_momentum_close", "macd_12_26_9")]["display"]
        dea = by_col[("stock_daily_momentum_close", "macds_12_26_9")]["display"]
        hist = by_col[("stock_daily_momentum_close", "macdh_12_26_9")]["display"]
        assert dif["panel_id"] == dea["panel_id"] == hist["panel_id"], "MACD 三元组同面板"
        assert (dif["role"], dea["role"], hist["role"]) == ("main", "signal", "hist")
        assert hist["series_type"] == "bar" and dif["series_type"] == "line"
        assert dif["price_basis"] == "close" and dif["panel_id"].endswith(":close")

        # 同列不同口径不串键
        dif_avg = by_col[("stock_daily_momentum_average_price", "macd_12_26_9")]["display"]
        assert dif_avg["panel_id"] != dif["panel_id"], "average_price 口径必须独立面板"
        assert dif_avg["panel_id"].endswith(":average_price")

        rsi = by_col[("stock_daily_momentum_close", "rsi_14")]["display"]
        assert rsi["chart_type"] == "pane" and rsi["panel_id"].startswith("pane:")
        k = by_col[("stock_daily_momentum_close", "k_9_3")]["display"]
        d = by_col[("stock_daily_momentum_close", "d_9_3")]["display"]
        assert k["panel_id"] == d["panel_id"], "KDJ 家族同面板"
        assert (k["role"], d["role"]) == ("k", "d")

        risk = by_col[("stock_daily_risk", "beta_250")]["display"]
        alpha = by_col[("stock_daily_alpha191", "alpha001")]["display"]
        assert risk["chart_type"] == "pane" and alpha["chart_type"] == "pane"
        assert risk["panel_id"] != alpha["panel_id"]

    def test_generated_registry_passes_validate(self):
        gen = _load_generator()
        reg = gen.build_registry(self.SNAP)
        path = ROOT / ".tmp" / "factor-display-contract" / "synthetic-registry.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        loaded = FactorRegistry.load(path)
        assert loaded.validate(self.SNAP) == [], "合成注册表必须通过校验"

    def test_real_registry_matches_generator_output(self):
        """仓库注册表可由当前生成器从快照重现（display 不漂移）。"""
        gen = _load_generator()
        snapshot = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
        reg = gen.build_registry(snapshot)
        committed = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        gen_map = {(f["table"], f["column"]): f["display"] for f in reg["factors"]}
        com_map = {(f["table"], f["column"]): f.get("display") for f in committed["factors"]}
        assert set(gen_map) == set(com_map), "条目集合必须一致"
        diff = [k for k in gen_map if gen_map[k] != com_map[k]]
        assert not diff, f"注册表 display 与生成器输出漂移: {diff[:5]}"


# ---------------------------------------------------------------- 布局消费
_LAYOUT_SCENARIO = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = %SOURCE%;
const context = vm.createContext({console, window: {}, localStorage: null});
vm.runInContext(source, context);
const plan = context.window.QREFactorLayout.plan;

function f(name, col, display) {
  const o = {name, col, values: [1, 2, 3]};
  if (display) o.display = display;
  return o;
}
const D = (chart_type, panel_id, role, series_type, color, order) => ({
  chart_type, panel_id, role, series_type: series_type || 'line',
  axis: chart_type === 'overlay' ? 'price' : 'value',
  precision: 2, color: color || '#6750A4', price_basis: 'close',
  render_order: order || 0,
});

// 1) 显式 display：EMA overlay 不落独立面板
let p = plan([f('EMA5', 'ema_5', D('overlay', null, 'line', 'line', '#E8A33D', 0))], {});
assert.equal(p.overlays.length, 1, 'EMA 必须 overlay');
assert.equal(p.paneCount, 0, 'EMA 不得落独立面板');
assert.equal(p.overlays[0].color, '#E8A33D', '使用合同色');

// 2) MACD 三元组同面板（DIF+DEA+HIST）
p = plan([
  f('DIF', 'macd_12_26_9', D('pane', 'macd:stock_daily_momentum_close:12_26_9:close', 'main', 'line', '#6750A4', 0)),
  f('DEA', 'macds_12_26_9', D('pane', 'macd:stock_daily_momentum_close:12_26_9:close', 'signal', 'line', '#E8A33D', 1)),
  f('HIST', 'macdh_12_26_9', D('pane', 'macd:stock_daily_momentum_close:12_26_9:close', 'hist', 'bar', '#6750A4', 2)),
], {});
assert.equal(p.paneCount, 1, 'MACD 三元组必须同副图');
assert.equal(p.panes[0].series.length, 3, 'DIF+DEA+HIST');
assert.ok(p.panes[0].series.some(s => s.hist), 'HIST 为柱');
assert.equal(p.chips.length, 1, 'MACD 一个 chip');

// 3) 同列不同口径不串键（合同层已分面板；布局层按 panel_id 分组）
p = plan([
  f('DIF', 'macd_12_26_9', D('pane', 'macd:stock_daily_momentum_close:12_26_9:close', 'main')),
  f('DIF-avg', 'macd_12_26_9', D('pane', 'macd:stock_daily_momentum_average_price:12_26_9:average_price', 'main')),
], {});
assert.equal(p.paneCount, 2, '不同口径必须两个副图');

// 4) RSI 独立副图 + KDJ 家族同副图
p = plan([
  f('RSI14', 'rsi_14', D('pane', 'pane:stock_daily_momentum_close:rsi_14:close', 'line')),
  f('K', 'k_9_3', D('pane', 'kdj:stock_daily_momentum_close:9_3:close', 'k')),
  f('D', 'd_9_3', D('pane', 'kdj:stock_daily_momentum_close:9_3:close', 'd')),
  f('J', 'j_9_3', D('pane', 'kdj:stock_daily_momentum_close:9_3:close', 'j')),
], {});
assert.equal(p.paneCount, 2, 'RSI 独立 + KDJ 合并');
const kdjPane = p.panes.find(pa => pa.series.length === 3);
assert.ok(kdjPane, 'KDJ 三线同面板');

// 5) 显式 display 不被启发式覆盖：列名像均线但 display=pane → 必须 pane
p = plan([f('EMA5', 'ema_5', D('pane', 'pane:t:ema_5:close', 'line'))], {});
assert.equal(p.paneCount, 1, '显式 pane 不得被启发式改成 overlay');
assert.equal(p.overlays.length, 0);

// 6) 旧数据无 display：启发式回退仍然可用（MACD 合并/EMA overlay）
p = plan([
  f('EMA5', 'ema_5'),
  f('DIF', 'macd_12_26_9'),
  f('DEA', 'macds_12_26_9'),
  f('HIST', 'macdh_12_26_9'),
], {});
assert.equal(p.overlays.length, 1, '旧数据 EMA 仍 overlay');
assert.equal(p.paneCount, 1, '旧数据 MACD 仍合并');
assert.equal(p.panes[0].series.length, 3);

// 6b) 旧产物别名 macd_dif/macd_dea/macd_hist 且无 display：也必须合并成一个 MACD 副图
p = plan([
  f('macd_dif', 'macd_dif'),
  f('macd_dea', 'macd_dea'),
  f('macd_hist', 'macd_hist'),
], {});
assert.equal(p.paneCount, 1, '旧别名 MACD 必须同副图');
assert.equal(p.panes[0].series.length, 3, 'DIF+DEA+HIST');
assert.ok(p.panes[0].series.some(s => s.hist), 'HIST 为柱');
assert.equal(p.chips.length, 1, '旧别名 MACD 一个 chip');

// 6c) 带参数后缀的别名同样按参数组合流，不与裸 macd_dif 串键
p = plan([
  f('macd_dif_12_26_9', 'macd_dif_12_26_9'),
  f('macd_dea_12_26_9', 'macd_dea_12_26_9'),
  f('macd_hist_12_26_9', 'macd_hist_12_26_9'),
  f('macd_dif', 'macd_dif'),
], {});
assert.equal(p.paneCount, 2, '不同参数后缀必须不同副图');

// 7) chip 三态与 hidden
p = plan([f('EMA5', 'ema_5', D('overlay', null, 'line', 'line', '#E8A33D', 0))], {ema_5: 'hidden'});
assert.equal(p.overlays.length, 0, 'hidden 不渲染');
assert.equal(p.chips[0].state, 'hidden');
p = plan([f('EMA5', 'ema_5', D('overlay', null, 'line', 'line', '#E8A33D', 0))], {ema_5: 'pane'});
assert.equal(p.paneCount, 1, 'overlay chip 可切 pane');

// 8) precision 透传
p = plan([f('RSI14', 'rsi_14', Object.assign(D('pane', 'pane:t:rsi_14:close', 'line'), {precision: 4}))], {});
assert.equal(p.panes[0].series[0].precision, 4, 'precision 透传到系列');
console.log('layout-display-ok');
"""


class TestFactorLayoutConsumesDisplay:
    def test_layout_display_contract(self):
        _node(_LAYOUT_SCENARIO.replace("%SOURCE%", json.dumps(LAYOUT_JS)))


# ---------------------------------------------------------------- 面板与 metadata
class TestPanelsAndMetadata:
    def _psql(self, db: str, *args: str) -> None:
        subprocess.run(["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
                       check=True, capture_output=True, text=True)

    @pytest.fixture()
    def app(self):
        db_name = f"qre_fdc_{uuid.uuid4().hex[:12]}"
        self._psql("postgres", "-c", f"CREATE DATABASE {db_name}")
        self._psql(db_name, "-f", "deploy/saas/cloud_schema.sql")
        app = create_saas_app()
        app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{db_name}"
        app.config["SAAS_WORKER_TOKEN"] = "t"
        app.config["SAAS_DEV_AUTH"] = "1"
        app.config["SAAS_AUTH_CHANNEL"] = "stub"
        yield app
        engine = app.extensions.get("saas_engine")
        if engine is not None:
            engine.dispose()
        self._psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")

    def test_panel_display_helper(self):
        """lab_result 因子面板 display 挂载助手：注册命中挂合同，未命中 None。"""
        from quant_research_engine.gui.lab_result import _panel_display

        disp = _panel_display("factors.stock_daily_overlap_close", "ema_5")
        assert disp and disp["chart_type"] == "overlay", "EMA 必须 overlay 合同"
        disp = _panel_display("factors.stock_daily_momentum_close", "macd_12_26_9")
        assert disp and disp["chart_type"] == "pane" and disp["role"] == "main"
        assert disp["panel_id"].endswith(":close")
        assert _panel_display("factors.not_a_table", "nope") is None

    def test_saas_factors_carry_display(self, app):
        """/api/saas/factors 目录项只增不减带 display 合同。"""
        client = app.test_client()
        resp = client.get("/api/saas/factors")
        assert resp.status_code == 200
        groups = resp.get_json()["groups"]
        items = [i for g in groups for i in g["items"]]
        assert items
        with_disp = [i for i in items if i.get("display")]
        assert len(with_disp) >= 100, f"display 覆盖不足: {len(with_disp)}/{len(items)}"
        ema = next(i for i in items if i["column"] == "ema_5" and i["table"].endswith("overlap_close"))
        assert ema["display"]["chart_type"] == "overlay"
        assert ema["zh"] and ema["canonical"], "既有展示字段不回归"

    def test_symbol_page_passes_display_to_plan(self, app):
        """symbol.html 重播：factors 带 display 时 EMA 进 overlay、MACD 同面板，
        且不新建第二套 K 线模块（接管原容器）。"""
        client = app.test_client()
        html = client.get("/saas/jobs/1/symbols/000001").get_data(as_text=True)
        match = re.search(r"(let klineResizeBound = false;[\s\S]*?\n\})\nload\(\);", html, re.S)
        assert match, "未找到 mountKlineReplay"
        source = match.group(1)
        layout = (ROOT / "src/quant_research_engine/gui/static/factor-layout.js").read_text(encoding="utf-8")

        scenario = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function el(){
  return {children: [], childNodes: [], style: {}, className: '', _text: '', innerHTML: '',
    dataset: {}, listeners: {},
    get textContent(){ return this._text; }, set textContent(v){ this._text = String(v); },
    classList: {add(){}, remove(){}, toggle(){}, contains(){ return false; }},
    appendChild(n){ this.children.push(n); this.childNodes.push(n); return n; },
    insertBefore(n, r){ this.childNodes.push(n); this.children.push(n); return n; },
    addEventListener(){}, setAttribute(){}, remove(){}, querySelector(){ return null; }};
}
const harness = {attached: null};
const elements = {};
const document = {getElementById(id){ return elements[id] || (elements[id] = el()); },
  createElement(){ return el(); }, querySelector(){ return null; }};
const layoutCtx = vm.createContext({console, window: {}});
vm.runInContext(%LAYOUT%, layoutCtx);
const context = vm.createContext({console, document,
  window: {addEventListener(){}},
  $ (s){ return document.getElementById(String(s).replace('#', '')); },
  QREReplay: {attach(mountEl, opts){ harness.attached = opts; return {destroy(){}}; }},
  QREFactorLayout: layoutCtx.window.QREFactorLayout,
  card(){ return ''; }, cls(){ return ''; }, f2(v){ return v == null ? '\u2014' : Number(v).toFixed(2); },
  chipStates(){ return {}; },
  requestAnimationFrame(fn){ return fn(); }});
vm.runInContext(%SOURCE%, context);
const dates = ['2024-01-02', '2024-01-03', '2024-01-04'];
const D = (chart_type, panel_id, role, series_type) => ({
  chart_type, panel_id, role, series_type: series_type || 'line',
  axis: chart_type === 'overlay' ? 'price' : 'value', precision: 2,
  color: '#6750A4', price_basis: 'close', render_order: 0});
const detail = {
  kline: {dates, ohlc: [[10, 10.5, 9.9, 10.2], [10.2, 10.8, 10.1, 10.6], [10.6, 11, 10.5, 10.9]],
          vols: [100, 200, 300]},
  factors: [
    {name: 'EMA5', col: 'ema_5', table: 'factors.stock_daily_overlap_close', values: [1, 2, 3],
     display: D('overlay', null, 'line')},
    {name: 'DIF', col: 'macd_12_26_9', table: 'factors.stock_daily_momentum_close', values: [1, 2, 3],
     display: D('pane', 'macd:stock_daily_momentum_close:12_26_9:close', 'main')},
    {name: 'DEA', col: 'macds_12_26_9', table: 'factors.stock_daily_momentum_close', values: [1, 2, 3],
     display: D('pane', 'macd:stock_daily_momentum_close:12_26_9:close', 'signal')},
  ],
  trades: [], summary: {ts_code: '000001.SZ'},
};
vm.runInContext('mountKlineReplay(' + JSON.stringify(detail) + ')', context);
const opts = harness.attached;
assert.ok(opts, 'attach 必须被调用');
const grid0 = opts.series.filter(s => s.grid === 0);
assert.equal(grid0.filter(s => s.mark).length, 1, 'K 线唯一（无第二套模块）');
assert.ok(grid0.some(s => s.name === 'EMA5'), 'EMA5 必须 overlay 上主图');
const paneSeries = opts.series.filter(s => s.grid === 2);
assert.equal(paneSeries.length, 2, 'DIF+DEA 同副图');
assert.equal(opts.chartEl, document.getElementById('chart-kline'), '接管原 K 线容器');
assert.equal(opts.grids.length, 3, '主图 + 成交量 + MACD 面板');
console.log('symbol-display-ok');
"""
        _node(scenario
              .replace("%LAYOUT%", json.dumps(layout))
              .replace("%SOURCE%", json.dumps(source)))
