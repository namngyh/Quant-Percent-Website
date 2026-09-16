"""Per-order paper leverage; isolated sessions, never the running account."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import routes_paper
from backend.paper.engine import PaperSession, OrderRefused
from backend.paper.manager import manager
from backend.strategy.engine import BacktestConfig
from backend.strategy.position_model import ContractConfig
import pandas as pd


def order(session, action, **kwargs):
    """Place a hand order and deliver the next bar, whose open fills it.

    Hand orders fill at the next bar's open (2026-09-16), so a test that wants
    the fill must hand the session that bar. Its open is the session's last
    price, which keeps every cost figure below measured at an unchanged price.
    A refusal at placement raises before any bar is delivered.
    """
    placed = session.place_order(action, now=0, **kwargs)
    bar_open = (session.last_bar_open + 60) * 1000
    price = session.last_price
    events = session.on_forming_candle(
        {"open_time": bar_open, "open": price, "high": price, "low": price, "close": price})
    return {"placed": placed, "events": events, "snapshot": session.snapshot()}


def session():
    return PaperSession('manual', 'BTCUSDT', '1m',
                        config=BacktestConfig(initial_capital=10000, size_pct=.5,
                                              leverage=1, fee=0, slippage=0), last_price=100)


def sizing_and_reversal():
    s = session()
    first = order(s, 'long', leverage=3)
    assert s.quantity == 150 and s.margin == 5000
    assert first['events'][0]['leverage'] == 3
    assert s.model.liquidation_price(100, 1) == 100 * (1 - 1 / 3)
    s.last_price = 110
    order(s, 'short', leverage=5)
    assert s.trades[0].pnl == 1500 and s.trades[0].leverage == 3
    assert abs(s.quantity + 11500 * .5 * 5 / 110) < 1e-9
    assert s.config.leverage == 5
    order(s, 'close', leverage=100)
    assert s.trades[-1].leverage == 5 and s.config.leverage == 5


def refusals_are_atomic():
    s = session(); order(s, 'long', leverage=3)
    before = s.snapshot()
    for leverage in [0, 126, float('nan'), float('inf')]:
        try: order(s, 'short', leverage=leverage)
        except OrderRefused as error: assert error.code == 'bad_leverage'
        else: raise AssertionError('invalid leverage accepted')
        assert s.snapshot() == before
    try: order(s, 'short', leverage=5, stop_loss=90)
    except OrderRefused: pass
    else: raise AssertionError('invalid short stop accepted')
    assert s.snapshot() == before


def contract_terms_are_not_overridden():
    s = session()
    s.config.contract = ContractConfig(multiplier=100000, initial_margin_rate=.2,
                                      maintenance_threshold=.5, fee_per_contract=20000)
    try: order(s, 'long', leverage=10)
    except OrderRefused as error: assert error.code == 'contract_leverage'
    else: raise AssertionError('contract margin silently changed')
    assert s.position == 0 and s.config.contract.initial_margin_rate == .2


def restart_keeps_selected_leverage():
    s = session(); order(s, 'long', leverage=7); order(s, 'short', leverage=2)
    with patch('backend.paper.manager.sources.get_candles', return_value=pd.DataFrame()):
        restored = manager._from_payload(manager._to_payload(s))
    assert restored.config.leverage == 2 and restored.quantity == s.quantity
    assert restored.trades[0].leverage == 7
    assert restored.model.liquidation_price(100, -1) == 150


def api_validates_and_forwards():
    app = FastAPI(); app.include_router(routes_paper.router)
    calls = []
    async def order(*args):
        calls.append(args)
        return {'snapshot': session().snapshot(), 'events': []}
    with patch.object(routes_paper.manager, 'order', side_effect=order):
        with TestClient(app) as client:
            response = client.post('/api/paper/test/order', json={'action': 'long', 'leverage': 8})
            assert response.status_code == 200 and calls[-1][-1] == 8
            for leverage in [0, 126, 'nan', 'inf']:
                assert client.post('/api/paper/test/order', json={'action': 'long', 'leverage': leverage}).status_code == 422
            assert len(calls) == 1


if __name__ == '__main__':
    tests = [sizing_and_reversal, refusals_are_atomic, contract_terms_are_not_overridden,
             restart_keeps_selected_leverage, api_validates_and_forwards]
    for test in tests:
        test(); print('PASS', test.__name__)
    print(f'{len(tests)} passed, 0 failed')
