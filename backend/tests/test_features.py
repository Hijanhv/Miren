import numpy as np
import pandas as pd
import pytest

import feature_engine
from feature_engine import FEATURE_COLUMNS, MarketDataError, compute_raw_features, extract_features


def test_columns_and_no_nans(ohlcv):
    raw = compute_raw_features(ohlcv)
    assert list(raw.columns) == FEATURE_COLUMNS
    assert not raw.isna().any().any()
    assert (raw["realized_vol"] > 0).all()
    assert raw["autocorrelation"].between(-1, 1).all()


def test_features_do_not_look_ahead(ohlcv):
    full = compute_raw_features(ohlcv)
    cut = compute_raw_features(ohlcv.iloc[:400])
    common = cut.index
    pd.testing.assert_frame_equal(full.loc[common], cut, check_exact=False, rtol=1e-9)


def test_zero_volume_index_is_handled(ohlcv):
    ohlcv = ohlcv.assign(volume=0.0)
    raw = compute_raw_features(ohlcv)
    assert (raw["volume_ratio"] == 1.0).all()


async def test_extract_features_scaled(monkeypatch, ohlcv):
    async def fake(symbol, bars):
        return ohlcv

    monkeypatch.setattr(feature_engine, "fetch_ohlcv", fake)
    df = await extract_features("X.NS", window=60)
    assert len(df) == 60
    assert np.allclose(df.mean(), 0, atol=1e-9)
    assert df.attrs["raw"].shape == df.shape


def test_bad_symbol_raises(monkeypatch):
    def boom(*a, **k):
        return pd.DataFrame()

    monkeypatch.setattr(feature_engine.yf, "download", boom)
    with pytest.raises(MarketDataError):
        feature_engine._download("NOPE.NS", pd.Timestamp("2024-01-01").to_pydatetime())


def test_yfinance_exception_becomes_market_data_error(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("offline")

    monkeypatch.setattr(feature_engine.yf, "download", boom)
    with pytest.raises(MarketDataError, match="offline"):
        feature_engine._download("X.NS", pd.Timestamp("2024-01-01").to_pydatetime())
