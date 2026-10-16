"""Market data download and feature extraction.

Every feature is computed from daily OHLCV bars using only data up to and
including that bar, so a feature row never looks into the future.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.preprocessing import StandardScaler
from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.momentum import RSIIndicator

log = logging.getLogger("miren.features")

FEATURE_COLUMNS = [
    "realized_vol",
    "autocorrelation",
    "adx",
    "atr_ratio",
    "bb_width",
    "rsi",
    "volume_ratio",
]

VOL_WINDOW = 20
AUTOCORR_WINDOW = 10
ADX_PERIOD = 14
ATR_PERIOD = 14
BB_PERIOD = 20
RSI_PERIOD = 14
VOLUME_WINDOW = 20
# ADX needs about 2x its period before it settles, so the first bars are dropped
WARMUP_BARS = 2 * ADX_PERIOD + 2


class MarketDataError(Exception):
    """Raised when a symbol has no usable data (unknown ticker, delisted, network failure)."""


def _download(symbol: str, start: datetime) -> pd.DataFrame:
    try:
        df = yf.download(
            symbol,
            start=start.strftime("%Y-%m-%d"),
            interval="1d",
            progress=False,
            auto_adjust=True,
            multi_level_index=False,
            threads=False,
        )
    except Exception as exc:  # yfinance raises many different types on network and parse errors
        raise MarketDataError(f"yfinance failed for {symbol}: {exc}") from exc
    if df is None or df.empty:
        raise MarketDataError(f"No data for {symbol}. Check the ticker (NSE stocks end in .NS, e.g. RELIANCE.NS)")
    df = df.rename(columns=str.lower)
    missing = {"open", "high", "low", "close", "volume"} - set(df.columns)
    if missing:
        raise MarketDataError(f"{symbol}: yfinance response is missing columns {sorted(missing)}")
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df = df[df["close"] > 0].dropna(subset=["open", "high", "low", "close"])
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df[~df.index.duplicated(keep="last")]


async def fetch_ohlcv(symbol: str, bars: int) -> pd.DataFrame:
    """Downloads at least `bars` daily candles plus the warmup the indicators need."""
    # about 250 trading days per 365 calendar days, plus slack for holidays
    calendar_days = math.ceil((bars + WARMUP_BARS + VOLUME_WINDOW) * 365 / 245) + 10
    start = datetime.now() - timedelta(days=calendar_days)
    return await asyncio.to_thread(_download, symbol, start)


def compute_raw_features(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Raw, unscaled features, one row per bar after the warmup."""
    close, high, low, volume = ohlcv["close"], ohlcv["high"], ohlcv["low"], ohlcv["volume"]
    log_ret = np.log(close).diff()

    out = pd.DataFrame(index=ohlcv.index)
    out["realized_vol"] = log_ret.rolling(VOL_WINDOW).std() * math.sqrt(252)
    # lag-1 autocorrelation of returns over a short window: > 0.1 persistent (trend), < -0.1 reverting
    out["autocorrelation"] = log_ret.rolling(AUTOCORR_WINDOW).corr(log_ret.shift(1))
    out["adx"] = ADXIndicator(high, low, close, window=ADX_PERIOD).adx()
    out["atr_ratio"] = AverageTrueRange(high, low, close, window=ATR_PERIOD).average_true_range() / close
    bb = BollingerBands(close, window=BB_PERIOD, window_dev=2)
    out["bb_width"] = (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg()
    out["rsi"] = RSIIndicator(close, window=RSI_PERIOD).rsi()
    avg_volume = volume.rolling(VOLUME_WINDOW).mean()
    # indices like ^NSEI report zero volume; a ratio of 1 then carries no information, which is correct
    out["volume_ratio"] = (volume / avg_volume.replace(0, np.nan)).fillna(1.0)

    # a flat return window gives an undefined correlation; treat it as no autocorrelation
    out["autocorrelation"] = out["autocorrelation"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    out = out.iloc[WARMUP_BARS:].replace([np.inf, -np.inf], np.nan).dropna()
    return out[FEATURE_COLUMNS]


def scale_features(raw: pd.DataFrame) -> tuple[pd.DataFrame, StandardScaler]:
    scaler = StandardScaler()
    scaled = pd.DataFrame(scaler.fit_transform(raw.values), index=raw.index, columns=raw.columns)
    return scaled, scaler


async def extract_features(symbol: str, window: int = 60) -> pd.DataFrame:
    """Last `window` bars of features, scaled with StandardScaler.

    The raw values and the OHLCV they came from are attached as
    `df.attrs["raw"]` and `df.attrs["ohlcv"]` so callers can explain a regime
    in real units.
    """
    ohlcv = await fetch_ohlcv(symbol, window)
    raw = compute_raw_features(ohlcv).tail(window)
    if raw.empty:
        raise MarketDataError(f"{symbol}: not enough history to compute features")
    scaled, _ = scale_features(raw)
    scaled.attrs["raw"] = raw
    scaled.attrs["ohlcv"] = ohlcv
    return scaled
