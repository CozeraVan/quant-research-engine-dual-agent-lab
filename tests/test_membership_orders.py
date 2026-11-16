import pytest

from quant_research_engine.gui.saas.orders import simulate_order, transition_order


def test_membership_order_happy_path():
    assert simulate_order(['submit', 'pay', 'fulfill']) == 'fulfilled'


def test_membership_order_refund_path():
    assert simulate_order(['submit', 'pay', 'fulfill', 'refund', 'refund_complete']) == 'refunded'


def test_order_rejects_unpaid_or_duplicate_fulfillment():
    with pytest.raises(ValueError):
        transition_order('pending', 'fulfill')
    with pytest.raises(ValueError):
        transition_order('fulfilled', 'fulfill')
    with pytest.raises(ValueError):
        transition_order('refunded', 'pay')
