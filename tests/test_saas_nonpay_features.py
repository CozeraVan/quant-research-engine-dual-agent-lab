from __future__ import annotations

from quant_research_engine.gui.saas import create_saas_app


def test_showcase_has_search_filter_compare_and_tracking():
    html = create_saas_app().test_client().get('/saas/showcase').data.decode()
    for marker in (
        'id="sc-search"', 'id="sc-filter"', 'id="sc-compare"',
        'id="sc-compare-modal"', 'data-sc-select', 'scVisibleItems',
        'tracking_days', '日更', 'renderCompare',
    ):
        assert marker in html, marker


def test_nl_quality_page_has_real_metric_containers():
    html = create_saas_app().test_client().get('/saas/nl-quality').data.decode()
    for marker in ('NL 编译质量', 'id="nq-total"', 'id="nq-daily"', 'id="nq-failures"'):
        assert marker in html, marker


def test_job_attribution_has_minimum_sample_filter():
    html = create_saas_app().test_client().get('/saas/jobs/1').data.decode()
    for marker in ('id="tag-min-samples"', 'tagMinSamples', 'tagSampleFiltered'):
        assert marker in html, marker


def test_job_has_json_csv_export_and_existing_share():
    html = create_saas_app().test_client().get('/saas/jobs/1').data.decode()
    for marker in ('id="btn-export-json"', 'id="btn-export-csv"', 'exportResultJson', 'exportResultCsv', 'btn-share'):
        assert marker in html, marker


def test_membership_has_launch_notification_for_free_users():
    html = create_saas_app().test_client().get('/saas/membership').data.decode()
    for marker in ('id="btn-member-notify"', '会员上线时通知我', 'membership/notify'):
        assert marker in html, marker


def test_single_full_backtest_product_preview_is_visible():
    html = create_saas_app().test_client().get('/saas/membership').data.decode()
    for marker in ('单次全期全量回测', '9.9元', '单次购买', '不限股票数·不限周期', '不参与', 'member-single-run'):
        assert marker in html, marker


def test_console_displays_single_run_credit_counts():
    html = create_saas_app().test_client().get('/saas/console').data.decode()
    for marker in ('单次回测可用', '单次回测已核销', 'single_run_active', 'single_run_consumed'):
        assert marker in html, marker


def test_lab_result_does_not_require_pandas_on_ecs_import():
    from pathlib import Path
    source = Path('src/quant_research_engine/gui/lab_result.py').read_text()
    assert '\nimport pandas as pd\n' not in source
    assert '    import pandas as pd\n' in source
