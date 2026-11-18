"""2026-11-04 个人中心与个股详情 UI 改版的聚焦回归。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "src/quant_research_engine/gui/static"
TEMPLATES = REPO / "src/quant_research_engine/gui/saas/templates"


def _node(source: str, script: str) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不可用")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write("const vm = require('node:vm');\nconst assert = require('node:assert/strict');\n")
        fh.write("const context = {console, window: {}}; vm.createContext(context);\n")
        fh.write("vm.runInContext(" + json.dumps(source) + ", context);\n")
        fh.write(script)
        path = fh.name
    try:
        result = subprocess.run([node, path], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout
    finally:
        os.unlink(path)


def test_stress_table_and_reference_card_render_real_fields() -> None:
    source = (STATIC / "risk-stress.js").read_text(encoding="utf-8")
    _node(source, r"""
const D = context.window.QRESymbolDetail;
const pct = v => v == null ? '—' : (Number(v) * 100).toFixed(2) + '%';
const cls = v => v > 0 ? 'pos' : (v < 0 ? 'neg' : 'flat');
const stress = {
  scenarios: {
    crash: {description: '历史下跌', window: {start: '2015-06-01', end: '2015-06-30'},
            strategy_cumulative_return: -0.12, strategy_peak_trough_drawdown: 0.20, var: 0.02},
    old: {description: '更早窗口', error: 'no strategy observations'},
  },
  var_es_reference: {confidence: 0.99, method: 'ewma_parametric', var: 0.021, es: 0.033,
                     note: '当前 1 日参照'},
};
const table = D.stressTable(stress, pct, cls);
assert.match(table, /risk-stress-table/);
assert.match(table, /历史下跌/);
assert.match(table, /-12\.00%/);
assert.match(table, /-20\.00%/);
assert.match(table, /2\.00%/);
assert.match(table, /未覆盖窗口：更早窗口/);
const ref = D.varEsReference(stress, pct);
assert.match(ref, /99% VaR \/ ES/);
assert.match(ref, /2\.10% \/ 3\.30%/);
assert.match(ref, /tip-trigger/);
assert.match(ref, /metric-card risk-reference-card/);
assert.doesNotMatch(ref, /metric-strip/, '参考卡不得独占一条指标行');
assert.equal(D.varEsReference({}, pct), '');
""")


def test_stress_empty_state_is_explicit() -> None:
    source = (STATIC / "risk-stress.js").read_text(encoding="utf-8")
    _node(source, r"""
const D = context.window.QRESymbolDetail;
const html = D.stressTable({scenarios: {old: {description: '窗口外', error: '无交易'}}});
assert.match(html, /压力测试暂无可用情景/);
assert.match(html, /窗口外/);
assert.doesNotMatch(html, /<table/);
""")


def test_order_markers_aggregate_and_refresh_with_zoom() -> None:
    source = (STATIC / "kline-order-markers.js").read_text(encoding="utf-8")
    _node(source, r"""
const series = [];
let zoomHandler = null;
let redraws = 0;
const markerUpdates = [];
const chart = {
  getOption: () => ({dataZoom: [{start: 0, end: 100}]}),
  getWidth: () => 100,
  on: (name, fn) => { if (name === 'dataZoom') zoomHandler = fn; },
  setOption: option => { markerUpdates.push(option); },
};
const dates = ['2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04', '2026-01-05'];
const detail = {
  kline: {ohlc: [[9, 10, 8, 11], [10, 11, 9, 12], [11, 12, 10, 13],
                 [12, 13, 11, 14], [13, 14, 12, 15]]},
  orders: [
    {side: 'buy', trade_date: dates[0], quantity: 100, price: 10, notional: 1000, cost: 5},
    {side: 'buy', trade_date: dates[1], quantity: 200, price: 11, notional: 2200, cost: 5},
    {side: 'sell', trade_date: dates[4], quantity: 300, price: 14, notional: 4200, cost: 6},
  ],
};
const markers = context.window.QREKlineOrderMarkers.attach(
  chart, series, detail, dates, () => { redraws += 1; });
assert.equal(series.length, 2);
assert.equal(markers.buy.data.length, 1, '默认全窗口下两个买点应聚合');
assert.equal(markers.buy.data[0].text, '买2');
assert.equal(markers.buy.data[0].value[1], 8);
assert.equal(markers.sell.data[0].value[1], 15);
assert.match(markers.buy.data[0].summary, /300 股/);
assert.equal(typeof zoomHandler, 'function');
zoomHandler();
assert.equal(redraws, 0, '缩放不得触发全量序列 replaceMerge');
assert.equal(markerUpdates.length, 1);
assert.deepEqual(Array.from(markerUpdates[0].series, s => s.id),
                 ['qre-order-markers-buy', 'qre-order-markers-sell']);
""")


def test_profile_center_preserves_background_refresh_fix() -> None:
    profile = (TEMPLATES / "profile.html").read_text(encoding="utf-8")
    records = (TEMPLATES / "_records_scripts.html").read_text(encoding="utf-8")
    css = (STATIC / "account.css").read_text(encoding="utf-8")
    assert '{% include "_membership_benefits.html" %}' not in profile
    assert profile.count('data-profile-view="') == 5  # 记录/分享/MCP/会员/账号
    assert "/api/saas/membership" in profile
    assert "let recordsHasLoadedOnce = false;" in records
    assert "recordsHasLoadedOnce = true;" in records
    assert "if (recordsHasLoadedOnce)" in records
    assert ".profile-list-card" in css
    for fixed_height in ("height: 540px", "height: 500px", "height: 460px"):
        assert fixed_height not in css
