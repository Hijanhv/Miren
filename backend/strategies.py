"""The four regime strategies.

Each strategy works on daily OHLCV and is long-only: BUY opens a long, SELL
closes it. `signals()` is vectorised so the same code drives the live loop
(last value) and the historical replay (every value), which keeps the two from
drifting apart.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

from models import RegimeType, Signal, Strategy

BUY: Signal = "BUY"
SELL: Signal = "SELL"
HOLD: Signal = "HOLD"


class BaseStrategy(ABC):
    name: ClassVar[str]
    regime: ClassVar[RegimeType]
    description: ClassVar[str]
    # fraction of capital a new long uses
    allocation: ClassVar[float] = 1.0
    # max loss per trade as a fraction of entry price, None for no stop
    stop_loss: ClassVar[float | None] = None

    @property
    @abstractmethod
    def parameters(self) -> dict[str, float | int]: ...

    @property
    @abstractmethod
    def min_bars(self) -> int:
        """Bars needed before the first non-HOLD signal is possible."""

    @abstractmethod
    def signals(self, data: pd.DataFrame) -> pd.Series:
        """One signal per bar ("BUY", "SELL" or "HOLD"), using only data up to that bar."""

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if len(data) < self.min_bars:
            return HOLD
        last = self.signals(data).iloc[-1]
        return last if last in (BUY, SELL) else HOLD

    def describe(self) -> Strategy:
        params = dict(self.parameters)
        params["allocation"] = self.allocation
        if self.stop_loss is not None:
            params["stop_loss"] = self.stop_loss
        return Strategy(name=self.name, regime=self.regime, description=self.description, parameters=params)

    @staticmethod
    def _label(index: pd.Index, buy: pd.Series, sell: pd.Series) -> pd.Series:
        out = pd.Series(HOLD, index=index, dtype=object)
        out[buy.fillna(False).astype(bool)] = BUY
        # if both fire on one bar the exit wins, which is the safer reading
        out[sell.fillna(False).astype(bool)] = SELL
        return out


class TrendingStrategy(BaseStrategy):
    name = "EMA Crossover"
    regime = RegimeType.TRENDING
    description = (
        "Dual EMA crossover. Buys when EMA(fast) crosses above EMA(slow) and exits when it crosses "
        "back below. Rides strong directional moves."
    )
    allocation = 1.0

    def __init__(self, fast_ema: int = 20, slow_ema: int = 50) -> None:
        if fast_ema >= slow_ema:
            raise ValueError("fast_ema must be shorter than slow_ema")
        self.fast_ema, self.slow_ema = fast_ema, slow_ema

    @property
    def parameters(self) -> dict[str, float | int]:
        return {"fast_ema": self.fast_ema, "slow_ema": self.slow_ema}

    @property
    def min_bars(self) -> int:
        return self.slow_ema + 1

    def signals(self, data: pd.DataFrame) -> pd.Series:
        fast = EMAIndicator(data["close"], window=self.fast_ema).ema_indicator()
        slow = EMAIndicator(data["close"], window=self.slow_ema).ema_indicator()
        above = fast > slow
        prev = above.shift(1, fill_value=False)
        valid = slow.notna() & slow.shift(1).notna()
        return self._label(data.index, valid & above & ~prev, valid & ~above & prev)


class MeanReversionStrategy(BaseStrategy):
    name = "Bollinger Reversion"
    regime = RegimeType.MEAN_REVERTING
    description = (
        "Buys a close at or below the lower Bollinger Band when RSI confirms oversold, and exits at "
        "the upper band when RSI confirms overbought."
    )
    allocation = 0.75

    def __init__(self, bb_period: int = 20, bb_std: float = 2.0, rsi_buy: float = 35, rsi_sell: float = 65) -> None:
        self.bb_period, self.bb_std, self.rsi_buy, self.rsi_sell = bb_period, bb_std, rsi_buy, rsi_sell

    @property
    def parameters(self) -> dict[str, float | int]:
        return {"bb_period": self.bb_period, "bb_std": self.bb_std, "rsi_buy": self.rsi_buy, "rsi_sell": self.rsi_sell}

    @property
    def min_bars(self) -> int:
        return self.bb_period + 1

    def signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        bb = BollingerBands(close, window=self.bb_period, window_dev=self.bb_std)
        rsi = RSIIndicator(close, window=14).rsi()
        buy = (close <= bb.bollinger_lband()) & (rsi < self.rsi_buy)
        sell = (close >= bb.bollinger_hband()) & (rsi > self.rsi_sell)
        return self._label(data.index, buy, sell)


class VolatilityStrategy(BaseStrategy):
    name = "ATR Breakout"
    regime = RegimeType.VOLATILE
    description = (
        "Buys a close above the prior 20-day high plus 0.5x ATR and exits below the prior 20-day low "
        "minus 0.5x ATR. A 1% stop caps the loss on every trade."
    )
    allocation = 0.5
    stop_loss = 0.01

    def __init__(self, lookback: int = 20, atr_multiplier: float = 0.5) -> None:
        self.lookback, self.atr_multiplier = lookback, atr_multiplier

    @property
    def parameters(self) -> dict[str, float | int]:
        return {"lookback": self.lookback, "atr_multiplier": self.atr_multiplier}

    @property
    def min_bars(self) -> int:
        return self.lookback + 15

    def signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        atr = AverageTrueRange(data["high"], data["low"], close, window=14).average_true_range()
        # the channel uses the previous `lookback` bars so today's bar cannot define its own breakout level
        upper = data["high"].rolling(self.lookback).max().shift(1) + self.atr_multiplier * atr
        lower = data["low"].rolling(self.lookback).min().shift(1) - self.atr_multiplier * atr
        warm = pd.Series(range(len(data)), index=data.index) >= 14  # ta's ATR is 0 before its window fills
        return self._label(data.index, warm & (close > upper), warm & (close < lower))


class CalmStrategy(BaseStrategy):
    name = "SMA Carry"
    regime = RegimeType.CALM
    description = (
        "Small, low-frequency position. Buys dips more than 0.3% below the 10-day SMA and sells "
        "rallies more than 0.3% above it. Capital preservation first."
    )
    allocation = 0.25

    def __init__(self, sma_period: int = 10, threshold: float = 0.003) -> None:
        self.sma_period, self.threshold = sma_period, threshold

    @property
    def parameters(self) -> dict[str, float | int]:
        return {"sma_period": self.sma_period, "threshold": self.threshold}

    @property
    def min_bars(self) -> int:
        return self.sma_period

    def signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        sma = close.rolling(self.sma_period).mean()
        return self._label(data.index, close < sma * (1 - self.threshold), close > sma * (1 + self.threshold))
