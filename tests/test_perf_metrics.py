"""风险调整收益指标与持股周期：JS 共享层 vs Python 权威实现的交叉验证。

QRE-PERF-METRICS-CONTRACT：`static/perf-metrics.js` 与
`risk/performance.py` 是**两套独立实现**（前端算 + 后端算），必须逐值一致。
本文件用 Python 权威实现在同一序列上现算期望值，再让 Node vm 跑真实
`perf-metrics.js` 比对，容差 1e-9——任何一侧公式漂移立即失败。

同时锁定：
- 常量与 `risk/constants.py` 一致（rf=0.03、ann=252），读源码断言；
- 边界行为（样本不足 / 基准方差 0 / 非法日期）不抛错、返回 null；
- `holding_days` 口径为自然日（与 `round_trips.csv` 的 holding_days 列一致）。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PERF_JS = (REPO / "src/quant_research_engine/gui/static/perf-metrics.js").read_text(
    encoding="utf-8"
)
CONSTANTS_PY = (REPO / "src/quant_research_engine/risk/constants.py").read_text(
    encoding="utf-8"
)
SYMBOL_TPL = (
    REPO / "src/quant_research_engine/gui/saas/templates/symbol.html"
).read_text(encoding="utf-8")
JOB_TPL = (REPO / "src/quant_research_engine/gui/saas/templates/job.html").read_text(
    encoding="utf-8"
)

TOL = 1e-9


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def _python_expected() -> dict:
    """Python 权威实现的期望值（测试运行时现算，永不过期）。

    注意：期望值必须按 **JS 实际看到的序列** 算——即从净值曲线差分出的日收益，
    而不是构造策略时的原始收益序列。cumprod 后差分会丢掉第一个点
    （400 点净值 → 399 个收益），两边各算各的会整体错位一位，Sharpe 能差 2.6%。
    """
    import numpy as np

    from quant_research_engine.risk.performance import performance_summary

    cases: dict[str, dict] = {}
    # beta_true 故意取 0.116 / 0.85 / 1.4：覆盖低相关、中相关、高 beta 三种形态
    for name, seed, beta_true in (
        ("decorrelated", 20261028, 0.116),
        ("correlated", 777, 0.85),
        ("highbeta", 4242, 1.4),
    ):
        rng = np.random.default_rng(seed)
        market = rng.normal(0.0002, 0.011, 400)
        strat = beta_true * market + rng.normal(0.0003, 0.006, 400)
        equity = list(np.cumprod(1 + strat))
        bench = list(np.cumprod(1 + market))
        py_r = [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity))]
        py_m = [bench[i] / bench[i - 1] - 1 for i in range(1, len(bench))]
        s = performance_summary(py_r, py_m)
        cases[name] = {
            "equity": equity,
            "bench_closes": bench,
            "sharpe": s["sharpe"]["sharpe"],
            "beta": s["beta"],
            "ir": s["information_ratio"]["information_ratio"],
            "alpha_annual": s["jensens_alpha"]["alpha_annual"],
            "jensen_beta": s["jensens_alpha"]["beta"],
            "n_obs": s["n_obs"],
        }
    return cases


_CASES = _python_expected()

_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = %SOURCE%;
const ctx = { console, window: {}, module: undefined, exports: undefined };
const context = vm.createContext(ctx);
vm.runInContext(source, context);
const P = context.window.QREPerfMetrics;
globalThis.P = P;
"""


def _scenario(cases: dict) -> str:
    return _HARNESS.replace("%SOURCE%", json.dumps(PERF_JS)) + r"""
const CASES = %CASES%;
const TOL = %TOL%;
for (const name of Object.keys(CASES)) {
  const c = CASES[name];
  // 1) riskAdjusted 主入口（benchmark 无 dates → 直接差分路径，对应 job 页）
  const ra = P.riskAdjusted({ equity: c.equity, benchmark: { name: 'X', closes: c.bench_closes } });
  assert.ok(ra, name + ': riskAdjusted 不得返回 null');
  assert.ok(Math.abs(ra.sharpe - c.sharpe) < TOL, name + ' sharpe ' + ra.sharpe + ' vs ' + c.sharpe);
  assert.ok(Math.abs(ra.beta - c.beta) < TOL, name + ' beta ' + ra.beta + ' vs ' + c.beta);
  assert.ok(Math.abs(ra.ir - c.ir) < TOL, name + ' ir ' + ra.ir + ' vs ' + c.ir);
  assert.ok(Math.abs(ra.alpha_annual - c.alpha_annual) < TOL,
            name + ' alpha ' + ra.alpha_annual + ' vs ' + c.alpha_annual);
  assert.equal(ra.n, c.n_obs, name + ' n_obs');

  // 2) 单函数入口与主入口必须自洽（beta 与 jensensAlpha.beta 同源）
  const r = P.dailyReturns(c.equity);
  const m = P.dailyReturns(c.bench_closes);
  const n = Math.min(r.length, m.length);
  const rr = r.slice(r.length - n), mm = m.slice(m.length - n);
  assert.ok(Math.abs(P.sharpe(rr) - c.sharpe) < TOL, name + ' sharpe()');
  assert.ok(Math.abs(P.beta(rr, mm) - c.beta) < TOL, name + ' beta()');
  assert.ok(Math.abs(P.informationRatio(rr, mm) - c.ir) < TOL, name + ' informationRatio()');
  const ja = P.jensensAlpha(rr, mm);
  assert.ok(ja && Math.abs(ja.alpha_annual - c.alpha_annual) < TOL, name + ' jensensAlpha()');
  assert.ok(Math.abs(ja.beta - c.jensen_beta) < TOL, name + ' jensens beta');

  // 3) benchmark 带 dates 的对齐路径（对应 symbol 页 kline 基准）
  const dates = c.equity.map((_, i) => '2024-01-04').map((d, i) => {
    const t = new Date(Date.UTC(2024, 0, 4 + i));
    return t.toISOString().slice(0, 10);
  });
  const ra2 = P.riskAdjusted({
    equity: c.equity, dates,
    benchmark: { name: 'hold', dates, closes: c.bench_closes },
  });
  assert.ok(ra2 && Math.abs(ra2.beta - c.beta) < TOL, name + ' dated benchmark beta');
  assert.ok(Math.abs(ra2.alpha_annual - c.alpha_annual) < TOL, name + ' dated benchmark alpha');
}
console.log('perf-metrics-cross-ok');
""".replace("%CASES%", json.dumps(cases)).replace("%TOL%", repr(TOL))


def test_js_matches_python_performance_summary():
    """JS 指标与 Python performance_summary 在三组序列上逐值一致（1e-9）。"""
    _node(_scenario(_CASES))


def test_js_matches_python_when_series_have_gaps():
    """equity/benchmark 含 null 与非法值时，JS 必须与 Python 在配对 dropna 后一致。"""
    import numpy as np

    from quant_research_engine.risk.performance import performance_summary

    rng = np.random.default_rng(31337)
    market = list(rng.normal(0.0002, 0.011, 300))
    strat = list(0.8 * np.asarray(market) + rng.normal(0.0003, 0.006, 300))
    eq = list(np.cumprod(1 + np.asarray(strat)))
    bc = list(np.cumprod(1 + np.asarray(market)))
    # 打成两处缺口（ equities 的第 50 与第 180 个点）
    eq[50] = None
    eq[180] = 0.0
    bc[50] = None
    bc[180] = None
    # Python 侧同样按「前值有效才算收益」过滤
    py_r, py_m = [], []
    for i in range(1, len(eq)):
        a, b = eq[i - 1], eq[i]
        ma, mb = bc[i - 1], bc[i]
        if a is None or b is None or ma is None or mb is None:
            continue
        if a <= 0 or b <= 0 or ma <= 0 or mb <= 0:
            continue
        py_r.append(b / a - 1)
        py_m.append(mb / ma - 1)
    s = performance_summary(py_r, py_m)
    _node(
        _HARNESS.replace("%SOURCE%", json.dumps(PERF_JS))
        + r"""
const CASES = {gaps: %s};
const TOL = %s;
const c = CASES.gaps;
const ra = P.riskAdjusted({equity: c.equity, benchmark: {name: 'X', closes: c.bench_closes}});
assert.ok(ra, 'gaps: 不得返回 null');
assert.ok(Math.abs(ra.sharpe - c.sharpe) < TOL, 'gaps sharpe ' + ra.sharpe + ' vs ' + c.sharpe);
assert.ok(Math.abs(ra.beta - c.beta) < TOL, 'gaps beta ' + ra.beta + ' vs ' + c.beta);
assert.ok(Math.abs(ra.ir - c.ir) < TOL, 'gaps ir ' + ra.ir + ' vs ' + c.ir);
assert.ok(Math.abs(ra.alpha_annual - c.alpha_annual) < TOL, 'gaps alpha');
console.log('perf-metrics-gaps-ok');
"""
        % (
            json.dumps(
                {
                    "equity": eq,
                    "bench_closes": bc,
                    "sharpe": s["sharpe"]["sharpe"],
                    "beta": s["beta"],
                    "ir": s["information_ratio"]["information_ratio"],
                    "alpha_annual": s["jensens_alpha"]["alpha_annual"],
                }
            ),
            repr(TOL),
        )
    )


# ---------------------------------------------------------------- 边界行为
_BOUNDARY = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = %SOURCE%;
const context = vm.createContext({ console, window: {}, module: undefined, exports: undefined });
vm.runInContext(source, context);
const P = context.window.QREPerfMetrics;

// 样本不足：1 个点 / 空数组 → 全部 null，不抛错
assert.equal(P.riskAdjusted({equity: [100], benchmark: {closes: [200, 201]}}), null);
assert.equal(P.riskAdjusted({equity: [], benchmark: {closes: [200, 201]}}), null);
assert.equal(P.riskAdjusted({equity: [100, 101], benchmark: {closes: []}}), null);
assert.equal(P.riskAdjusted({}), null);
assert.equal(P.riskAdjusted(null), null);

// 基准恒定（方差 0）→ beta/alpha 无法回归，JS 降级为 null；
// ir 仍然有效（active = 策略 − 恒定基准，TE = 策略自身波动），sharpe 也只依赖策略自身。
// 注意：Python 的 beta()/jensens_alpha() 在基准方差 0 时是 raise ValueError，
// 前端不能抛错，所以这里断言的是「JS 的降级行为」而非与 Python 比数值。
const flat = P.riskAdjusted({equity: [100, 101, 102, 103], benchmark: {closes: [50, 50, 50, 50]}});
assert.ok(flat, '恒定基准不得整体 null');
assert.equal(flat.beta, null, '恒定基准 beta 必须降级 null');
assert.equal(flat.alpha_annual, null, '恒定基准 alpha 必须降级 null');
assert.ok(isFinite(flat.ir), '恒定基准 ir 仍有效（TE=策略自身波动）');
assert.ok(isFinite(flat.sharpe), '恒定基准 sharpe 仍可算');

// equity 含 0 / 负值 → 那些位被跳过，不产生 NaN/Infinity
const dirty = P.riskAdjusted({equity: [100, 0, 101, 102, -5, 103, 104], benchmark: {closes: [10, 11, 12, 13, 14, 15, 16]}});
assert.ok(dirty, '脏净值不得整体 null');
for (const k of ['sharpe', 'beta', 'ir', 'alpha_annual']) {
  assert.ok(dirty[k] == null || isFinite(dirty[k]), k + ' 不得为 NaN/Infinity: ' + dirty[k]);
}

// 长度不齐：benchmark 比 equity 短 → 取尾部对齐，不抛错
const short = P.riskAdjusted({equity: [100, 101, 102, 103, 104], benchmark: {closes: [10, 11]}});
assert.equal(short, null, '对齐后不足 2 个收益 → null');

// holdingDaysOf：自然日；缺字段 / 未平仓 / 非法日期 → null
assert.equal(P.holdingDaysOf({entry_date: '2025-04-21', exit_date: '2025-05-22'}), 31);
assert.equal(P.holdingDaysOf({entry_date: '2025-10-16', exit_date: '2025-11-13'}), 28);
assert.equal(P.holdingDaysOf({entry_date: '2025-04-21'}), null, '未平仓不得算 0');
assert.equal(P.holdingDaysOf({exit_date: '2025-05-22'}), null);
assert.equal(P.holdingDaysOf({entry_date: '', exit_date: ''}), null);
assert.equal(P.holdingDaysOf({entry_date: 'bad', exit_date: '2025-05-22'}), null);
assert.equal(P.holdingDaysOf({entry_date: '2025-05-22', exit_date: '2025-04-21'}), null, '倒挂不得给负数');
assert.equal(P.holdingDaysOf(null), null);

// avgHoldingDays：跳过无效行；全无效 → null（不编 0）
assert.equal(P.avgHoldingDays([]), null);
assert.equal(P.avgHoldingDays(null), null);
assert.equal(P.avgHoldingDays([{entry_date: '2025-04-21'}]), null);
assert.equal(P.avgHoldingDays([
  {entry_date: '2025-04-21', exit_date: '2025-05-22'},      // 31
  {entry_date: '2025-10-16', exit_date: '2025-11-13'},      // 28
  {entry_date: '2025-01-01'},                                // 跳过
]), 29.5);
console.log('perf-metrics-boundary-ok');
"""


def test_boundaries_return_null_not_nan():
    """样本不足 / 基准恒定 / 脏净值 / 非法日期一律降级，不抛错不造值。"""
    _node(_BOUNDARY.replace("%SOURCE%", json.dumps(PERF_JS)))


# ---------------------------------------------------------------- 源码合同
class TestSourceContract:
    def test_constants_match_risk_constants_py(self):
        """rf / ann 必须与 risk/constants.py 一致——常量漂移即失败。"""
        ann = re.search(r"ANNUALIZATION_FACTOR\s*=\s*(\d+)", CONSTANTS_PY)
        rf = re.search(r"DEFAULT_RISK_FREE_RATE\s*=\s*([0-9.]+)", CONSTANTS_PY)
        assert ann and rf, "未找到 risk/constants.py 常量"
        assert f"var ANN = {ann.group(1)};" in PERF_JS, (
            f"perf-metrics.js 的 ANN 必须等于 {ann.group(1)}"
        )
        assert f"var RF = {rf.group(1)};" in PERF_JS, (
            f"perf-metrics.js 的 RF 必须等于 {rf.group(1)}"
        )

    def test_formulas_documented_against_python(self):
        """每个指标函数必须注释其 Python 出处，防止后续"顺手改公式"。"""
        for fn, anchor in (
            ("function sharpe(", "performance.sharpe_ratio"),
            ("function beta(", "performance.beta"),
            ("function informationRatio(", "performance.information_ratio"),
            ("function jensensAlpha(", "performance.jensens_alpha"),
        ):
            assert fn in PERF_JS, f"缺少 {fn}"
            # 出处注记写在函数上方的 docblock 里，往前找 1200 字符足够
            i = PERF_JS.index(fn)
            head = PERF_JS[max(0, i - 1200):i]
            assert anchor in head, f"{fn} 未标注 Python 出处 {anchor}"

    def test_both_templates_load_the_shared_module(self):
        """job 与 symbol 两个模板都必须引入共享层，禁止各自复制一份公式。"""
        for name, tpl in (("job.html", JOB_TPL), ("symbol.html", SYMBOL_TPL)):
            assert "/static/perf-metrics.js" in tpl, f"{name} 未引入 perf-metrics.js"

    def test_templates_use_shared_helpers_not_inline_formulas(self):
        """模板里不得内联 Sharpe/β/IR 公式——只允许调 QREPerfMetrics。

        注意：`Math.sqrt(252)` 在 symbol.html 的 EWMA 年化波动里本就存在（既有验收
        行为，非本次引入），所以不断言全文无该串，只断言新增指标不得自己算。
        """
        for name, tpl in (("job.html", JOB_TPL), ("symbol.html", SYMBOL_TPL)):
            assert "QREPerfMetrics.riskAdjusted" in tpl, f"{name} 未调用 riskAdjusted"
            assert "QREPerfMetrics.avgHoldingDays" in tpl, f"{name} 未调用 avgHoldingDays"
        # 单笔持股周期列只有个股交易明细表有（策略页是聚合卡，不需要逐笔）
        assert "QREPerfMetrics.holdingDaysOf" in SYMBOL_TPL, "symbol.html 未调用 holdingDaysOf"
        # 四个指标的公式只准出现在共享层，模板里出现即为绕过
        for marker in (
            "function sharpe(", "function beta(", "function informationRatio(",
            "function jensensAlpha(",
        ):
            assert marker not in JOB_TPL, f"job.html 不得内联 {marker}"
            assert marker not in SYMBOL_TPL, f"symbol.html 不得内联 {marker}"


# ---------------------------------------------------------------- 渲染行为
def _render_fn(tpl: str, name: str) -> str:
    """从模板里抽出指定 render 函数体（含签名那一行到配对的右花括号）。"""
    m = re.search(rf"function {name}\(d\)\{{[\s\S]*?\n\}}", tpl)
    assert m, f"未找到 {name}"
    return m.group(0)


_RA_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const perfSrc = %PERF%;
const fnSrc = %FN%;
function makeEl(id){
  return {id, style: {}, _html: '', listeners: {},
    get innerHTML(){ return this._html; }, set innerHTML(v){ this._html = String(v); },
    classList: {add(){}, remove(){}, contains(){ return false; }}};
}
const els = {};
const document = { getElementById(id){ return els[id] || (els[id] = makeEl(id)); } };
// 浏览器同构：window 必须指向全局自身。否则 perf-metrics.js 里的
// `root.QREPerfMetrics = api` 只落在普通对象上，vm 内 `typeof QREPerfMetrics`
// 恒为 'undefined'，renderRiskAdjusted 会永远走隐藏分支（第一版就这么错的）。
const sandbox = {
  console, document,
  $(sel){ return document.getElementById(String(sel).replace(/^#/, '')); },
  // 模板同款最小 card/pct/cls（只服务于本测试的数值断言）
  card(label, value, klass, tip){
    return '<div class="metric-card" data-label="' + label + '" data-tip="' + (tip || '') + '">' +
           '<div class="m-value ' + (klass || '') + '">' + value + '</div></div>';
  },
  pct(v){ return v == null ? '—' : (Number(v) * 100).toFixed(2) + '%'; },
  cls(v){ return v == null ? 'flat' : (v > 0 ? 'pos' : (v < 0 ? 'neg' : 'flat')); },
  escH(s){ return String(s == null ? '' : s); },
};
sandbox.window = sandbox;
const context = vm.createContext(sandbox);
vm.runInContext(perfSrc, context);
vm.runInContext(fnSrc, context);
globalThis.els = els;
globalThis.ctx = context;
"""


def _run_ra(tpl: str, scenario: str) -> None:
    script = (
        _RA_HARNESS.replace("%PERF%", json.dumps(PERF_JS)).replace(
            "%FN%", json.dumps(_render_fn(tpl, "renderRiskAdjusted"))
        )
        + scenario
    )
    _node(script)


class TestRiskAdjustedRendering:
    """renderRiskAdjusted 的真实渲染行为（各 harness 都把它打桩了，必须单独覆盖）。"""

    def test_job_hides_strip_when_all_null(self):
        """三项全 null → 整块隐藏且清空，不留空壳。"""
        _run_ra(JOB_TPL, r"""
// 只有 1 个净值点 → 收益不足 2 个 → 全 null。元素由函数内部 getElementById 创建，
// 所以必须先调用再读 els（这也是本测试第一次踩过的坑：先读会拿到 undefined）。
ctx.renderRiskAdjusted({equity: [100], dates: ['2024-01-02'],
  benchmarks: {'000001.SH': {name: '上证指数', closes: [3000, 3010]}}});
const el = els['ra-strip'];
assert.ok(el, 'ra-strip 元素必须被创建');
assert.equal(el.style.display, 'none', '无数据必须隐藏');
assert.equal(el.innerHTML, '', '隐藏时必须清空，不留空壳');
// 无 benchmarks 键 → 同样隐藏
ctx.renderRiskAdjusted({equity: [100, 101, 102], dates: []});
assert.equal(el.style.display, 'none', '无基准必须隐藏');
console.log('ra-job-hide-ok');
""")

    def test_job_renders_three_cards_with_python_values(self):
        """有数据 → 显示 3 张卡，数值与 Python performance_summary 一致。"""
        _run_ra(JOB_TPL, r"""
const c = %CASE%;
ctx.renderRiskAdjusted({equity: c.equity, dates: c.dates,
  benchmarks: {'000300.SH': {name: '沪深300', closes: []},
               '000001.SH': {name: '上证指数', closes: c.bench_closes}}});
const el = els['ra-strip'];
assert.equal(el.style.display, '', '有数据必须显示');
assert.equal(el.innerHTML.indexOf('α（年化）') >= 0, true, '缺 α 卡');
assert.equal(el.innerHTML.indexOf('data-label="β"') >= 0, true, '缺 β 卡');
assert.equal(el.innerHTML.indexOf('信息比率') >= 0, true, '缺 IR 卡');
// β 卡数值
const betaCard = el.innerHTML.split('data-label="β"')[1].split('</div>')[0];
assert.equal(betaCard.indexOf(Number(c.beta).toFixed(2)) >= 0, true, 'β 数值不符: ' + betaCard);
// α 卡数值（pct 口径 = ×100 后两位小数）
const alphaCard = el.innerHTML.split('data-label="α（年化）"')[1].split('</div>')[0];
assert.equal(alphaCard.indexOf((c.alpha_annual * 100).toFixed(2)) >= 0, true, 'α 数值不符: ' + alphaCard);
// 跳过 closes 为空的基准，落到第二个
assert.equal(el.innerHTML.indexOf('上证指数') >= 0, true, '基准名必须来自第一个非空基准');
// tooltip 必须披露口径（基准名 + 曲线同源）
assert.equal(el.innerHTML.indexOf('与上方曲线同源') >= 0, true, '必须披露计算口径');
// 不得出现重复的夏普卡
assert.equal(el.innerHTML.indexOf('夏普') >= 0, false, 'Sharpe 已在指标条，不得重复');
console.log('ra-job-render-ok');
""".replace("%CASE%", json.dumps(_CASES["correlated"] | {"dates": []})))

    def test_symbol_uses_buy_hold_benchmark_from_kline(self):
        """symbol 版基准 = 买入持有该股，从 kline 收盘按 equity 日期对齐。"""
        _run_ra(SYMBOL_TPL, r"""
const c = %CASE%;
// 构造与 equity 等长的 kline：dates 用真实日期，ohlc[i][1] = bench_closes[i]
const dates = c.equity.map((_, i) => new Date(Date.UTC(2024, 0, 2 + i)).toISOString().slice(0, 10));
const ohlc = c.bench_closes.map(v => [v, v, v, v]);
ctx.renderRiskAdjusted({equity: {dates, values: c.equity}, kline: {dates, ohlc}});
const el = els['ra-strip'];
assert.equal(el.style.display, '', '有数据必须显示');
const betaCard = el.innerHTML.split('data-label="β"')[1].split('</div>')[0];
assert.equal(betaCard.indexOf(Number(c.beta).toFixed(2)) >= 0, true, 'β 数值不符: ' + betaCard);
assert.equal(el.innerHTML.indexOf('基准 = 区间内买入并持有该股') >= 0, true, '必须披露基准口径');
// 无 kline → 隐藏（不抛错）
ctx.renderRiskAdjusted({equity: {dates, values: c.equity}, kline: null});
assert.equal(el.style.display, 'none', '缺 kline 必须隐藏');
console.log('ra-symbol-ok');
""".replace("%CASE%", json.dumps(_CASES["correlated"])))


# ---------------------------------------------------------------- 小卡条样式契约
class TestMetricStripStyleContract:
    """QRE-SAAS-CARD-CLASS：小数据卡必须统一「白底磨砂玻璃」，数值色三分（中性紫/红/绿）。

    2026-10-29 用户定稿：取消所有紫底小卡；先改白底紫框，当日再修正为**白底磨砂
    玻璃**（与 .card / .chart-box 同一套玻璃 token）——这些小 div 本就是玻璃材质，
    之前只有 CSS 没跟上（card-fx.js 的 TILT_SEL 早就含 .metric-card）。
    中性数据（日期/暴露度/笔数/持股周期/β/磨损金额）紫字，盈亏数据红涨绿跌。

    历史坑（本类测试存在的原因）：
    · 2026-10-28 第一版只把六条指标条并进紫底名单，漏了交易磨损(.wear-cards)与
      风险分析(.risk-cards)，后者还吃着 lab-theme 的粉底粉框 → 白/紫/粉混搭；
    · 规则散在 base.html 内联 + lab-theme.css + 模板 ID 覆盖三处，改一处漏两处。
    现收敛到独立文件 static/card-class.css（在 lab/night 之后加载，同特异性后加载胜出），
    是这类卡的唯一权威。
    """

    BASE = (REPO / "src/quant_research_engine/gui/saas/templates/base.html").read_text(
        encoding="utf-8"
    )
    CARD_CSS = (REPO / "src/quant_research_engine/gui/static/card-class.css").read_text(
        encoding="utf-8"
    )
    # 详情页全部小卡容器（job/symbol 两页）
    ALL_STRIPS = ["#metric-strip", "#sum-strip", "#range-strip", "#ra-strip",
                  "#replay-metrics", "#kreplay-info"]

    def test_card_class_css_is_loaded_last(self):
        """card-class.css 必须在 lab-theme / night-mode 之后加载——
        同特异性下后加载才胜出，这是它能压住 lab-theme 粉底粉框的唯一原因。"""
        i_lab = self.BASE.index('href="/static/lab-theme.css')
        i_night = self.BASE.index('href="/static/night-mode.css')
        i_card = self.BASE.index('href="/static/card-class.css')
        assert i_lab < i_night < i_card, (
            "加载顺序必须是 lab-theme → night-mode → card-class"
        )

    def test_base_no_longer_overrides_card_background(self):
        """base.html 内联不得再写小卡的背景/边框/flex 规则——
        唯一权威在 card-class.css，留着会再次出现"改一处漏两处"。"""
        inline = self.BASE[self.BASE.index("<style>"):self.BASE.index("</style>")]
        # 只挑出「选择器里含 .metric-card」的规则——base 里 .sidenav/.wb-track 等
        # 非卡片元素本来就用 --tint，那些不在本类测试范围内。
        card_rules = [
            m.group(0)
            for m in re.finditer(r"[^{}]*\.metric-card[^{}]*\{[^}]*\}", inline)
        ]
        assert card_rules, "base 内联应保留 .metric-card 基类兜底"
        for rule in card_rules:
            assert "var(--tint" not in rule, (
                f"base 内联的 .metric-card 规则不得再用 --tint 紫底: {rule[:120]}"
            )
            assert not re.search(r"#[a-z-]+-strip \.metric-card", rule), (
                f"base 内联不得按小卡条 ID 覆盖样式: {rule[:120]}"
            )

    def test_all_cards_frosted_glass(self):
        """所有小卡（含磨损/风险）必须是白底磨砂玻璃——与 .card 家族同一套 token。

        用户 2026-10-29 定稿规格：半透明白色磨砂（blur(28px) saturate(140%)、
        白 45%–60% 透明度）、1px 半透明白描边、顶部内侧细高光、圆角 24px、
        大而柔的紫投影。
        """
        # 基类规则：用容器类选择器把特异性提到与 lab-theme 同级，靠后加载胜出
        assert ".metric-strip .metric-card," in self.CARD_CSS
        assert ".wear-cards .metric-card," in self.CARD_CSS
        assert ".risk-cards .metric-card," in self.CARD_CSS
        base_rule = re.search(
            r"\.metric-strip \.metric-card,\s*\n\.wear-cards \.metric-card,\s*\n"
            r"\.risk-cards \.metric-card,\s*\n\.metric-card \{([^}]*)\}",
            self.CARD_CSS,
        )
        assert base_rule, "未找到小卡基类规则（磨砂玻璃）"
        rule = base_rule.group(1)
        # 磨砂：backdrop-filter 两行（-webkit- 前缀 + 标准）
        assert "backdrop-filter: blur(28px) saturate(140%)" in rule, "缺 backdrop-filter"
        assert "-webkit-backdrop-filter: blur(28px) saturate(140%)" in rule, (
            "缺 -webkit- 前缀的 backdrop-filter"
        )
        # 半透明白底：必须拆成 background-color + background-image——
        # background 简写会重置 background-image，把 --glass-sheen 抹掉（踩过）
        assert "background: " not in rule, (
            "不得用 background 简写（会重置 background-image / 抹掉 glass-sheen）"
        )
        assert "background-color: var(--glass-bg)" in rule, "缺半透明玻璃底"
        assert "background-image: var(--glass-sheen)" in rule, "缺顶部受光 sheen"
        # 1px 半透明白描边
        assert "border: 1px solid var(--glass-line)" in rule, "缺 1px 半透明白描边"
        # 顶部内侧细高光 + 大而柔的紫投影
        assert "box-shadow: inset 0 1px 0 var(--glass-hi), var(--glass-shadow)" in rule, (
            "缺顶部细高光或紫投影"
        )
        # 圆角 24px
        assert "border-radius: var(--card-radius)" in rule, "缺 24px 圆角 token"
        assert "--card-radius:24px" in (
            REPO / "src/quant_research_engine/gui/static/lab-theme.css"
        ).read_text(encoding="utf-8"), "--card-radius 必须是 24px"
        # 磨损/风险条：lab-theme 的粉底粉框必须被显式收回玻璃
        override = re.search(
            r"\.wear-cards \.metric-card,\s*\n\.risk-cards \.metric-card \{([^}]*)\}",
            self.CARD_CSS,
        )
        assert override, "未找到磨损/风险条的收回规则"
        o = override.group(1)
        assert "background-color: var(--glass-bg)" in o, "磨损/风险条必须收回玻璃底"
        assert "border-color: var(--glass-line)" in o, "磨损/风险条必须收回白描边"
        assert "background: " not in o, "收回规则同样不得用 background 简写"

    def test_value_colors_neutral_purple_pnl_red_green(self):
        """数值色：中性默认 --lav-deep；盈亏 .pos 红 / .neg 绿（且必须提级压过基类）。"""
        assert ".metric-card .m-value {" in self.CARD_CSS
        assert "color: var(--lav-deep)" in self.CARD_CSS, "中性数值必须紫"
        # .pos/.neg 在 base 是 0,1,0，会被 0,2,0 的 .metric-card .m-value 压住，
        # 必须在 card-class.css 里用 0,3,0 显式提级
        assert ".metric-card .m-value.pos {" in self.CARD_CSS
        assert "color: var(--pos)" in self.CARD_CSS, "盈利必须红"
        assert ".metric-card .m-value.neg {" in self.CARD_CSS
        assert "color: var(--neg)" in self.CARD_CSS, "亏损必须绿"
        # 磨损条毛/净收益值同理（lab-theme 的 .wb-val 同特异性但先加载）
        assert ".wb-val.pos {" in self.CARD_CSS
        assert ".wb-val.neg {" in self.CARD_CSS

    def test_dense_strips_fit_seven_in_one_row(self):
        """密集条（7 卡左右）min 150px：容器拓宽到 1920px 后 7 卡一行余量充足。

        实测：job 页 .container 约 1000px，7×150+6×10=1110 放不下 → 6+1；
        7×130+6×10=970 放得下 → 一行并排。
        """
        m = re.search(
            r"#metric-strip \.metric-card,\s*\n#range-strip \.metric-card,\s*\n"
            r"#replay-metrics \.metric-card,\s*\n#kreplay-info \.metric-card \{([^}]*)\}",
            self.CARD_CSS,
        )
        assert m, "未找到密集条 flex 规则"
        basis = re.search(r"flex: 1 1 (\d+)px", m.group(1))
        assert basis, "密集条必须写 flex: 1 1 <N>px"
        assert int(basis.group(1)) == 150, (
            f"密集条 min 应为 150px（容器 1920），实际 {basis.group(1)}px"
        )

    def test_summary_and_ra_strips_use_wider_basis(self):
        """简介条与风险调整收益条卡少字号大，min 280px → 8 卡呈 4+4、3 卡撑满整行。

        CR-2026-10-29 C3.5：容器加宽到 1600px 后同步放大（250→280px，15→16.5px）。
        """
        m = re.search(r"#sum-strip \.metric-card,\s*\n#ra-strip \.metric-card \{([^}]*)\}",
                      self.CARD_CSS)
        assert m, "未找到简介/风险调整收益条规则"
        assert "flex: 1 1 280px" in m.group(1), "简介与 ra 条必须 min 280px（C3.5）"
        assert "font-size: 19.5px" in self.CARD_CSS, "两条的 m-value 必须 19.5px（UI-ROUND3 全站 +2）"
        assert "font-size: 21px" in self.CARD_CSS, "密集条 m-value 必须 21px（UI-ROUND3 全站 +2）"

    def test_no_leftover_grid_rules_for_these_strips(self):
        """旧的 grid-template-columns 规则必须删掉——flex 容器上它们是死代码，
        留着会误导后来者以为还在用 grid。"""
        for sid in self.ALL_STRIPS:
            assert f"{sid}{{grid-template-columns" not in self.CARD_CSS.replace(" ", ""), (
                f"{sid} 不得再写 grid-template-columns（已改 flex）"
            )

    def test_wear_renderers_do_not_force_inline_color(self):
        """两个模板的磨损卡渲染函数不得再用内联 style 强制颜色——
        内联样式压过一切 CSS，是"统一风格"最大的漏洞。"""
        for name in ("job", "symbol"):
            tpl = (REPO / f"src/quant_research_engine/gui/saas/templates/{name}.html").read_text(
                encoding="utf-8"
            )
            assert 'm-value flat" style="color:var(--lav-deep)"' not in tpl, (
                f"{name}.html 的磨损卡不得内联强制紫色"
            )
            # 毛/净收益必须按盈亏上色
            assert "wb-val ' + (" in tpl, f"{name}.html 磨损条盈亏值未上色"
