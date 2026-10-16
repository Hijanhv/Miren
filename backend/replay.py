"""Day-by-day replay of the regime-switching system over a detector window.

Rules, identical to the live executor:
- the strategy for a day is the one routed from that day's regime;
- a regime change closes any open position at that day's close;
- signals act at the close of the bar that produced them, so a position opened
  on day t earns the return of day t+1 onwards;
- longs only, sized by the strategy's allocation; the volatility stop is
  checked against each close.
"""

from __future__ import annotations

from models import Bar, RegimeAnalysis, RegimeType, TimelineDay
from regime_detector import Detection
from strategy_router import get_strategy


def replay(symbol: str, det: Detection) -> RegimeAnalysis:
    ohlcv = det.ohlcv
    strategies = {r: get_strategy(r) for r in RegimeType}
    # each signal series only looks backwards, so computing it once on the full frame is safe
    signals = {r: s.signals(ohlcv) for r, s in strategies.items()}
    closes = ohlcv["close"]

    position, alloc, entry = 0, 0.0, 0.0
    prev_regime: RegimeType | None = None
    prev_close: float | None = None
    equity = 1.0
    days: list[TimelineDay] = []

    for ts, row in det.history.iterrows():
        close = float(closes.loc[ts])
        regime = RegimeType(row["regime"])
        strat = strategies[regime]

        day_ret = position * alloc * (close / prev_close - 1) if prev_close else 0.0
        equity *= 1 + day_ret

        if prev_regime is not None and regime != prev_regime:
            position = 0
        if position and strat.stop_loss is not None and close <= entry * (1 - strat.stop_loss):
            position = 0
        sig = signals[regime].loc[ts]
        if sig == "BUY" and not position:
            position, alloc, entry = 1, strat.allocation, close
        elif sig == "SELL" and position:
            position = 0

        days.append(
            TimelineDay(
                date=ts.date(),
                close=round(close, 2),
                regime=regime,
                confidence=round(float(row["confidence"]), 4),
                strategy=strat.name,
                position=position,
                pnl_pct=round(day_ret * 100, 4) + 0.0,  # + 0.0 turns -0.0 into 0.0
            )
        )
        prev_regime, prev_close = regime, close

    first = float(closes.loc[det.history.index[0]])
    last = float(closes.loc[det.history.index[-1]])
    start = det.history.index[0]
    bars = [
        Bar(date=ts.date(), open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
        for ts, r in ohlcv.loc[start:].iterrows()
    ]
    return RegimeAnalysis(
        symbol=symbol,
        bars=bars,
        timeline=days,
        current=det.regime,
        replay_return_pct=round((equity - 1) * 100, 2),
        buy_hold_return_pct=round((last / first - 1) * 100, 2),
        note=(
            "Replay labels each day with forward-filtered HMM probabilities (no future bars), "
            "but the HMM parameters were fit on this whole window. Treat it as an illustration, "
            "not a backtest. No costs or slippage."
        ),
    )
