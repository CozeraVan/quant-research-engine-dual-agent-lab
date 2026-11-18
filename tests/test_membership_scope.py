from quant_research_engine.gui.saas.membership import quota_pool, validate_scope_policy


def test_large_scale_pool_covers_full_minus_one_and_random_cap():
    assert quota_pool({'all_market': True}) == 'large'
    assert quota_pool({'universe': {'key': 'x'}}) == 'large'
    assert quota_pool({'random_n': 2000}) == 'large'
    assert quota_pool({'codes': ['x'] * 4000}, available_symbols=5000) == 'large'
    assert quota_pool({'codes': ['x'] * 3999}, available_symbols=5000) == 'small'
    assert quota_pool({'random_n': 1999}) == 'small'


def test_scope_policy_applies_to_direct_params_not_only_ui():
    policy = {'max_codes': 10, 'max_days': 3650}
    assert validate_scope_policy({'random_n': 2001}, policy, logged_in=True) is not None
    assert validate_scope_policy({'codes': ['x'] * 11}, policy, logged_in=True) is not None
    assert validate_scope_policy({'universe': {'key': 'x'}}, policy, logged_in=True) is not None
    assert validate_scope_policy({'start': '2000-01-01', 'end': '2026-01-01'}, policy, logged_in=True) is not None
    assert validate_scope_policy({'random_n': 10, 'start': '2025-01-01', 'end': '2025-12-31'}, policy, logged_in=True) is None


def test_admin_scope_display_uses_execution_constants():
    from pathlib import Path
    app = Path('src/quant_research_engine/gui/saas/app.py').read_text(encoding='utf-8')
    console = Path('src/quant_research_engine/gui/saas/templates/console.html').read_text(encoding='utf-8')
    assert 'membership.MAX_RANDOM_UNIVERSE' in app
    assert 'membership.LARGE_SCALE_COVERAGE' in app
    assert 'renderScopePolicy(d.scope_policy' in console


def test_paid_membership_expires_to_member():
    from datetime import datetime, timedelta, timezone
    from quant_research_engine.gui.saas.membership import effective_tier
    now = datetime.now(timezone.utc)
    assert effective_tier('starter', now + timedelta(seconds=1), now=now) == 'starter'
    assert effective_tier('starter', now, now=now) == 'member'
    assert effective_tier('paid', None, now=now) == 'paid'
