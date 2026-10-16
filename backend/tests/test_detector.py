import numpy as np

from feature_engine import FEATURE_COLUMNS, compute_raw_features, scale_features
from models import RegimeType
from regime_detector import RegimeDetector, assign_regimes
from replay import replay


def profile(**kw):
    return [kw.get(c, 0.0) for c in FEATURE_COLUMNS]


def test_assign_regimes_maps_obvious_profiles():
    profiles = np.array(
        [
            profile(realized_vol=2, atr_ratio=2),  # volatile
            profile(adx=1.5, autocorrelation=1.0),  # trending
            profile(realized_vol=-1, adx=-1, bb_width=-1),  # calm
            profile(autocorrelation=-1.5, adx=-0.2),  # mean reverting
        ]
    )
    m = assign_regimes(profiles)
    assert m == {
        0: RegimeType.VOLATILE,
        1: RegimeType.TRENDING,
        2: RegimeType.CALM,
        3: RegimeType.MEAN_REVERTING,
    }


def test_run_returns_regime_and_history(ohlcv):
    det = RegimeDetector().run(ohlcv, window=500)
    assert det.regime.type in RegimeType
    assert 0 <= det.regime.confidence <= 1
    assert len(det.history) == 500
    assert set(det.history["regime"]) <= {r.value for r in RegimeType}
    assert det.regime.features["as_of"] == det.history.index[-1].strftime("%Y-%m-%d")
    # each of the 4 hidden states gets a distinct label
    assert len(set(RegimeDetector().run(ohlcv).history["regime"])) >= 2


def test_filtered_history_does_not_use_future_rows(ohlcv):
    raw = compute_raw_features(ohlcv).tail(500)
    scaled, _ = scale_features(raw)
    d = RegimeDetector()
    d.fit(scaled)
    full = d.history(scaled)
    prefix = d.history(scaled.iloc[:300])
    assert (full["hmm_state"].iloc[:300].to_numpy() == prefix["hmm_state"].to_numpy()).all()
    assert np.allclose(full["confidence"].iloc[:300], prefix["confidence"])


def test_volatile_stretch_is_labelled_volatile(ohlcv):
    det = RegimeDetector().run(ohlcv, window=500)
    raw = det.raw
    top_vol_days = raw["realized_vol"].nlargest(40).index
    share = (det.history.loc[top_vol_days, "regime"] == RegimeType.VOLATILE.value).mean()
    assert share > 0.5


def test_replay_shapes(ohlcv):
    det = RegimeDetector().run(ohlcv, window=300)
    a = replay("SYN", det)
    assert len(a.timeline) == 300 == len(a.bars)
    assert a.timeline[0].pnl_pct == 0
    assert all(t.position in (0, 1) for t in a.timeline)
