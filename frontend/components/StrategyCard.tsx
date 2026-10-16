import { Badge } from "@/components/ui/badge";
import { Empty, Panel, PanelLabel } from "@/components/ui/panel";
import { REGIMES } from "@/lib/regime";
import type { Signal, Strategy, StrategyView } from "@/lib/types";
import { cn, formatNum, formatTime } from "@/lib/utils";

const PARAM_LABELS: Record<string, string> = {
  fast_ema: "EMA Fast",
  slow_ema: "EMA Slow",
  bb_period: "BB Period",
  bb_std: "BB Std Dev",
  rsi_buy: "RSI Buy Below",
  rsi_sell: "RSI Sell Above",
  lookback: "Channel Lookback",
  atr_multiplier: "ATR Multiplier",
  sma_period: "SMA Period",
  threshold: "Band Threshold",
  allocation: "Capital Allocation",
  stop_loss: "Stop Loss",
};

const PERCENT_PARAMS = new Set(["threshold", "allocation", "stop_loss"]);

function formatParam(key: string, v: number): string {
  return PERCENT_PARAMS.has(key) ? `${+(v * 100).toFixed(2)}%` : String(v);
}

const SIGNAL_TONE: Record<Signal, "accent" | "danger" | "muted"> = {
  BUY: "accent",
  SELL: "danger",
  HOLD: "muted",
};

interface Props {
  /** Live strategy from the executor, with its signals. */
  live: StrategyView | null;
  /** Strategy the router would pick for the detected regime, shown before START. */
  preview: Strategy | null;
  running: boolean;
}

export function StrategyCard({ live, preview, running }: Props) {
  const s: Strategy | null = live ?? preview;
  if (!s)
    return (
      <Panel className="border">
        <PanelLabel>Active Strategy</PanelLabel>
        <Empty>Waiting for the first regime detection.</Empty>
      </Panel>
    );
  const style = REGIMES[s.regime];
  const signals = live?.recent_signals ?? [];

  return (
    <Panel className="border">
      <PanelLabel
        right={
          <Badge tone={live && running ? "accent" : "muted"}>
            {live ? (running ? "active" : "stopped") : "standby"}
          </Badge>
        }
      >
        Active Strategy
      </PanelLabel>
      <div className="grid gap-6 p-4 lg:grid-cols-3">
        <div className="flex flex-col gap-2">
          <h3 className="font-mono text-lg font-bold text-fg">{s.name}</h3>
          <span
            className={cn(
              "w-fit border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em]",
              style.border,
              style.text,
              style.tint,
            )}
          >
            for {style.label}
          </span>
          <p className="text-sm leading-relaxed text-muted">{s.description}</p>
          {!live && (
            <p className="font-mono text-[11px] text-muted">
              Router pick for the detected regime. Press START to run it.
            </p>
          )}
        </div>
        <div>
          <h4 className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-muted">Parameters</h4>
          <table className="w-full font-mono text-[11px]">
            <tbody>
              {Object.entries(s.parameters).map(([k, v]) => (
                <tr key={k} className="border-b border-line last:border-0">
                  <td className="py-1.5 text-muted">{PARAM_LABELS[k] ?? k}</td>
                  <td className="tabular py-1.5 text-right text-fg">{formatParam(k, v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h4 className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
            Last 5 Signals
          </h4>
          {signals.length === 0 ? (
            <p className="font-mono text-[11px] text-muted">No signals yet.</p>
          ) : (
            <ul className="flex flex-col">
              {signals.map((x, i) => (
                <li
                  key={`${x.timestamp}-${i}`}
                  className="flex items-center justify-between border-b border-line py-1.5 font-mono text-[11px] last:border-0"
                >
                  <span className="text-muted">{formatTime(x.timestamp)}</span>
                  <Badge tone={SIGNAL_TONE[x.signal]}>{x.signal}</Badge>
                  <span className="tabular text-fg">{formatNum(x.price)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Panel>
  );
}
