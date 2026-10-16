from datetime import datetime, timezone

import pandas as pd
import pytest

from dhan_client import DhanError
from executor import MirenExecutor
from feature_engine import MarketDataError
from models import EventKind, Regime, RegimeType
from regime_detector import Detection


def bars(closes):
    idx = pd.bdate_range("2024-01-01", periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c + 0.5, "low": c - 0.5, "close": c, "volume": 1e6})


class FakeDetector:
    """Hands out a scripted list of (regime, confidence, closes)."""

    def __init__(self, script):
        self.script = list(script)

    async def analyze(self, symbol):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        regime, conf, closes = item
        r = Regime(type=regime, confidence=conf, detected_at=datetime.now(timezone.utc), features={})
        return Detection(regime=r, ohlcv=bars(closes), raw=pd.DataFrame(), history=pd.DataFrame())


CALM_BUY = [100.0] * 15 + [99.0]  # CalmStrategy BUY
CALM_FLAT = [100.0] * 15 + [100.1]  # HOLD
ATR_FLAT = [100 + (i % 2) * 0.2 for i in range(40)]


def make(script, **kw):
    return MirenExecutor("TEST.NS", 100_000, "PAPER", detector=FakeDetector(script), **kw)


async def test_initial_regime_and_paper_buy():
    ex = make([(RegimeType.CALM, 0.9, CALM_BUY)])
    await ex.tick()
    st = await ex.get_status()
    assert st.active_regime == RegimeType.CALM
    assert st.active_strategy == "SMA Carry"
    assert st.position_qty == int(100_000 * 0.25 // 99.0)
    assert st.total_trades == 1
    assert ex.events[0].kind == EventKind.ORDER
    assert ex.events[1].message.startswith("INITIAL REGIME: CALM")


async def test_regime_switch_flattens_and_reports_pnl_impact():
    ex = make([(RegimeType.CALM, 0.9, CALM_BUY), (RegimeType.VOLATILE, 0.95, ATR_FLAT[:-1] + [101.0])])
    await ex.tick()
    qty = ex.position_qty
    await ex.tick()
    st = await ex.get_status()
    assert st.regime_switches == 1
    assert st.active_strategy == "ATR Breakout"
    assert st.realized_pnl == pytest.approx((101.0 - 99.0) * qty)
    switch = next(e for e in ex.events if e.kind == EventKind.REGIME_CHANGE and "→" in e.message)
    assert "CALM → VOLATILE" in switch.message
    assert "P&L impact of SMA Carry: +" in switch.message
    assert [h.regime for h in ex.get_regime_history()] == [RegimeType.CALM, RegimeType.VOLATILE]


async def test_low_confidence_change_is_held():
    ex = make([(RegimeType.CALM, 0.9, CALM_FLAT), (RegimeType.TRENDING, 0.4, CALM_FLAT)])
    await ex.tick()
    await ex.tick()
    st = await ex.get_status()
    assert st.active_regime == RegimeType.CALM
    assert st.regime_switches == 0
    assert ex.events[0].kind == EventKind.REGIME_HELD


async def test_volatility_stop_loss():
    up = ATR_FLAT + [110.0]  # breakout BUY at 110
    ex = make([(RegimeType.VOLATILE, 0.9, up), (RegimeType.VOLATILE, 0.9, up + [108.5])])
    await ex.tick()
    assert ex.position_qty > 0
    await ex.tick()
    assert ex.position_qty == 0
    assert any(e.kind == EventKind.STOP_LOSS for e in ex.events)
    assert ex.realized < 0


async def test_market_data_error_keeps_running():
    ex = make([MarketDataError("no data"), (RegimeType.CALM, 0.9, CALM_FLAT)])
    await ex.tick()
    assert ex.state.status == "ERROR"
    await ex.tick()
    assert ex.state.status == "RUNNING"
    assert ex.state.error is None


async def test_start_stop_loop():
    ex = make([(RegimeType.CALM, 0.9, CALM_FLAT)] * 3, tick_seconds=60)
    await ex.start()
    assert ex.running
    for _ in range(50):
        if ex.state.status == "RUNNING":
            break
        import asyncio

        await asyncio.sleep(0.01)
    await ex.stop()
    assert not ex.running
    assert ex.state.status == "STOPPED"
    assert ex.events[0].kind == EventKind.STOP


async def test_live_requires_security_id():
    with pytest.raises(ValueError):
        MirenExecutor("X.NS", 1000, "LIVE")


class FakeDhan:
    def __init__(self, fail=False):
        self.fail = fail
        self.orders = []

    def place_order(self, security_id, action, qty, order_type, segment, product, price, tag):
        if self.fail:
            raise DhanError("order rejected: RMS")
        self.orders.append((security_id, action.value, qty, order_type, segment, product))
        return {"orderId": f"o{len(self.orders)}", "orderStatus": "TRANSIT"}

    def settle(self, order_id):
        return "TRADED", 99.5, self.orders[-1][2]


async def test_live_uses_dhan_fill_price():
    dhan = FakeDhan()
    ex = MirenExecutor(
        "X.NS", 100_000, "LIVE", dhan_client=dhan, security_id="2885",
        detector=FakeDetector([(RegimeType.CALM, 0.9, CALM_BUY)]),
    )
    await ex.tick()
    assert dhan.orders[0][:2] == ("2885", "BUY")
    assert ex.avg_price == 99.5
    assert ex.trades[0].order_id == "o1"


async def test_live_rejection_leaves_position_flat():
    ex = MirenExecutor(
        "X.NS", 100_000, "LIVE", dhan_client=FakeDhan(fail=True), security_id="2885",
        detector=FakeDetector([(RegimeType.CALM, 0.9, CALM_BUY)]),
    )
    await ex.tick()
    assert ex.position_qty == 0
    assert ex.events[0].kind == EventKind.ERROR
