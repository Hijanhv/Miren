"""Regime classification with a Gaussian HMM and a KMeans cross-check.

How a hidden state becomes a regime label:
the HMM is fit on standardised features, so each state's mean vector is a
z-score profile (for example "ADX +1.2, autocorrelation +0.6"). Each of the
four regimes has a scoring rule over that profile, and the 4 states are
assigned to the 4 regimes by the permutation with the highest total score.
KMeans centroids are labelled with the same rule, which gives an independent
second opinion on the latest bar.

The current state comes from filtered (forward-only) probabilities, so the
label of any day only uses bars up to that day. The model parameters are still
fit on the whole window, which the replay note states.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import os
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from scipy.special import logsumexp
from scipy.stats import multivariate_normal
from sklearn.cluster import KMeans

from feature_engine import FEATURE_COLUMNS, MarketDataError, compute_raw_features, fetch_ohlcv, scale_features
from models import Regime, RegimeType

log = logging.getLogger("miren.detector")

# a 4-state full-covariance HMM over 7 features has ~150 free parameters, so it needs
# a few hundred daily rows; 60 rows (the feature_engine default) is too few to fit
DEFAULT_WINDOW = int(os.getenv("MIREN_DETECT_WINDOW", "500"))
MIN_ROWS = 120

REGIME_ORDER = [RegimeType.TRENDING, RegimeType.MEAN_REVERTING, RegimeType.VOLATILE, RegimeType.CALM]


def regime_score(profile: dict[str, float], regime: RegimeType) -> float:
    """How well a z-score feature profile matches a regime. Higher is better."""
    adx, ac = profile["adx"], profile["autocorrelation"]
    vol, atr, bbw = profile["realized_vol"], profile["atr_ratio"], profile["bb_width"]
    if regime is RegimeType.TRENDING:
        return adx + ac
    if regime is RegimeType.MEAN_REVERTING:
        return -ac - adx
    if regime is RegimeType.VOLATILE:
        return vol + atr
    return -vol - adx - bbw  # CALM


def assign_regimes(profiles: np.ndarray) -> dict[int, RegimeType]:
    """Assigns each of the 4 state (or cluster) profiles a distinct regime, maximising total score."""
    n = len(profiles)
    if n != len(REGIME_ORDER):
        raise ValueError(f"expected {len(REGIME_ORDER)} profiles, got {n}")
    named = [dict(zip(FEATURE_COLUMNS, map(float, p))) for p in profiles]
    scores = np.array([[regime_score(p, r) for r in REGIME_ORDER] for p in named])
    best = max(itertools.permutations(range(n)), key=lambda perm: sum(scores[s, perm[s]] for s in range(n)))
    return {s: REGIME_ORDER[best[s]] for s in range(n)}


@dataclass
class Detection:
    """Everything one detector run produced."""

    regime: Regime
    ohlcv: pd.DataFrame
    raw: pd.DataFrame
    # one row per feature date: regime and kmeans_regime (RegimeType values as plain strings, since
    # pandas does not compare str-Enum members reliably), confidence (filtered posterior), hmm_state
    history: pd.DataFrame


class RegimeDetector:
    def __init__(self, n_regimes: int = 4, random_state: int = 42) -> None:
        if n_regimes != 4:
            raise ValueError("Miren labels exactly 4 regimes")
        self.n_regimes = n_regimes
        self.random_state = random_state
        self.hmm = self._new_hmm("full")
        self.kmeans = KMeans(n_clusters=n_regimes, n_init=10, random_state=random_state)
        self.state_map: dict[int, RegimeType] = {}
        self.cluster_map: dict[int, RegimeType] = {}

    def _new_hmm(self, covariance_type: str) -> GaussianHMM:
        return GaussianHMM(
            n_components=self.n_regimes,
            covariance_type=covariance_type,
            n_iter=100,
            min_covar=1e-3,
            random_state=self.random_state,
        )

    def fit(self, features: pd.DataFrame) -> None:
        if len(features) < MIN_ROWS:
            raise MarketDataError(f"need at least {MIN_ROWS} feature rows to fit the HMM, got {len(features)}")
        x = features[FEATURE_COLUMNS].to_numpy()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # hmmlearn warns on every non-converged EM run
            try:
                self.hmm = self._new_hmm("full")
                self.hmm.fit(x)
                self._filtered(x)  # fails fast if a covariance came out singular
            except (ValueError, np.linalg.LinAlgError) as exc:
                log.warning("full-covariance HMM failed (%s); falling back to diagonal", exc)
                self.hmm = self._new_hmm("diag")
                self.hmm.fit(x)
        self.kmeans.fit(x)
        self.state_map = assign_regimes(self.hmm.means_)
        self.cluster_map = assign_regimes(self.kmeans.cluster_centers_)

    def _filtered(self, x: np.ndarray) -> np.ndarray:
        """P(state_t | x_1..x_t) for every t, via the forward algorithm (no future data)."""
        k = self.n_regimes
        log_b = np.column_stack(
            [multivariate_normal.logpdf(x, self.hmm.means_[s], self.hmm.covars_[s], allow_singular=False) for s in range(k)]
        )
        log_a = np.log(np.maximum(self.hmm.transmat_, 1e-300))
        log_alpha = np.log(np.maximum(self.hmm.startprob_, 1e-300)) + log_b[0]
        out = np.empty((len(x), k))
        out[0] = np.exp(log_alpha - logsumexp(log_alpha))
        for t in range(1, len(x)):
            log_alpha = logsumexp(log_alpha[:, None] + log_a, axis=0) + log_b[t]
            log_alpha -= logsumexp(log_alpha)
            out[t] = np.exp(log_alpha)
        return out

    def history(self, features: pd.DataFrame) -> pd.DataFrame:
        x = features[FEATURE_COLUMNS].to_numpy()
        post = self._filtered(x)
        states = post.argmax(axis=1)
        clusters = self.kmeans.predict(x)
        return pd.DataFrame(
            {
                "hmm_state": states,
                "regime": [self.state_map[int(s)].value for s in states],
                "confidence": post[np.arange(len(x)), states],
                "kmeans_regime": [self.cluster_map[int(c)].value for c in clusters],
            },
            index=features.index,
        )

    def predict(self, features: pd.DataFrame, raw: pd.DataFrame | None = None) -> Regime:
        hist = self.history(features)
        last = hist.iloc[-1]
        regime = RegimeType(last["regime"])
        kmeans_regime = RegimeType(last["kmeans_regime"])
        values = (raw if raw is not None else features).iloc[-1]
        feats: dict[str, int | float | str | bool | None] = {c: round(float(values[c]), 6) for c in FEATURE_COLUMNS}
        feats.update(
            {
                "hmm_state": int(last["hmm_state"]),
                "kmeans_regime": kmeans_regime.value,
                "models_agree": bool(kmeans_regime == regime),
                "covariance_type": str(self.hmm.covariance_type),
                "window_rows": len(features),
                "as_of": features.index[-1].strftime("%Y-%m-%d"),
            }
        )
        return Regime(
            type=regime,
            confidence=round(float(last["confidence"]), 4),
            detected_at=datetime.now(timezone.utc),
            features=feats,
        )

    def run(self, ohlcv: pd.DataFrame, window: int = DEFAULT_WINDOW) -> Detection:
        """Synchronous pipeline on already-downloaded bars: features, fit, predict."""
        raw = compute_raw_features(ohlcv).tail(window)
        scaled, _ = scale_features(raw)
        self.fit(scaled)
        regime = self.predict(scaled, raw)
        return Detection(regime=regime, ohlcv=ohlcv, raw=raw, history=self.history(scaled))

    async def analyze(self, symbol: str, window: int = DEFAULT_WINDOW) -> Detection:
        ohlcv = await fetch_ohlcv(symbol, window)
        return await asyncio.to_thread(self.run, ohlcv, window)

    async def detect(self, symbol: str) -> Regime:
        """Full pipeline: extract, fit, predict."""
        return (await self.analyze(symbol)).regime
