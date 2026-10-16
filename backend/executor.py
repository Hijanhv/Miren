"""The autonomous loop: detect regime, route strategy, act on its signal, repeat."""

from __future__ import annotations

import asyncio
import logging
import math
import os
from collections import deque
from datetime import datetime, timedelta, timezone

import pandas as pd

from dhan_client import DhanClient, DhanError
from feature_engine import MarketDataError
from models import (
    Action,
    Event,
    EventKind,
    ExecutorStatus,
    Mode,
    Regime,
    RegimeHistory,
    RegimeType,
    SignalRecord,
    StrategyView,
    Trade,
)
from regime_detector import RegimeDetector
from strategies import BaseStrategy
from strategy_router import get_strategy

log = logging.getLogger("miren.executor")

TICK_SECONDS = float(os.getenv("MIREN_TICK_SECONDS", "300"))
# a regime change below this HMM confidence is logged but does not switch strategy
MIN_SWITCH_CONFIDENCE = float(os.getenv("MIREN_MIN_SWITCH_CONFIDENCE", "0.6"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pct(v: float) -> str:
    return f"{v:+.2f}%"


class MirenExecutor:
    def __init__(
        self,
        symbol: str,
        capital: float,
        mode: Mode = "PAPER",
        dhan_client: DhanClient | None = None,
        security_id: str | None = None,
        detector: RegimeDetector | None = None,
        tick_seconds: float = TICK_SECONDS,
        min_switch_confidence: float = MIN_SWITCH_CONFIDENCE,
    ) -> None:
        if mode == "LIVE" and (dhan_client is None or not security_id):
            raise ValueError("LIVE mode needs a configured Dhan client and the instrument's security_id")
        self.symbol = symbol
        self.capital = float(capital)
        self.mode: Mode = mode
        self.dhan = dhan_client
        self.security_id = security_id
        self.detector = detector or RegimeDetector()
        self.tick_seconds = tick_seconds
        self.min_switch_confidence = min_switch_confidence

        self.state = ExecutorStatus(symbol=symbol, mode=mode, capital=self.capital)
        self.regime: Regime | None = None
        self.strategy: BaseStrategy | None = None
        self.position_qty = 0
        self.avg_price = 0.0
        self.realized = 0.0
        self.last_price: float | None = None
        self.stint_start_equity = 0.0  # P&L when the active strategy took over

        self.trades: list[Trade] = []
        self.history: list[RegimeHistory] = []
        self.events: deque[Event] = deque(maxlen=300)
        self.signals: deque[SignalRecord] = deque(maxlen=50)
        self.equity_marks: list[tuple[datetime, float]] = []

        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()

    # lifecycle

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Starts the background loop and returns immediately."""
        if self.running:
            return
        self._stop.clear()
        self.state.status = "DETECTING"
        self.state.started_at = _now()
        self.state.error = None
        self._event(
            EventKind.START,
            f"Started {self.mode} on {self.symbol} with capital {self.capital:,.0f}. "
            f"Detecting every {self.tick_seconds:g}s.",
        )
        self._task = asyncio.create_task(self._loop(), name=f"miren-{self.symbol}")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self.state.status != "STOPPED":
            self.state.status = "STOPPED"
            self.state.next_tick_at = None
            pos = f" Open position kept: {self.position_qty} @ {self.avg_price:.2f}." if self.position_qty else ""
            self._event(EventKind.STOP, f"Stopped. P&L {self._total_pnl():+,.2f}.{pos}")

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # one bad tick must not kill an autonomous loop
                log.exception("tick failed")
                self.state.error = str(exc)
                self._event(EventKind.ERROR, f"Tick failed: {exc}")
            self.state.next_tick_at = _now() + timedelta(seconds=self.tick_seconds)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick_seconds)
            except asyncio.TimeoutError:
                pass

    # one cycle

    async def tick(self) -> None:
        async with self._lock:
            try:
                det = await self.detector.analyze(self.symbol)
            except MarketDataError as exc:
                self.state.error = str(exc)
                self._event(EventKind.ERROR, f"Market data: {exc}. Retrying next tick.")
                if self.regime is None:
                    self.state.status = "ERROR"
                return

            self.state.error = None
            self.state.status = "RUNNING"
            self.state.last_tick_at = _now()
            regime = det.regime
            self.regime = regime
            price = float(det.ohlcv["close"].iloc[-1])
            self.last_price = price

            await self._route(regime, price)
            assert self.strategy is not None
            self.history.append(
                RegimeHistory(
                    timestamp=regime.detected_at,
                    regime=regime.type,
                    confidence=regime.confidence,
                    strategy=self.strategy.name,
                )
            )

            if (
                self.position_qty
                and self.strategy.stop_loss is not None
                and price <= self.avg_price * (1 - self.strategy.stop_loss)
            ):
                await self._sell(price, f"stop loss {self.strategy.stop_loss:.0%} hit", EventKind.STOP_LOSS)

            signal = self.strategy.generate_signal(det.ohlcv)
            self.signals.appendleft(
                SignalRecord(timestamp=_now(), signal=signal, price=round(price, 2), strategy=self.strategy.name)
            )
            if signal == "BUY" and not self.position_qty:
                await self._buy(price, f"{self.strategy.name} BUY signal")
            elif signal == "SELL" and self.position_qty:
                await self._sell(price, f"{self.strategy.name} SELL signal")

            self._mark()

    async def _route(self, regime: Regime, price: float) -> None:
        new = regime.type
        conf = f"{regime.confidence:.0%}"
        if self.strategy is None:
            self.strategy = get_strategy(new)
            self.state.active_regime = new
            self.state.active_strategy = self.strategy.name
            self.stint_start_equity = self._total_pnl()
            self._event(
                EventKind.REGIME_CHANGE,
                f"INITIAL REGIME: {new.value} | Strategy: {self.strategy.name} | Confidence: {conf}",
                new,
            )
            return
        old = self.strategy.regime
        if new == old:
            return
        if regime.confidence < self.min_switch_confidence:
            self._event(
                EventKind.REGIME_HELD,
                f"Detector says {new.value} at {conf}, below the {self.min_switch_confidence:.0%} switch threshold. "
                f"Keeping {old.value}.",
                old,
            )
            return

        if self.position_qty:
            await self._sell(price, f"regime switch {old.value} -> {new.value}")
        stint = self._total_pnl() - self.stint_start_equity
        prev_name = self.strategy.name
        self.strategy = get_strategy(new)
        self.state.active_regime = new
        self.state.active_strategy = self.strategy.name
        self.state.regime_switches += 1
        self.stint_start_equity = self._total_pnl()
        self._event(
            EventKind.REGIME_CHANGE,
            f"REGIME CHANGE: {old.value} → {new.value} | Strategy: {prev_name} → {self.strategy.name} | "
            f"Confidence: {conf} | P&L impact of {prev_name}: {_pct(stint / self.capital * 100)}",
            new,
        )

    # orders

    async def _buy(self, price: float, reason: str) -> None:
        assert self.strategy is not None
        qty = math.floor(self.capital * self.strategy.allocation / price)
        if qty <= 0:
            self._event(EventKind.ERROR, f"BUY skipped: capital too small for one share at {price:.2f}")
            return
        filled = await self._execute(Action.BUY, qty, price)
        if filled is None:
            return
        fill_qty, fill_price, order_id = filled
        self.position_qty, self.avg_price = fill_qty, fill_price
        self.trades.append(
            Trade(
                entry_price=fill_price,
                quantity=fill_qty,
                action=Action.BUY,
                timestamp=_now(),
                strategy=self.strategy.name,
                reason=reason,
                order_id=order_id,
            )
        )
        self._event(EventKind.ORDER, f"BUY {fill_qty} {self.symbol} @ {fill_price:.2f} ({reason})", self.strategy.regime)

    async def _sell(self, price: float, reason: str, kind: EventKind = EventKind.ORDER) -> None:
        assert self.strategy is not None
        filled = await self._execute(Action.SELL, self.position_qty, price)
        if filled is None:
            return
        fill_qty, fill_price, order_id = filled
        pnl = (fill_price - self.avg_price) * fill_qty
        self.realized += pnl
        entry = self.avg_price
        self.position_qty -= fill_qty
        if self.position_qty <= 0:
            self.position_qty, self.avg_price = 0, 0.0
        self.trades.append(
            Trade(
                entry_price=entry,
                exit_price=fill_price,
                quantity=fill_qty,
                action=Action.SELL,
                pnl=round(pnl, 2),
                timestamp=_now(),
                strategy=self.strategy.name,
                reason=reason,
                order_id=order_id,
            )
        )
        self._event(
            kind, f"SELL {fill_qty} {self.symbol} @ {fill_price:.2f}, P&L {pnl:+,.2f} ({reason})", self.strategy.regime
        )

    async def _execute(self, action: Action, qty: int, price: float) -> tuple[int, float, str | None] | None:
        """Returns (filled qty, fill price, order id), or None if nothing filled."""
        if self.mode == "PAPER":
            return qty, price, None
        assert self.dhan is not None and self.security_id is not None
        try:
            order = await asyncio.to_thread(
                self.dhan.place_order, self.security_id, action, qty, "MARKET", "NSE_EQ", "CNC", 0, "miren"
            )
            order_id = str(order["orderId"])
            status, avg, filled = await asyncio.to_thread(self.dhan.settle, order_id)
        except DhanError as exc:
            self._event(EventKind.ERROR, f"Dhan {action.value} {qty} failed: {exc}")
            return None
        if filled <= 0:
            self._event(EventKind.ERROR, f"Dhan order {order_id} ended {status} with no fill; cancelled, position unchanged")
            return None
        if filled < qty:
            self._event(EventKind.ERROR, f"Dhan order {order_id} filled {filled} of {qty}; the rest was cancelled")
        return filled, avg or price, order_id

    # accounting

    def _unrealized(self) -> float:
        if not self.position_qty or self.last_price is None:
            return 0.0
        return (self.last_price - self.avg_price) * self.position_qty

    def _total_pnl(self) -> float:
        return self.realized + self._unrealized()

    def _mark(self) -> None:
        self.equity_marks.append((_now(), self.capital + self._total_pnl()))
        self.state.sharpe = self.sharpe()

    def sharpe(self) -> float | None:
        """Annualised Sharpe of daily equity returns. None until there are 5 daily returns."""
        if len(self.equity_marks) < 2:
            return None
        s = pd.Series([e for _, e in self.equity_marks], index=pd.DatetimeIndex([t for t, _ in self.equity_marks]))
        daily = s.resample("1D").last().dropna().pct_change().dropna()
        if len(daily) < 5 or daily.std() == 0:
            return None
        return round(float(daily.mean() / daily.std() * math.sqrt(252)), 2)

    def _event(self, kind: EventKind, message: str, regime: RegimeType | None = None) -> None:
        log.info("%s %s", kind.value, message)
        self.events.appendleft(Event(timestamp=_now(), kind=kind, message=message, regime=regime))

    # read side

    async def get_status(self) -> ExecutorStatus:
        s = self.state
        s.realized_pnl = round(self.realized, 2)
        s.unrealized_pnl = round(self._unrealized(), 2)
        s.current_pnl = round(self._total_pnl(), 2)
        s.position_qty = self.position_qty
        s.position_avg_price = round(self.avg_price, 2) if self.position_qty else None
        s.last_price = self.last_price
        s.total_trades = len(self.trades)
        return s.model_copy()

    def get_regime_history(self) -> list[RegimeHistory]:
        return list(self.history)

    def strategy_view(self) -> StrategyView | None:
        if self.strategy is None:
            return None
        recent = [x for x in self.signals if x.strategy == self.strategy.name][:5]
        return StrategyView(**self.strategy.describe().model_dump(), recent_signals=recent)
