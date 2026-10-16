"""Miren API."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv()

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from dhan_client import DhanClient  # noqa: E402
from executor import MirenExecutor  # noqa: E402
from feature_engine import MarketDataError  # noqa: E402
from models import (  # noqa: E402
    Event,
    ExecutorStatus,
    LiveSnapshot,
    Regime,
    RegimeAnalysis,
    RegimeHistory,
    StartRequest,
    Strategy,
    StrategyView,
)
from regime_detector import RegimeDetector  # noqa: E402
from replay import replay  # noqa: E402
from strategy_router import all_strategies  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")

DEFAULT_SYMBOL = os.getenv("MIREN_DEFAULT_SYMBOL", "^NSEI")
CACHE_SECONDS = float(os.getenv("MIREN_CACHE_SECONDS", "300"))
WS_SECONDS = float(os.getenv("MIREN_WS_SECONDS", "5"))
CACHE_MAX_SYMBOLS = 32


class AnalysisCache:
    """One detector run per symbol per CACHE_SECONDS, so page loads do not refit the HMM each time."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, RegimeAnalysis]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, symbol: str) -> RegimeAnalysis:
        lock = self._locks.setdefault(symbol, asyncio.Lock())
        async with lock:
            hit = self._data.get(symbol)
            if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
                return hit[1]
            det = await RegimeDetector().analyze(symbol)
            analysis = await asyncio.to_thread(replay, symbol, det)
            self._data[symbol] = (time.monotonic(), analysis)
            if len(self._data) > CACHE_MAX_SYMBOLS:  # drop the oldest entry so arbitrary tickers cannot grow memory
                oldest = min(self._data, key=lambda k: self._data[k][0])
                self._data.pop(oldest, None)
                self._locks.pop(oldest, None)
            return analysis


cache = AnalysisCache()
executor: MirenExecutor | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    if executor is not None:
        await executor.stop()


app = FastAPI(title="Miren", version="1.0.0", lifespan=lifespan)
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _clean(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not symbol or len(symbol) > 32:
        raise HTTPException(status_code=422, detail="symbol must be 1 to 32 characters")
    return symbol


async def _analysis(symbol: str) -> RegimeAnalysis:
    try:
        return await cache.get(symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class HealthResponse(BaseModel):
    status: str
    executor_running: bool
    dhan_configured: bool


class StartResponse(BaseModel):
    status: str
    symbol: str
    mode: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        executor_running=bool(executor and executor.running),
        dhan_configured=DhanClient().configured,
    )


@app.post("/start", response_model=StartResponse)
async def start(req: StartRequest) -> StartResponse:
    global executor
    if executor is not None and executor.running:
        raise HTTPException(status_code=409, detail=f"Already running on {executor.symbol}. Stop it first.")
    dhan: DhanClient | None = None
    if req.mode == "LIVE":
        dhan = DhanClient()
        if not dhan.configured:
            raise HTTPException(status_code=400, detail="LIVE mode needs DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN in .env")
        if not req.security_id:
            raise HTTPException(status_code=400, detail="LIVE mode needs the Dhan security_id of the instrument")
        if not req.confirm_live:
            raise HTTPException(status_code=400, detail="LIVE mode places real orders; set confirm_live to true")
    executor = MirenExecutor(req.symbol, req.capital, req.mode, dhan_client=dhan, security_id=req.security_id)
    await executor.start()
    return StartResponse(status="started", symbol=req.symbol, mode=req.mode)


@app.post("/stop", response_model=ExecutorStatus)
async def stop() -> ExecutorStatus:
    if executor is None:
        raise HTTPException(status_code=404, detail="Executor has not been started")
    await executor.stop()
    return await executor.get_status()


@app.get("/status", response_model=ExecutorStatus)
async def status() -> ExecutorStatus:
    return await executor.get_status() if executor else ExecutorStatus()


@app.get("/regime/current", response_model=Regime)
async def regime_current(symbol: str | None = Query(default=None)) -> Regime:
    """The executor's latest regime, or a fresh (cached) detection for `symbol` when idle."""
    if executor is not None and executor.regime is not None and (symbol is None or _clean(symbol) == executor.symbol):
        return executor.regime
    return (await _analysis(_clean(symbol or DEFAULT_SYMBOL))).current


@app.get("/regime/history", response_model=list[RegimeHistory])
async def regime_history() -> list[RegimeHistory]:
    return executor.get_regime_history() if executor else []


@app.get("/regime/analysis", response_model=RegimeAnalysis)
async def regime_analysis(symbol: str = Query(default=DEFAULT_SYMBOL)) -> RegimeAnalysis:
    """Price bars with a per-day regime label and replay P&L, for the chart and the 30-day timeline."""
    return await _analysis(_clean(symbol))


@app.get("/strategy", response_model=StrategyView | None)
async def active_strategy() -> StrategyView | None:
    return executor.strategy_view() if executor else None


@app.get("/strategies", response_model=list[Strategy])
async def strategies() -> list[Strategy]:
    return all_strategies()


@app.get("/events", response_model=list[Event])
async def events(limit: int = Query(default=100, ge=1, le=300)) -> list[Event]:
    return list(executor.events)[:limit] if executor else []


async def snapshot() -> LiveSnapshot:
    if executor is None:
        return LiveSnapshot(status=ExecutorStatus(), regime=None, strategy=None, events=[])
    return LiveSnapshot(
        status=await executor.get_status(),
        regime=executor.regime,
        strategy=executor.strategy_view(),
        events=list(executor.events)[:100],
    )


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            await ws.send_text((await snapshot()).model_dump_json())
            await asyncio.sleep(WS_SECONDS)
    except (WebSocketDisconnect, RuntimeError):
        pass
