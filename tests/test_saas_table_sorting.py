"""经典策略与个人中心回测记录的表头排序合同。"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = (ROOT / "src/quant_research_engine/gui/saas/templates/showcase.html").read_text(
    encoding="utf-8"
)
RECORDS_BODY = (
    ROOT / "src/quant_research_engine/gui/saas/templates/_records_body.html"
).read_text(encoding="utf-8")
RECORDS_SCRIPTS = (
    ROOT / "src/quant_research_engine/gui/saas/templates/_records_scripts.html"
).read_text(encoding="utf-8")
PROFILE_RECORDS = (
    ROOT / "src/quant_research_engine/gui/saas/templates/_profile_records.html"
).read_text(encoding="utf-8")


def test_showcase_all_data_columns_have_header_sort_controls():
    keys = re.findall(r'data-sc-sort="([^"]+)"', SHOWCASE)
    assert keys == [
        "title", "date_start", "total_return", "excess_return",
        "max_drawdown", "win_rate", "total_trade_count", "data_until",
    ]
    assert "scState.order = scState.order === 'desc' ? 'asc' : 'desc'" in SHOWCASE
    assert "scState.order = 'desc'" in SHOWCASE
    assert "slice().sort" in SHOWCASE
    assert "aria-sort" in SHOWCASE


def test_showcase_has_large_viewport_and_pagination():
    assert "max-height:720px" in SHOWCASE
    assert "pageSize: 20" in SHOWCASE
    assert "scState.page = 1" in SHOWCASE
    for element_id in ("sc-prev", "sc-next", "sc-pages", "sc-info"):
        assert f'id="{element_id}"' in SHOWCASE
    assert "slice(start, start + scState.pageSize)" in SHOWCASE


def test_records_sort_controls_live_in_jobs_table_header():
    header = re.search(r'<table class="tbl" id="jobs-table">(.*?)</thead>', RECORDS_BODY, re.S)
    assert header is not None
    keys = re.findall(r'data-sort="([^"]+)"', header.group(1))
    assert keys == ["excess_return", "created_at"]
    assert "创建时间 ▼" in header.group(1)
    assert "aria-sort" in RECORDS_SCRIPTS
    assert "listState.order = listState.order === 'desc' ? 'asc' : 'desc'" in RECORDS_SCRIPTS


def test_active_profile_records_template_has_same_header_controls():
    header = re.search(r'<table class="tbl" id="jobs-table">(.*?)</thead>', PROFILE_RECORDS, re.S)
    assert header is not None
    assert re.findall(r'data-sort="([^"]+)"', header.group(1)) == [
        "excess_return", "created_at",
    ]
    assert "创建时间 ▼" in header.group(1)
