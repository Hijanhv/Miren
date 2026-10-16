import numpy as np
import pandas as pd
import pytest

from models import RegimeType
from strategies import CalmStrategy, MeanReversionStrategy, TrendingStrategy, VolatilityStrategy
from strategy_router import all_strategies, get_strategy


def frame(close, spread=0.5):
    close = np.asarray(close, dtype=float)
    idx = pd.bdate_range("2024-01-01", periods=len(close))
    return pd.DataFrame(
        {"open": close, "high": close + spread, "low": close - spread, "close": close, "volume": 1e6}, index=idx
    )


def test_router_mapping():
    assert isinstance(get_strategy(RegimeType.TRENDING), TrendingStrategy)
    assert isinstance(get_strategy(RegimeType.MEAN_REVERTING), MeanReversionStrategy)
    assert isinstance(get_strategy(RegimeType.VOLATILE), VolatilityStrategy)
    assert isinstance(get_strategy(RegimeType.CALM), CalmStrategy)
    assert {s.regime for s in all_strategies()} == set(RegimeType)


def test_short_history_holds():
    for r in RegimeType:
        assert get_strategy(r).generate_signal(frame([100] * 5)) == "HOLD"


def test_ema_crossover_fires_once_on_the_cross():
    down = np.linspace(200, 100, 80)
    up = np.linspace(100, 200, 80)
    s = TrendingStrategy().signals(frame(np.concatenate([down, up])))
    buys = s[s == "BUY"]
    assert len(buys) == 1
    assert s.index.get_loc(buys.index[0]) > 80
    # a cross the other way gives one SELL
    s2 = TrendingStrategy().signals(frame(np.concatenate([up, down])))
    assert (s2 == "SELL").sum() == 1


def test_trending_rejects_bad_params():
    with pytest.raises(ValueError):
        TrendingStrategy(fast_ema=50, slow_ema=20)


def test_mean_reversion_buys_oversold_band_touch():
    close = [100 + np.sin(i / 3) for i in range(40)] + [100 - i * 1.5 for i in range(1, 8)]
    assert MeanReversionStrategy().generate_signal(frame(close)) == "BUY"
    close = [100 + np.sin(i / 3) for i in range(40)] + [100 + i * 1.5 for i in range(1, 8)]
    assert MeanReversionStrategy().generate_signal(frame(close)) == "SELL"


def test_atr_breakout():
    flat = [100 + (i % 2) * 0.2 for i in range(40)]
    assert VolatilityStrategy().generate_signal(frame(flat + [110])) == "BUY"
    assert VolatilityStrategy().generate_signal(frame(flat + [90])) == "SELL"
    assert VolatilityStrategy().generate_signal(frame(flat + [100.5])) == "HOLD"
    assert VolatilityStrategy.stop_loss == 0.01


def test_calm_sma_band():
    base = [100.0] * 15
    assert CalmStrategy().generate_signal(frame(base + [99.0])) == "BUY"
    assert CalmStrategy().generate_signal(frame(base + [101.0])) == "SELL"
    assert CalmStrategy().generate_signal(frame(base + [100.1])) == "HOLD"


def test_describe_includes_risk_params():
    d = VolatilityStrategy().describe()
    assert d.parameters["stop_loss"] == 0.01
    assert d.parameters["allocation"] == 0.5
