"""QRE-SAAS-CLASSIC-ACTIONS-UI：经典策略 CTA 与结果操作卡合并。

覆盖（先 RED 后 GREEN）：
- showcase.html：页头灰字备注 / #sc-hint / 底部灰字长文与弱链接删除，改为
  「复现经典策略」tip + 「新建同款策略」主按钮；策略 subtitle 内容保留。
- job.html：#box-actions 与 #box-share 合并进 #result-actions-card「结果操作」卡；
  原 ID / 权限 / 事件绑定 / API 不变；改动区域无 .opt 灰色备注；信号面板风险提示
  移入问号提示；新增空安全 syncResultActionCard()。
- lab-theme.css：仅新增局部规则（.result-action-* / .showcase-cta），按钮 ≥44px，
  不新增灰色小字备注样式。
- Node harness：外层卡可见性矩阵（保存+信号+分享 / 仅分享 / 游客 / 只读）、
  连续初始化与失败重试不重复绑定、syncResultActionCard 空安全。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src/quant_research_engine/gui/saas/templates"


def _template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def _css() -> str:
    return (ROOT / "src/quant_research_engine/gui/static/lab-theme.css").read_text(encoding="utf-8")


def _node():
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        import pytest

        pytest.skip("node 不可用")
    return node


def _run_node(script: str) -> None:
    result = subprocess.run([_node(), "-e", script], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr or result.stdout


def _job_actions_source(html: str) -> str:
    """job.html 主脚本段：poll/initResultActions/initShareButton/syncResultActionCard。"""
    match = re.search(
        r"(const ACTIVE =[\s\S]*?async function initResultActions[\s\S]*?\n\})(?=\n\nif \(new URLSearchParams)",
        html, re.S)
    assert match, "未找到 job.html 结果操作脚本段"
    return match.group(1)


# ---------------------------------------------------------------- 静态断言：showcase
class TestShowcaseCta:
    def test_header_gray_note_moved_to_tip(self):
        page = _template("showcase.html")
        # 页头第二行 .opt 备注删除，信息移入 H1 旁问号提示
        assert '<p style="font-size:13px"><span class="opt">只读展示' not in page
        assert 'data-tip="只读展示 · 数据每日收盘后更新 · 过往表现不构成投资建议。"' in page
        # 主描述保留
        assert "经典量化策略在全 A 股、全历史区间的真实回测成绩" in page

    def test_sc_hint_removed(self):
        page = _template("showcase.html")
        assert 'id="sc-hint"' not in page
        assert "点击任意策略查看完整回测详情" not in page
        assert "getElementById('sc-hint')" not in page

    def test_bottom_card_is_primary_cta(self):
        page = _template("showcase.html")
        assert "如何复现这些策略？" not in page
        assert "立即试试" not in page
        assert "以上策略均可用「新建策略」页的入口自由复现" not in page
        # 精简 CTA：标题 + 问号提示 + 主按钮（链接仍为 /saas/new）
        assert "复现经典策略" in page
        assert 'class="card showcase-cta"' in page
        assert 'class="btn btn-primary"' in page
        assert "新建同款策略" in page
        assert 'href="/saas/new"' in page
        assert 'class="tip-trigger"' in page
        assert page.count('data-tip=') >= 2

    def test_subtitle_content_preserved(self):
        page = _template("showcase.html")
        # 策略自身 subtitle 是内容而非备注：渲染逻辑保留
        assert "it.subtitle" in page
        # 全页仅剩 subtitle 一处 .opt（策略内容），不再有备注性灰字
        assert page.count('class="opt"') == 1


# ---------------------------------------------------------------- 静态断言：job
class TestResultActionsCard:
    def test_outer_card_wraps_both_groups(self):
        html = _template("job.html")
        assert 'class="chart-box hidden" id="result-actions-card"' in html
        assert "结果操作" in html
        i_outer = html.index('id="result-actions-card"')
        i_actions = html.index('id="box-actions"')
        i_share = html.index('id="box-share"')
        i_download = html.index('id="download-card"')
        assert i_outer < i_actions < i_share < i_download, "两组必须在外层卡内"
        # 原两个独立标题删除，外层一个问号提示承载说明
        assert 'chart-title">下一步' not in html
        assert 'chart-title">分享结果' not in html
        assert 'id="result-actions-card"' in html and 'class="tip-trigger"' in html

    def test_original_ids_and_contracts_preserved(self):
        html = _template("job.html")
        for marker in (
            'id="box-actions"', 'id="btn-save-lib"', 'id="btn-signal-open"',
            'id="btn-signal-confirm"', 'id="action-status"', 'id="signal-panel"',
            'id="sig-sector-row"', 'id="sig-univ-group"', 'id="sig-univ-key"',
            'name="sig-scope" value="last_run_universe"', 'name="sig-scope" value="sector"',
            'name="sig-scope" value="all_a"',
            'id="box-share"', 'id="btn-share"', 'id="share-status"',
            'id="share-modal"', 'id="share-modal-yes"', 'id="share-link-modal"',
            'id="share-link-input"', 'id="btn-copy-share"', 'id="share-link-done"',
            # API 与事件契约不变
            "/api/saas/strategies/' + sid + '/save'",
            "/api/saas/strategies/' + sid + '/watch'",
            "shareUrl('/api/saas/jobs/' + JOB_ID + '/share-links')",
            "function initResultActions(jobData, chart)",
            "function initShareButton(data)",
            "dataset.actionsBound",
            "dataset.shareBound",
        ):
            assert marker in html, marker

    def test_button_hierarchy(self):
        html = _template("job.html")
        assert 'class="btn btn-primary" id="btn-save-lib"' in html
        assert 'class="btn btn-ghost" id="btn-signal-open"' in html
        assert 'class="btn btn-ghost" id="btn-share"' in html
        assert 'class="btn btn-primary" id="btn-signal-confirm"' in html
        assert "background:var(--accent)" not in html
        assert 'class="result-action-buttons"' in html
        assert 'class="result-action-status" id="action-status"' in html
        assert 'class="result-action-status" id="share-status"' in html

    def test_changed_region_has_no_gray_notes(self):
        html = _template("job.html")
        region = html[html.index('id="result-actions-card"'):html.index('id="download-card"')]
        assert 'class="opt"' not in region
        assert "--faint" not in region
        assert "font-size:12" not in region
        # 信号面板风险提示移入问号提示，radio/select/scope 值不变
        panel = region[region.index('id="signal-panel"'):]
        assert 'data-tip="T+1 参考' in panel
        assert 'class="tip-trigger"' in panel
        assert "扫描范围" in panel

    def test_sync_result_action_card_contract(self):
        html = _template("job.html")
        assert "function syncResultActionCard()" in html
        actions_src = re.search(
            r"async function initResultActions\(jobData, chart\)\{[\s\S]*?\n\}",
            html).group(0)
        share_src = re.search(
            r"function initShareButton\(data\)\{[\s\S]*?\n\}", html).group(0)
        # 每个显示/隐藏分支结束后都同步外层
        assert actions_src.count("syncResultActionCard()") >= 4
        assert share_src.count("syncResultActionCard()") >= 4
        # 只读分支连外层卡一起隐藏
        assert "'box-actions', 'download-card', 'guest-result-note', 'guest-note', " \
               "'box-share', 'guest-strip', 'result-actions-card'" in html

    def test_lab_theme_local_rules_only(self):
        css = _css()
        for selector in (".result-action-group", ".result-action-buttons",
                         ".result-action-status", ".showcase-cta"):
            assert selector + "{" in css or selector + " {" in css, selector
        block = css[css.index("QRE-SAAS-CLASSIC-ACTIONS-UI"):]
        assert "min-height:44px" in block
        assert "--faint" not in block, "不得新增灰色小字备注样式"
        assert ".btn-sm" not in block, "不得改动全站 .btn-sm"


# ---------------------------------------------------------------- Node：可见性矩阵
_JOB_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function el(){
  const e = {
    children: [], childNodes: [], style: {}, className: '', textContent: '', innerHTML: '',
    disabled: false, dataset: {}, listeners: {}, classes: new Set(), value: '', checked: false,
    appendChild(...nodes){ this.children.push(...nodes); this.childNodes.push(...nodes); return nodes[nodes.length - 1]; },
    replaceChildren(...nodes){ this.children = [...nodes]; this.childNodes = [...nodes]; },
    addEventListener(type, fn){ (this.listeners[type] ||= []).push(fn); },
    setAttribute(name, value){ this[name] = String(value); },
    removeAttribute(name){ delete this[name]; },
    querySelectorAll(){ return []; },
  };
  e.classList = {
    add(c){ e.classes.add(c); },
    remove(c){ e.classes.delete(c); },
    toggle(c, on){ if (on === undefined) on = !e.classes.has(c); if (on) e.classes.add(c); else e.classes.delete(c); },
    contains(c){ return e.classes.has(c); },
  };
  return e;
}
function response(status, data){
  return {status, ok: status >= 200 && status < 300, json: async () => data};
}
function createHarness(options){
  const opts = options || {};
  // 与 job.html 静态 class 一致：两组与外层卡初始均为 hidden
  const initialClasses = {'box-actions': ['hidden'], 'box-share': ['hidden'], 'result-actions-card': ['hidden']};
  const elements = new Proxy({}, {get(obj, key){
    if (!obj[key]){
      obj[key] = el();
      (initialClasses[key] || []).forEach(c => obj[key].classes.add(c));
    }
    return obj[key];
  }});
  const calls = {requests: [], failure: 0, access: 0};
  const timers = new Map();
  const windowListeners = {};
  let nextTimer = 1;
  let now = 1000;
  const root = el();
  root.childNodes = [el()];
  const document = {
    querySelector(selector){
      if (selector === '.container') return root;
      if (selector === '.container .card') return root.children[root.children.length - 1];
      if (selector.startsWith('input[name=sig-scope]:checked')) return Object.assign(el(), {value: 'last_run_universe'});
      return null;
    },
    querySelectorAll(){ return []; },
    getElementById(id){ return elements[id]; },
    createElement(){ return el(); },
  };
  const window = {addEventListener(type, fn){ (windowListeners[type] ||= []).push(fn); }};
  const context = vm.createContext({
    console, document, window, JOB_ID: 1, STATUS_LABEL: {}, SAAS_BYPASS: !!opts.bypass,
    AbortController, MAX_ACTIVE_WAIT_MS: 300000,
    Date: {now(){ return now; }},
    location: {search: opts.search || ''}, URLSearchParams,
    requestAnimationFrame(fn){ return fn(); },
    saasToken(){ return opts.token === undefined ? 'token' : opts.token; },
    apiFetch(url, options){ calls.requests.push({url, options}); return opts.fetch(url, options); },
    showAccessFallback(target){ calls.access += 1; target.replaceChildren(el()); },
    showLoadFailure(target, retry){ calls.failure += 1; calls.retry = retry; target.replaceChildren(el()); },
    setTimeout(fn, delay){ const id = nextTimer++; timers.set(id, {fn, at: now + delay}); return id; },
    clearTimeout(id){ timers.delete(id); },
    renderMeta(){}, renderStrategyInfo(){}, renderMetrics(){}, renderMain(){}, empty(){},
    renderContract(){}, initReplay(){}, renderFees(){}, loadRisk(){}, renderRisk(){},
    renderAttribution(){}, mountReplay(){ return {destroy(){}}; },
  });
  return {context, calls, elements, timers, windowListeners};
}
"""


class TestResultActionsVisibilityMatrix:
    def _run(self, scenario: str):
        html = _template("job.html")
        source = _job_actions_source(html)
        script = _JOB_HARNESS + "\nconst source = " + json.dumps(source) + ";\n" + scenario
        _run_node(script)

    def test_visibility_matrix_and_single_binding(self):
        self._run(r"""
function successFetch(url){
  if (url.includes('/summary')) return response(200, {ok: true, strategy_id: 7, summary: {}});
  if (url.includes('/chart-data')) return response(200, {ok: true, dates: ['2026-01-01'], equity: [1]});
  if (url.includes('/tag-analysis')) return response(404, {ok: false});
  if (url.endsWith('/api/saas/strategies/7')) return response(200, {ok: true, strategy: {in_library: false}});
  if (url.endsWith('/api/saas/universes')) return response(200, {ok: true, groups: []});
  return response(200, {ok: true});
}
function hidden(h, id){ return h.elements[id].classes.has('hidden'); }
function clicks(h, id){ return (h.elements[id].listeners.click || []).length; }
(async () => {
  // 保存 + 信号 + 分享：两组可见 → 外层可见；连续初始化不重复绑定
  const full = createHarness({fetch: successFetch});
  vm.runInContext(source, full.context);
  await vm.runInContext('poll()', full.context);
  assert.ok(!hidden(full, 'box-actions'), '登录完成后保存/信号组必须可见');
  assert.ok(!hidden(full, 'box-share'), '登录完成后分享组必须可见');
  assert.ok(!hidden(full, 'result-actions-card'), '任一组可见时外层必须可见');
  await vm.runInContext('poll()', full.context);
  for (const id of ['btn-save-lib', 'btn-signal-open', 'btn-signal-confirm', 'btn-share'])
    assert.equal(clicks(full, id), 1, id + ' 连续初始化不得重复绑定');
  assert.ok(!hidden(full, 'result-actions-card'), '连续初始化后外层仍可见');

  // 仅分享（job 无 strategy_id）：保存/信号组隐藏，外层仍可见
  const shareOnly = createHarness({fetch: url => url.includes('/summary')
    ? response(200, {ok: true, summary: {}}) : successFetch(url)});
  vm.runInContext(source, shareOnly.context);
  await vm.runInContext('poll()', shareOnly.context);
  assert.ok(hidden(shareOnly, 'box-actions'), '无 strategy_id 不显示保存/信号组');
  assert.ok(!hidden(shareOnly, 'box-share'), '仅分享形态分享组必须可见');
  assert.ok(!hidden(shareOnly, 'result-actions-card'), '仅分享时外层必须可见');

  // 游客：两组皆隐藏 → 外层隐藏
  const guest = createHarness({fetch: successFetch, token: ''});
  vm.runInContext(source, guest.context);
  await vm.runInContext('poll()', guest.context);
  assert.ok(hidden(guest, 'box-actions'), '游客不得显示保存/信号组');
  assert.ok(hidden(guest, 'box-share'), '游客不得显示分享组');
  assert.ok(hidden(guest, 'result-actions-card'), '游客必须整体隐藏结果操作卡');

  // 只读（showcase/分享视图）：两组皆隐藏 → 外层隐藏
  const readonly = createHarness({fetch: url => url.includes('/summary')
    ? response(200, {ok: true, readonly: true, readonly_kind: 'showcase', strategy_id: 7, summary: {}})
    : successFetch(url)});
  vm.runInContext(source, readonly.context);
  await vm.runInContext('poll()', readonly.context);
  assert.ok(hidden(readonly, 'box-actions'), '只读不得显示保存/信号组');
  assert.ok(hidden(readonly, 'box-share'), '只读不得显示分享组');
  assert.ok(hidden(readonly, 'result-actions-card'), '只读必须整体隐藏结果操作卡');

  // 失败后重试：不重复绑定、外层状态恢复
  let failed = true;
  const retry = createHarness({fetch: url => (failed && url.includes('/chart-data'))
    ? response(500, {ok: false}) : successFetch(url)});
  vm.runInContext(source, retry.context);
  await vm.runInContext('poll()', retry.context);
  failed = false;
  await retry.calls.retry();
  for (const id of ['btn-save-lib', 'btn-signal-open', 'btn-signal-confirm', 'btn-share'])
    assert.equal(clicks(retry, id), 1, id + ' 失败后重试不得重复绑定');
  assert.ok(!hidden(retry, 'result-actions-card'), '重试成功后外层必须可见');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_sync_result_action_card_null_safe(self):
        html = _template("job.html")
        fn = re.search(r"function syncResultActionCard\(\)\{[\s\S]*?\n\}", html)
        assert fn, "未找到 syncResultActionCard 定义"
        self._run_null_safe(fn.group(0))

    def _run_null_safe(self, fn_source: str):
        script = (
            "const assert = require('node:assert/strict');\n"
            "const vm = require('node:vm');\n"
            "const document = {getElementById(){ return null; }};\n"
            "const context = vm.createContext({document});\n"
            "const source = " + json.dumps(fn_source) + ";\n"
            "vm.runInContext(source, context);\n"
            "vm.runInContext('syncResultActionCard()', context);\n"
            "assert.ok(true, '元素缺失时不得抛错');\n"
        )
        _run_node(script)
