"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { EventLog } from "@/components/EventLog";
import { MetricsGrid } from "@/components/MetricsGrid";
import { PriceChart } from "@/components/PriceChart";
import { RegimePanel } from "@/components/RegimePanel";
import { RegimeTimeline } from "@/components/RegimeTimeline";
import { StrategyCard } from "@/components/StrategyCard";
import { TopBar } from "@/components/TopBar";
import { Input, Label } from "@/components/ui/input";
import { Dots, Panel } from "@/components/ui/panel";
import { api, errorMessage } from "@/lib/api";
import type { ExecutorStatus, Mode, RegimeAnalysis, Strategy } from "@/lib/types";
import { useLive } from "@/lib/useLive";
import { signedPct } from "@/lib/utils";

const DEFAULT_SYMBOL = "RELIANCE.NS";
const ANALYSIS_REFRESH_MS = 5 * 60 * 1000;

const IDLE: ExecutorStatus = {
  symbol: null,
  mode: "PAPER",
  active_regime: null,
  active_strategy: null,
  status: "IDLE",
  current_pnl: 0,
  realized_pnl: 0,
  unrealized_pnl: 0,
  capital: 0,
  position_qty: 0,
  position_avg_price: null,
  last_price: null,
  sharpe: null,
  total_trades: 0,
  regime_switches: 0,
  started_at: null,
  last_tick_at: null,
  next_tick_at: null,
  error: null,
};

export default function Home() {
  const { snapshot, state: wsState } = useLive();
  const status = snapshot?.status ?? IDLE;
  const serverRunning =
    status.status === "RUNNING" || status.status === "DETECTING" || status.status === "ERROR";
  // the WebSocket pushes every few seconds; until it confirms, treat a successful /start as running
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const running = serverRunning || startedAt !== null;

  const [symbolInput, setSymbolInput] = useState(DEFAULT_SYMBOL);
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL);
  const [capital, setCapital] = useState("100000");
  const [mode, setMode] = useState<Mode>("PAPER");
  const [securityId, setSecurityId] = useState("");
  const [busy, setBusy] = useState(false);

  const [analysis, setAnalysis] = useState<RegimeAnalysis | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [now, setNow] = useState(() => Date.now());

  // follow the running executor's symbol so the chart matches what is being traded
  useEffect(() => {
    if (running && status.symbol && status.symbol !== symbol) {
      setSymbol(status.symbol);
      setSymbolInput(status.symbol);
    }
  }, [running, status.symbol, symbol]);

  useEffect(() => {
    if (startedAt === null) return;
    if (serverRunning) {
      setStartedAt(null);
      return;
    }
    const t = setTimeout(() => setStartedAt(null), 15_000);
    return () => clearTimeout(t);
  }, [serverRunning, startedAt]);

  const load = useCallback(async (sym: string, quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      setAnalysis(await api.analysis(sym));
      setAnalysisError(null);
    } catch (err) {
      const msg = errorMessage(err);
      setAnalysisError(msg);
      if (!quiet) {
        setAnalysis(null);
        toast.error(msg);
      }
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(symbol);
    const t = setInterval(() => void load(symbol, true), ANALYSIS_REFRESH_MS);
    return () => clearInterval(t);
  }, [symbol, load]);

  useEffect(() => {
    api
      .strategies()
      .then(setStrategies)
      .catch(() => setStrategies([]));
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const regime = snapshot?.regime ?? analysis?.current ?? null;
  const preview = useMemo(
    () => (regime ? (strategies.find((s) => s.regime === regime.type) ?? null) : null),
    [regime, strategies],
  );

  const start = async (): Promise<void> => {
    const cap = Number(capital);
    if (!Number.isFinite(cap) || cap <= 0) {
      toast.error("Capital must be a positive number");
      return;
    }
    const sym = symbolInput.trim().toUpperCase();
    if (!sym) {
      toast.error("Enter a symbol");
      return;
    }
    if (mode === "LIVE") {
      if (!securityId.trim()) {
        toast.error("LIVE mode needs the Dhan security ID");
        return;
      }
      if (!window.confirm(`LIVE mode places real orders on Dhan for ${sym}. Continue?`)) return;
    }
    setBusy(true);
    try {
      setSymbol(sym);
      await api.start({
        symbol: sym,
        capital: cap,
        mode,
        ...(mode === "LIVE" ? { security_id: securityId.trim(), confirm_live: true } : {}),
      });
      setStartedAt(Date.now());
      toast.success(`Miren started on ${sym} (${mode})`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const stop = async (): Promise<void> => {
    setBusy(true);
    try {
      await api.stop();
      setStartedAt(null);
      toast.success("Miren stopped");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen">
      <TopBar running={running} busy={busy} mode={mode} onMode={setMode} onStart={start} onStop={stop} />

      <main className="mx-auto flex max-w-[1400px] flex-col gap-4 px-4 py-4">
        <Panel className="border">
          <form
            className="grid grid-cols-2 items-end gap-3 p-4 md:grid-cols-[1.2fr_1fr_1fr_auto]"
            onSubmit={(e) => {
              e.preventDefault();
              const sym = symbolInput.trim().toUpperCase();
              if (sym && !running) setSymbol(sym);
            }}
          >
            <div className="col-span-2 md:col-span-1">
              <Label htmlFor="symbol">Symbol (yfinance)</Label>
              <Input
                id="symbol"
                value={symbolInput}
                disabled={running}
                onChange={(e) => setSymbolInput(e.target.value)}
                placeholder="RELIANCE.NS or ^NSEI"
                autoComplete="off"
              />
            </div>
            <div>
              <Label htmlFor="capital">Capital (₹)</Label>
              <Input
                id="capital"
                inputMode="decimal"
                value={capital}
                disabled={running}
                onChange={(e) => setCapital(e.target.value.replace(/[^\d.]/g, ""))}
              />
            </div>
            <div>
              <Label htmlFor="secid">Dhan Security ID {mode === "PAPER" && "(LIVE only)"}</Label>
              <Input
                id="secid"
                value={securityId}
                disabled={running || mode === "PAPER"}
                onChange={(e) => setSecurityId(e.target.value.replace(/\D/g, ""))}
                placeholder="e.g. 2885"
              />
            </div>
            <button
              type="submit"
              disabled={running}
              className="col-span-2 h-10 border border-line px-4 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted transition-colors hover:text-fg disabled:opacity-40 md:col-span-1"
            >
              Analyze
            </button>
          </form>
          {status.error && running && (
            <p className="border-t border-line px-4 py-2 font-mono text-[11px] text-danger">{status.error}</p>
          )}
        </Panel>

        <Panel className="border">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
            <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-accent">
              {symbol} · Price + Regime
            </h2>
            {analysis && (
              <span className="font-mono text-[10px] text-muted">
                {analysis.timeline.length}d replay {signedPct(analysis.replay_return_pct)} vs buy and hold{" "}
                {signedPct(analysis.buy_hold_return_pct)}
              </span>
            )}
          </div>
          {loading ? (
            <div className="flex h-[300px] flex-col items-center justify-center gap-3 font-mono text-xs text-muted sm:h-[380px]">
              <Dots />
              Detecting regimes for {symbol}
            </div>
          ) : analysis ? (
            <>
              <PriceChart analysis={analysis} liveRegime={snapshot?.regime?.type ?? null} />
              <p className="border-t border-line px-4 py-2 font-mono text-[10px] leading-relaxed text-muted">
                {analysis.note}
              </p>
            </>
          ) : (
            <div className="flex h-[300px] items-center justify-center p-6 text-center font-mono text-xs text-danger">
              {analysisError ?? "No data"}
            </div>
          )}
        </Panel>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
          <RegimePanel regime={regime} loading={loading && !snapshot?.regime} />
          <MetricsGrid status={status} now={now} />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <RegimeTimeline timeline={analysis?.timeline ?? []} loading={loading} />
          <EventLog events={snapshot?.events ?? []} connected={wsState === "open"} />
        </div>

        <StrategyCard live={snapshot?.strategy ?? null} preview={preview} running={running} />

        <footer className="pb-6 pt-2 text-center font-mono text-[10px] text-muted">
          Pure quant math: Gaussian HMM + KMeans. No LLM anywhere. Market data from yfinance, orders via Dhan.
        </footer>
      </main>
    </div>
  );
}
