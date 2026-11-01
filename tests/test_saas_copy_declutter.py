"""P1-9 文案精简化收尾：静态灰色备注不得常驻，必要说明进 tip-trigger。

第一段锁定三处高频静态备注：
- `symbols.html` 的“点列头排序……”灰字段 → 并入 H1 问号提示；
- `new.html` 的“没思路？点一个示例填入——”灰字标签 → 删除（示例按钮自解释）；
- `new.html` 的“没有你要的因子？……”灰字段落 → 保留链接，但不再使用 `.opt` 灰字包装。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src" / "quant_research_engine" / "gui" / "saas" / "templates"


def _read(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def test_symbols_page_sorting_note_moved_to_tip() -> None:
    page = _read("symbols.html")
    assert '<p class="opt" style="margin-top:6px">点列头排序，点行进详情；输入完整代码回车直跳。</p>' not in page
    assert '点列头排序' in page
    assert 'data-tip=' in page


def test_new_page_example_hint_removed() -> None:
    page = _read("new.html")
    assert '<span class="opt">没思路？点一个示例填入：</span>' not in page


def test_new_page_factor_request_link_not_gray_wrapper() -> None:
    page = _read("new.html")
    assert '<p class="opt" style="margin-top:14px"><a class="inl" href="/saas/factor-request">没有你要的因子？点此申请新因子 →</a></p>' not in page
    assert 'href="/saas/factor-request"' in page


def test_job_page_brief_line_is_not_gray_small() -> None:
    page = _read("job.html")
    assert 'color:#888' not in page
    assert 'font-size:14px;color:#888' not in page
    assert 'id="brief-text"' in page


def test_strategy_page_recompile_note_moved_to_tip() -> None:
    page = _read("strategy.html")
    assert '<p class="opt" style="margin:6px 0">重新编译后，需保存修改才会生效。</p>' not in page
    assert '重新编译后，需保存修改才会生效。' in page
    assert 'class="tip-trigger"' in page


def test_new_page_modal_and_pipeline_hints_not_gray() -> None:
    page = _read("new.html")
    assert '<p class="opt">你可以：' not in page
    assert 'id="factor-modal-status" class="opt"' not in page
    assert "'<br><span class=\"opt\">已停留在当前步骤，修正后重新运行。</span>'" not in page
    assert "'<br><span class=\"opt\">未提交全量回测；可前往任务页查看后台进度，或修正后重新运行。</span>'" not in page


def test_job_page_dynamic_content_not_gray_wrapper() -> None:
    page = _read("job.html")
    assert "'<div class=\"opt\" style=\"font-size:14px;margin-bottom:16px\">'" not in page
    assert "'<div class=\"opt\" style=\"padding:2px 0\">'" not in page
    assert "'<div class=\"opt\" style=\"color:var(--faint)\">— 组间 '" not in page
    assert "'<div class=\"opt\" style=\"white-space:pre-wrap;color:var(--ink)\">'" not in page
    assert '<p class="opt" style="margin:0 0 16px">（快速向导入口；无条件快照，显示最终 YAML）</p>' not in page
