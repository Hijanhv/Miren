# Miren

Miren is an autonomous market regime detector. It reads daily market data, decides which of four regimes the market is in (trending, mean-reverting, volatile, calm), and runs the strategy built for that regime. When the regime changes, it closes the old strategy's position, switches strategy, and logs what the old strategy earned.

```
[14:32:05] REGIME CHANGE: TRENDING → VOLATILE | Strategy: EMA Crossover → ATR Breakout | Confidence: 91% | P&L impact of EMA Crossover: +2.31%
```

There is no LLM anywhere in Miren. Detection is a Gaussian Hidden Markov Model with a KMeans cross-check, and every strategy is a fixed indicator rule.

## How it works

```
yfinance daily OHLCV
   → feature_engine    realized vol, autocorrelation, ADX, ATR ratio, BB width, RSI, volume ratio
   → regime_detector   GaussianHMM (4 states, full covariance) + KMeans (4 clusters)
   → regime label      TRENDING / MEAN_REVERTING / VOLATILE / CALM
   → strategy_router   one strategy per regime
   → executor          asyncio loop every 5 minutes, PAPER fills or Dhan orders
   → dashboard         price chart with regime bands, live P&L, event log (WebSocket)
```

### Features (`backend/feature_engine.py`)

| Feature | Definition | Reads as |
|---|---|---|
| `realized_vol` | 20-day std of log returns × √252 | annualised volatility |
| `autocorrelation` | lag-1 autocorrelation of returns over 10 days | > 0.1 persistent (trend), < -0.1 reverting |
| `adx` | ADX(14) from `ta` | trend strength, > 25 is strong |
| `atr_ratio` | ATR(14) / close | normalised daily range |
| `bb_width` | (upper − lower) / middle Bollinger Band | squeeze vs expansion |
| `rsi` | RSI(14) | overbought / oversold |
| `volume_ratio` | volume / 20-day average volume | participation |

Every feature on a given day uses only bars up to that day. A test checks that features computed on a truncated history match the full history.

### The four regimes

| Regime | What the market is doing | Strategy | Rules |
|---|---|---|---|
| **TRENDING** (blue) | Strong ADX, positive autocorrelation: moves persist | EMA Crossover | BUY when EMA(20) crosses above EMA(50), SELL on the cross back. 100% allocation |
| **MEAN_REVERTING** (purple) | Negative autocorrelation, weak ADX: moves snap back | Bollinger Reversion | BUY at or below the lower band (20, 2σ) with RSI < 35, SELL at the upper band with RSI > 65. 75% allocation |
| **VOLATILE** (red) | High realized vol and ATR ratio | ATR Breakout | BUY above the prior 20-day high + 0.5×ATR, SELL below the prior 20-day low − 0.5×ATR. 1% stop loss. 50% allocation |
| **CALM** (green) | Low vol, low ADX, narrow bands | SMA Carry | BUY 0.3% below SMA(10), SELL 0.3% above. 25% allocation |

All strategies are long-only: BUY opens a long, SELL closes it. This matches what you can hold overnight in a cash (CNC) equity account on Dhan.

### From hidden state to label (`backend/regime_detector.py`)

The HMM is fit on standardised features, so each hidden state's mean vector is a z-score profile, for example "ADX +1.2, autocorrelation +0.6, vol −0.3". Each regime has a score over that profile:

- TRENDING = adx + autocorrelation
- MEAN_REVERTING = −autocorrelation − adx
- VOLATILE = realized_vol + atr_ratio
- CALM = −realized_vol − adx − bb_width

The 4 states are assigned to the 4 regimes by the permutation with the highest total score, so every state gets a distinct label. KMeans centroids are labelled with the same rule.

Confidence is the HMM's posterior probability of the chosen state on the latest bar. Miren uses **filtered** (forward-only) probabilities, not the smoothed ones `hmmlearn.predict_proba` returns. As a result, the label for any past day only uses data up to that day.

### HMM vs KMeans

| | Gaussian HMM | KMeans |
|---|---|---|
| Time | Models transitions between states, so regimes are sticky and one noisy day rarely flips the label | Classifies each day on its own; labels can flicker day to day |
| Shape | Full covariance per state: captures "vol and ATR rise together" | Spherical clusters of equal size by assumption |
| Output | A probability per state (used as confidence) | A hard cluster ID, no confidence |
| Cost | EM can converge to a local optimum; needs a few hundred rows | Fast and stable with `n_init=10` |
| Calibration | Posteriors are often near 0% or 100%, so read confidence as relative, not as a calibrated probability | n/a |

Miren trusts the HMM for the label and confidence. KMeans is a second opinion: the dashboard shows whether it agrees on the latest bar. Persistent disagreement is a hint that the regime is ambiguous.

### Switching rules (`backend/executor.py`)

Every tick (default 300 s):

1. Download fresh bars and refit the detector on the latest 500-day window.
2. If the regime changed **and** HMM confidence is at least `MIREN_MIN_SWITCH_CONFIDENCE` (default 0.6): close the open position, switch strategy, and log the outgoing strategy's P&L as a percent of capital. A change below that confidence is logged as `REGIME_HELD` and ignored.
3. Check the stop loss (ATR Breakout only).
4. Ask the active strategy for a signal on the latest candle and act on it.
5. Mark equity for P&L and Sharpe (annualised from daily equity, shown once there are 5 daily returns).

A failed download or a broker error is logged and retried on the next tick. It never kills the loop.

## Project layout

```
miren/
├── backend/
│   ├── main.py              FastAPI routes + WebSocket
│   ├── models.py            Pydantic v2 models
│   ├── feature_engine.py    yfinance download + features
│   ├── regime_detector.py   HMM + KMeans + state→regime mapping
│   ├── strategies.py        the 4 strategies
│   ├── strategy_router.py   regime → strategy
│   ├── replay.py            day-by-day historical replay for the chart and timeline
│   ├── executor.py          the autonomous asyncio loop
│   ├── dhan_client.py       dhanhq v2 wrapper (credentials from env)
│   └── tests/               41 tests: synthetic data and a mock Dhan v2 server, no network
├── frontend/                Next.js 14 App Router, TypeScript, Tailwind, lightweight-charts
├── .env.example
└── start.sh
```

## Setup

Requirements: Python 3.11+, Node 18+.

```bash
git clone <this repo> miren && cd miren
cp .env.example .env
./start.sh
```

- Dashboard: http://localhost:3001
- API: http://localhost:8001 (interactive docs at `/docs`)

`start.sh` creates `backend/.venv`, installs `requirements.txt` (with `uv` if present, otherwise pip), runs `npm install` once, and starts both servers.

To run the parts by hand:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8001

cd frontend && npm install && npm run dev -- --port 3001
```

Tests:

```bash
cd backend && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest
cd frontend && npm run typecheck && npm run lint
```

### Symbols

Symbols use yfinance tickers: NSE stocks end in `.NS` (`RELIANCE.NS`, `TCS.NS`, `HDFCBANK.NS`), and indices start with `^` (`^NSEI` for Nifty 50, `^NSEBANK`). Unknown tickers return a clear 422 error instead of crashing.

## Dhan credentials (LIVE mode only)

PAPER mode needs no credentials. For LIVE:

1. Log in to [web.dhan.co](https://web.dhan.co) → My Profile → **Access DhanHQ APIs** and generate an access token. It lasts 24 hours.
2. Put `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN` in `.env`. Never commit that file.
3. Dhan requires a whitelisted static IP for order placement. Set it on the same page.
4. In the dashboard, switch to LIVE, enter the instrument's **Dhan security ID** (RELIANCE `2885`, HDFCBANK `1333`, INFY `1594`, from Dhan's [instrument list](https://images.dhan.co/api-data/api-scrip-master.csv)), and confirm the prompt.

LIVE places MARKET CNC orders on `NSE_EQ` and polls each order until it trades. A rejected order leaves the position unchanged and shows up in the event log.

To try LIVE without real money, use Dhan's sandbox: create keys at [developer.dhanhq.co](https://developer.dhanhq.co) and set `DHAN_API_BASE_URL=https://sandbox.dhan.co/v2`.

## Deployment

**Why the backend cannot run on Vercel.** Vercel runs Python as short-lived serverless functions. Miren's backend needs three things that model does not offer: a background loop that keeps running every 5 minutes, a WebSocket (`/ws/live`), and executor state held in memory between requests. Vercel's Hobby cron also fires at most once a day. So the frontend goes on Vercel and the backend goes on a host that runs a long-lived process (Render, Railway, Fly.io or any VPS).

Deploy the backend **without** `DHAN_CLIENT_ID` / `DHAN_ACCESS_TOKEN` unless you mean to trade. The API has no login, so anyone who can reach a backend that holds Dhan credentials can start LIVE trading. Without them, LIVE is refused and the public app is PAPER only.

### Backend on Render or Railway

- Root directory: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Env: `CORS_ORIGINS=https://<your-app>.vercel.app` (add Dhan credentials only on a private deployment)

The executor lives in process memory, so run one instance. A free instance that sleeps will pause the loop.

### Frontend on Vercel

1. Import the repo in Vercel and set **Root Directory** to `frontend`. The framework is detected as Next.js.
2. Add `NEXT_PUBLIC_API_URL=https://<your-backend-host>`. The WebSocket URL is derived from it (`https` → `wss`).
3. Deploy.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/start` | `{symbol, capital, mode, security_id?, confirm_live?}` starts the executor |
| POST | `/stop` | stops it (an open position is kept and reported) |
| GET | `/status` | `ExecutorStatus` |
| GET | `/regime/current?symbol=` | executor's regime, or a fresh detection when idle |
| GET | `/regime/history` | regime per executor tick |
| GET | `/regime/analysis?symbol=` | bars + per-day regime + replay P&L (chart and timeline) |
| GET | `/strategy` | active strategy with its last signals |
| GET | `/strategies` | all four strategies and parameters |
| GET | `/events` | event log, newest first |
| GET | `/health` | `{status, executor_running, dhan_configured}` |
| WS | `/ws/live` | pushes status, regime, strategy and events every 5 s |

## Example output

Recent regime transitions detected on RELIANCE.NS (daily bars, 500-day window, run on 2026-10-16):

```
2026-05-29  MEAN_REVERTING → TRENDING        conf 100%  Strategy: EMA Crossover
2026-06-12  TRENDING → MEAN_REVERTING        conf  60%  Strategy: Bollinger Reversion
2026-08-31  MEAN_REVERTING → TRENDING        conf 100%  Strategy: EMA Crossover
2026-09-03  TRENDING → MEAN_REVERTING        conf  99%  Strategy: Bollinger Reversion
2026-09-16  MEAN_REVERTING → TRENDING        conf  91%  Strategy: EMA Crossover
```

The live event log for the same symbol:

```
[17:46:22] Started PAPER on RELIANCE.NS with capital 100,000. Detecting every 300s.
[17:46:22] INITIAL REGIME: TRENDING | Strategy: EMA Crossover | Confidence: 100%
```

The 500-day replay for RELIANCE.NS returned +25.9% against −11.0% for buy and hold. Read that number with care:

## Limits, stated plainly

- **The replay is not a backtest.** Each day's label uses only past bars, but the HMM parameters are fit on the whole window, and there are no costs or slippage.
- **Daily bars, 5-minute loop.** Detection runs every 5 minutes on daily candles. Intraday, the latest candle is today's partial bar from yfinance (which can be delayed), so the regime rarely changes within a day. The loop keeps the system current without waiting for the close.
- **The HMM is refit every tick.** State numbering can change between fits; the label mapping above is recomputed each time, so labels stay consistent.
- **Window size.** `extract_features` defaults to 60 rows as specified, but the detector fits on 500 rows (`MIREN_DETECT_WINDOW`). A 4-state full-covariance HMM over 7 features has about 150 parameters and cannot be fit on 60 rows. If the full-covariance fit fails, it falls back to diagonal.
- **Crossover strategies wait for a cross.** After a switch into TRENDING, EMA Crossover stays flat until the next crossover rather than buying into an existing trend.
- **State is in memory.** Restarting the API clears the executor, events and P&L.
- Nothing here is investment advice. Use PAPER mode until you understand what it does.
