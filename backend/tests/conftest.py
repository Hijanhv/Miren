import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_ohlcv(n: int = 700, seed: int = 7) -> pd.DataFrame:
    """Synthetic daily bars that cycle through calm, trending, choppy and volatile stretches."""
    rng = np.random.default_rng(seed)
    rets = []
    phases = [(0.0002, 0.004, 0.0), (0.002, 0.008, 0.3), (0.0, 0.01, -0.4), (0.0, 0.03, 0.0)]
    while len(rets) < n:
        drift, vol, ac = phases[len(rets) // 60 % len(phases)]
        prev = 0.0
        for _ in range(60):
            r = drift + ac * prev + rng.normal(0, vol)
            rets.append(r)
            prev = r
    close = 1000 * np.exp(np.cumsum(rets[:n]))
    spread = np.abs(rng.normal(0, 0.006, n)) * close
    idx = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.002, n)),
            "high": close + spread,
            "low": close - spread,
            "close": close,
            "volume": rng.integers(1_000_000, 3_000_000, n).astype(float),
        },
        index=idx,
    )


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    return make_ohlcv()
