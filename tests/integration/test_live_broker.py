"""Optional READ-ONLY official PAPER account verification; no submitted orders."""

import os

import pytest

from quantlab.execution.authority import Authority
from quantlab.execution.broker import AlpacaPaperBroker


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("QUANTLAB_LIVE_BROKER") != "1", reason="opt-in read-only PAPER account verification"
)
def test_official_paper_account_read_only():
    names = (
        "QUANTLAB_ALPACA_PAPER_KEY",
        "QUANTLAB_ALPACA_PAPER_SECRET",
        "QUANTLAB_PAPER_ACCOUNT_ID",
        "QUANTLAB_SANDBOX_AUTHORIZATION_KEY",
    )
    if not all(os.getenv(k) for k in names):
        pytest.skip("Separate PAPER credentials/account/private authorization key unavailable")
    authority = Authority(
        os.environ["QUANTLAB_SANDBOX_AUTHORIZATION_KEY"].encode(),
        mode="BROKER_SANDBOX",
        account_id=os.environ["QUANTLAB_PAPER_ACCOUNT_ID"],
    )
    broker = AlpacaPaperBroker(authority)
    try:
        assert broker.account()["id"] == authority.account_id
        assert isinstance(broker.positions(), list)
        assert isinstance(broker.open_orders(), list)
    finally:
        broker.close()
