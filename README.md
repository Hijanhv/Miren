# Miren

**The market changes. Miren changes with it.**

Miren is an autonomous market regime detector. It reads daily market data, decides which of four regimes the market is in (trending, mean-reverting, volatile, calm), and runs the strategy built for that regime. When the regime changes, it closes the old strategy's position, switches strategy, and logs what the old strategy earned.

```
[14:32:05] REGIME CHANGE: TRENDING → VOLATILE | Strategy: EMA Crossover → ATR Breakout | Confidence: 91% | P&L impact of EMA Crossover: +2.31%
```

There is no LLM anywhere in Miren. Detection is a Gaussian Hidden Markov Model with a KMeans cross-check, and every strategy is a fixed indicator rule. Miren runs on your own machine (localhost).

## Contents

1. [Quick start](#quick-start)
2. [Using the dashboard](#using-the-dashboard)
3. [Running the backend and frontend separately](#running-the-backend-and-frontend-separately)
4. [Configuration](#configuration)
5. [Symbols](#symbols)
6. [Tests](#tests)
7. [LIVE mode with Dhan](#live-mode-with-dhan)
8. [How it works](#how-it-works)
9. [Project layout](#project-layout)
10. [API](#api)
11. [Example output](#example-output)
12. [Troubleshooting](#troubleshooting)
13. [Why localhost and not Vercel](#why-localhost-and-not-vercel)
14. [Limits, stated plainly](#limits-stated-plainly)

## Quick start

### 1. Prerequisites

| Tool | Version | Check with |
|---|---|---|
| Python | 3.11 or newer | `python3 --version` |
| Node.js | 18 or newer | `node --version` |
| git | any | `git --version` |
| [uv](https://docs.astral.sh/uv/) | optional, makes installs faster | `uv --version` |

You also need an internet connection: market data comes from Yahoo Finance through `yfinance`. No API keys are needed for PAPER mode.

### 2. Get the code

```bash
git clone https://github.com/Hijanhv/Miren.git miren
cd miren
```

### 3. Start everything

```bash
./start.sh
```

On the first run this:

1. copies `.env.example` to `.env`,
2. creates a Python virtual environment in `backend/.venv` and installs `backend/requirements.txt`,
3. runs `npm install` in `frontend/`,
4. starts the API on port 8001 and the dashboard on port 3001.

The first run takes a few minutes because of the installs. Later runs start in seconds.

### 4. Open the dashboard

- Dashboard: **http://localhost:3001**
- API docs (Swagger): http://localhost:8001/docs
- Health check: http://localhost:8001/health

### 5. Stop

Press **Ctrl+C** in the terminal running `start.sh`. Both servers stop. Executor state (P&L, events) lives in memory, so it resets on the next start.

## Using the dashboard

1. **Pick a symbol.** The page opens on `RELIANCE.NS`. Type another yfinance ticker (for example `TCS.NS` or `^NSEI`) and press **Analyze**. Miren downloads about two years of daily bars, fits the HMM and KMeans, and labels every day. This takes a few seconds; skeletons show while it runs.
2. **Read the chart.** The price line sits over colour bands, one per regime: blue TRENDING, purple MEAN_REVERTING, red VOLATILE, green CALM. The label in the top right is today's regime. The header line compares the regime-switching replay with buy and hold over the same window.
3. **Read the current regime.** The regime card shows the label, the HMM confidence bar, whether KMeans agrees, and the seven raw features with a plain reading (for example `ADX 35.9 HIGH`, `Autocorr 0.13 TRENDING`).
4. **Check the 30-day timeline.** One coloured block per day. Hover or tap a block to see that day's regime, confidence, active strategy and replay P&L. A dot means the replay held a long at that day's close.
5. **Set capital and mode.** Enter capital in rupees and leave the mode on **PAPER**.
6. **Press START.** Miren runs its first detection straight away, then every 5 minutes. The controls lock while it runs.
7. **Watch it work.** The event log (newest first) shows the initial regime, every regime change with the strategy switch and the outgoing strategy's P&L, every order, stop-loss exits and any data errors. The strategy card shows the active strategy, its parameters and its last 5 signals. The metric tiles show P&L, Sharpe, the number of regime switches and how long it has been running.
8. **Press STOP** to end the run. An open paper position is kept and reported in the log.

You never pick a strategy by hand. The router picks it from the detected regime.

To see the loop tick faster while demoing, set `MIREN_TICK_SECONDS=30` in `.env` and restart. The regime is computed from daily bars, so it rarely changes within a day; faster ticks mostly show new HOLD signals.

## Running the backend and frontend separately

Use two terminals if you want to see each log on its own.

**Terminal 1, API:**

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8001
```

**Terminal 2, dashboard:**

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8001 npm run dev -- --port 3001
```

For a production build of the dashboard: `npm run build && npm start -- --port 3001`.

## Configuration

All settings live in `.env` at the repo root (created from `.env.example`). The API reads it on start; `start.sh` passes `NEXT_PUBLIC_API_URL` to the dashboard. Restart after changing it. Never commit `.env`; it is in `.gitignore`.

| Variable | Default | What it does |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8001` | Where the dashboard finds the API. The WebSocket URL is derived from it |
| `MIREN_TICK_SECONDS` | `300` | Seconds between detection cycles |
| `MIREN_MIN_SWITCH_CONFIDENCE` | `0.6` | A regime change below this HMM confidence is logged as `REGIME_HELD` and does not switch strategy |
| `MIREN_DETECT_WINDOW` | `500` | Daily feature rows the HMM and KMeans are fit on |
| `MIREN_DEFAULT_SYMBOL` | `^NSEI` | Symbol `/regime/current` and `/regime/analysis` use when none is given |
| `MIREN_CACHE_SECONDS` | `300` | How long an analysis per symbol is reused before refitting |
| `MIREN_WS_SECONDS` | `5` | How often `/ws/live` pushes an update |
| `CORS_ORIGINS` | `*` | Comma-separated origins allowed to call the API |
| `LOG_LEVEL` | `INFO` | API log level |
| `DHAN_CLIENT_ID` | none | LIVE mode only, see below |
| `DHAN_ACCESS_TOKEN` | none | LIVE mode only, see below |
| `DHAN_API_BASE_URL` | Dhan production | Set to `https://sandbox.dhan.co/v2` to use Dhan's sandbox |
| `DHAN_HTTP_TIMEOUT` | `20` | Seconds before a Dhan call is abandoned |

## Symbols

Symbols use yfinance tickers:

- NSE stocks end in `.NS`: `RELIANCE.NS`, `TCS.NS`, `HDFCBANK.NS`, `INFY.NS`
- BSE stocks end in `.BO`: `RELIANCE.BO`
- Indices start with `^`: `^NSEI` (Nifty 50), `^NSEBANK` (Bank Nifty)
- US tickers work as they are: `AAPL`, `SPY`

An unknown ticker shows a clear error ("No data for ...") instead of crashing. A symbol needs at least about 170 trading days of history for the HMM to fit.

## Tests

```bash
# backend: 41 tests, no network needed (synthetic data and a mock Dhan v2 server)
cd backend
.venv/bin/pip install -r requirements-dev.txt     # or: uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest

# frontend: type check, lint, production build
cd frontend
npm run typecheck
npm run lint
npm run build
```

GitHub Actions runs all of the above on every push (`.github/workflows/ci.yml`).

## LIVE mode with Dhan

PAPER mode needs nothing from Dhan. LIVE mode places real orders, so try the sandbox first.

### Test with Dhan's sandbox (virtual money)

1. Create sandbox keys at [developer.dhanhq.co](https://developer.dhanhq.co).
2. In `.env` set:
   ```
   DHAN_CLIENT_ID=<sandbox client id>
   DHAN_ACCESS_TOKEN=<sandbox token>
   DHAN_API_BASE_URL=https://sandbox.dhan.co/v2
   ```
3. Run the check script:
   ```bash
   cd backend && .venv/bin/python scripts/dhan_sandbox_check.py
   ```
   It buys and sells 1 share of RELIANCE through Miren's Dhan client and prints each step. It refuses to run against any URL other than the sandbox, so it can never touch real money.
4. Restart `./start.sh` and use LIVE in the dashboard as below. Orders go to the sandbox.

### Real account

1. Log in to [web.dhan.co](https://web.dhan.co) → My Profile → **Access DhanHQ APIs** and generate an access token. It lasts 24 hours, so generate a new one each day.
2. Put `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN` in `.env` and remove `DHAN_API_BASE_URL`.
3. Whitelist your static IP on the same page. Dhan rejects order placement from other IPs.
4. Restart `./start.sh`. `http://localhost:8001/health` should show `"dhan_configured": true`.
5. In the dashboard, switch to **LIVE**, enter the instrument's **Dhan security ID** (RELIANCE `2885`, HDFCBANK `1333`, INFY `1594`, all in Dhan's [instrument list](https://images.dhan.co/api-data/api-scrip-master.csv)), press START and confirm the prompt. The yfinance symbol and the security ID must be the same instrument.

What LIVE does: MARKET orders, product CNC, segment `NSE_EQ`. Each order is polled until it trades. Anything still open after polling is cancelled, so no order is left working at the broker. A partial fill is kept and the rest cancelled. A rejected order leaves the position unchanged and shows the broker's reason in the event log.

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
│   ├── scripts/             dhan_sandbox_check.py
│   ├── tests/               41 tests: synthetic data and a mock Dhan v2 server, no network
│   └── requirements.txt
├── frontend/
│   ├── app/                 layout.tsx, page.tsx, globals.css
│   ├── components/          PriceChart, RegimePanel, MetricsGrid, RegimeTimeline, EventLog, StrategyCard, TopBar, ui/
│   ├── lib/                 api.ts (Axios), useLive.ts (WebSocket with reconnect), types.ts, regime.ts, utils.ts
│   └── package.json
├── .github/workflows/ci.yml
├── .env.example
├── start.sh
└── README.md
```

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

Examples:

```bash
curl http://localhost:8001/health
curl "http://localhost:8001/regime/current?symbol=TCS.NS"
curl -X POST http://localhost:8001/start -H "Content-Type: application/json" \
     -d '{"symbol": "RELIANCE.NS", "capital": 100000, "mode": "PAPER"}'
curl http://localhost:8001/events
curl -X POST http://localhost:8001/stop
```

Only one executor runs at a time. A second `/start` while one is running returns 409.

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

The 500-day replay for RELIANCE.NS returned +25.9% against −11.0% for buy and hold. Read that number with the limits below in mind.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Python 3.11+ is required` | Install Python 3.11 or newer, or install `uv` (`curl -LsSf https://astral.sh/uv/install.sh \| sh`) and `start.sh` will fetch Python 3.12 for you |
| `address already in use` on 8001 or 3001 | Something else uses the port. Find it with `lsof -i :8001` and stop it, or stop an older `start.sh` |
| Dashboard says "Cannot reach the Miren API" | The API is not running or `NEXT_PUBLIC_API_URL` is wrong. Open http://localhost:8001/health to check |
| Event log shows "reconnecting" | The WebSocket dropped (for example the API restarted). It reconnects on its own with backoff up to 15 s |
| "No data for SYMBOL" | Wrong ticker. NSE stocks need `.NS`. Yahoo also rate-limits now and then; wait a minute and retry |
| "need at least 120 feature rows" | The symbol is too new for the HMM. Pick one with more history |
| Dependency install fails on a very new Python | Use Python 3.12 (`uv venv --python 3.12 backend/.venv`), then rerun `./start.sh` |
| LIVE start says Dhan credentials are missing | Fill `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN` in `.env` and restart |
| Dhan `DH-901` / invalid token | The access token expired (24 h). Generate a new one |
| Orders rejected for IP | Whitelist your static IP on web.dhan.co |
| Want a clean slate | Stop, then `rm -rf backend/.venv frontend/node_modules frontend/.next` and run `./start.sh` again |

## Why localhost and not Vercel

Miren is meant to run on localhost. It does not need a deployment.

Vercel can host the dashboard, but not the backend. Vercel runs Python as short-lived serverless functions, and Miren's backend needs three things that model does not offer:

- a background loop that keeps running every 5 minutes,
- a WebSocket (`/ws/live`),
- executor state held in memory between requests.

Vercel's Hobby cron also fires at most once a day. Deploying only the dashboard would give a page that tries to reach `localhost` on the visitor's machine, which does not work.

If you ever want a public demo, put the backend on a host that runs a long-lived process (Render, Railway, Fly.io or a VPS) and the dashboard on Vercel:

- **Backend:** root directory `backend`, build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`, env `CORS_ORIGINS=https://<your-app>.vercel.app`. Run one instance only, since state is in memory. A free instance that sleeps pauses the loop.
- **Dashboard:** import the repo in Vercel, set Root Directory to `frontend`, add `NEXT_PUBLIC_API_URL=https://<your-backend-host>`.
- **Do not put Dhan keys on a public backend.** The API has no login, so anyone who can reach it could start LIVE trading. Without keys, LIVE is refused and the public app is PAPER only.

## Limits, stated plainly

- **The replay is not a backtest.** Each day's label uses only past bars, but the HMM parameters are fit on the whole window, and there are no costs or slippage.
- **Daily bars, 5-minute loop.** Detection runs every 5 minutes on daily candles. Intraday, the latest candle is today's partial bar from yfinance (which can be delayed), so the regime rarely changes within a day. The loop keeps the system current without waiting for the close.
- **The HMM is refit every tick.** State numbering can change between fits; the label mapping above is recomputed each time, so labels stay consistent.
- **Window size.** `extract_features` defaults to 60 rows as specified, but the detector fits on 500 rows (`MIREN_DETECT_WINDOW`). A 4-state full-covariance HMM over 7 features has about 150 parameters and cannot be fit on 60 rows. If the full-covariance fit fails, it falls back to diagonal.
- **Crossover strategies wait for a cross.** After a switch into TRENDING, EMA Crossover stays flat until the next crossover rather than buying into an existing trend.
- **State is in memory.** Restarting the API clears the executor, events and P&L.
- Nothing here is investment advice. Use PAPER mode until you understand what it does.
