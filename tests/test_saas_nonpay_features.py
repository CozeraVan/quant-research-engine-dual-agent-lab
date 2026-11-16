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
