"""Pydantic v2 models shared by the API, the detector and the executor."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegimeType(str, Enum):
    TRENDING = "TRENDING"
    MEAN_REVERTING = "MEAN_REVERTING"
    VOLATILE = "VOLATILE"
    CALM = "CALM"


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


Signal = Literal["BUY", "SELL", "HOLD"]
Mode = Literal["PAPER", "LIVE"]
RunState = Literal["IDLE", "DETECTING", "RUNNING", "STOPPED", "ERROR"]


class Regime(BaseModel):
    type: RegimeType
    confidence: float = Field(ge=0, le=1)
    detected_at: datetime
    # raw (unscaled) feature values of the latest bar plus detector diagnostics
    features: dict[str, int | float | str | bool | None]


class Strategy(BaseModel):
    name: str
    regime: RegimeType
    description: str
    parameters: dict[str, float | int]


class Trade(BaseModel):
    entry_price: float
    exit_price: float | None = None
    quantity: int
    action: Action
    pnl: float | None = None
    timestamp: datetime
    strategy: str
    reason: str
    order_id: str | None = None


class ExecutorStatus(BaseModel):
    symbol: str | None = None
    mode: Mode = "PAPER"
    active_regime: RegimeType | None = None
    active_strategy: str | None = None
    status: RunState = "IDLE"
    current_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    capital: float = 0.0
    position_qty: int = 0
    position_avg_price: float | None = None
    last_price: float | None = None
    sharpe: float | None = None
    total_trades: int = 0
    regime_switches: int = 0
    started_at: datetime | None = None
    last_tick_at: datetime | None = None
    next_tick_at: datetime | None = None
    error: str | None = None


class RegimeHistory(BaseModel):
    timestamp: datetime
    regime: RegimeType
    confidence: float
    strategy: str


class SignalRecord(BaseModel):
    timestamp: datetime
    signal: Signal
    price: float
    strategy: str


class EventKind(str, Enum):
    START = "START"
    STOP = "STOP"
    REGIME_CHANGE = "REGIME_CHANGE"
    REGIME_HELD = "REGIME_HELD"
    ORDER = "ORDER"
    STOP_LOSS = "STOP_LOSS"
    ERROR = "ERROR"


class Event(BaseModel):
    timestamp: datetime
    kind: EventKind
    message: str
    regime: RegimeType | None = None


class StartRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    symbol: str = Field(min_length=1, max_length=32, examples=["RELIANCE.NS"])
    capital: float = Field(gt=0, le=1e9)
    mode: Mode = "PAPER"
    # LIVE only: Dhan security id of the same instrument (e.g. RELIANCE 2885) and an explicit opt-in
    security_id: str | None = Field(default=None, max_length=20)
    confirm_live: bool = False

    @field_validator("symbol")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()


class StrategyView(Strategy):
    """Strategy plus the last signals it produced, for the dashboard."""

    recent_signals: list[SignalRecord] = []


class LiveSnapshot(BaseModel):
    """What /ws/live pushes every few seconds."""

    status: ExecutorStatus
    regime: Regime | None
    strategy: StrategyView | None
    events: list[Event]


class Bar(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class TimelineDay(BaseModel):
    date: date
    close: float
    regime: RegimeType
    confidence: float
    strategy: str
    position: int  # 1 long, 0 flat, at the close of this day
    pnl_pct: float  # replay return of the day, in percent of capital


class RegimeAnalysis(BaseModel):
    """Historical regime replay for a symbol. `timeline` has one entry per bar; the dashboard
    colours the chart with all of it and shows the last 30 days in the timeline panel."""

    symbol: str
    bars: list[Bar]
    timeline: list[TimelineDay]
    current: Regime
    replay_return_pct: float
    buy_hold_return_pct: float
    note: str
