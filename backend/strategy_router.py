"""Maps a detected regime to the strategy that trades it."""

from __future__ import annotations

from models import RegimeType, Strategy
from strategies import BaseStrategy, CalmStrategy, MeanReversionStrategy, TrendingStrategy, VolatilityStrategy

_ROUTES: dict[RegimeType, type[BaseStrategy]] = {
    RegimeType.TRENDING: TrendingStrategy,
    RegimeType.MEAN_REVERTING: MeanReversionStrategy,
    RegimeType.VOLATILE: VolatilityStrategy,
    RegimeType.CALM: CalmStrategy,
}


def get_strategy(regime: RegimeType) -> BaseStrategy:
    """A fresh instance of the strategy for `regime`, with default parameters."""
    return _ROUTES[regime]()


def all_strategies() -> list[Strategy]:
    return [cls().describe() for cls in _ROUTES.values()]
