import { Panel } from "@/components/ui/panel";
import type { ExecutorStatus } from "@/lib/types";
import { cn, signedINR, signedPct, since } from "@/lib/utils";

function Tile({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "up" | "down";
}) {
  return (
    <div className="flex min-w-0 flex-col justify-between gap-2 border border-line bg-surface p-4">
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">{label}</span>
      <span
        className={cn(
          "tabular truncate font-mono text-xl font-bold sm:text-2xl",
          tone === "up" ? "text-accent" : tone === "down" ? "text-danger" : "text-fg",
        )}
      >
        {value}
      </span>
      <span className="truncate font-mono text-[10px] text-muted">{sub ?? " "}</span>
    </div>
  );
}

export function MetricsGrid({ status, now }: { status: ExecutorStatus; now: number }) {
  const live = status.started_at !== null;
  const pnl = status.current_pnl;
  const pnlPct = status.capital ? (pnl / status.capital) * 100 : 0;
  return (
    <Panel className="grid grid-cols-2 gap-px bg-line lg:col-span-2">
      <Tile
        label="Current P&L"
        value={live ? signedINR(pnl) : "n/a"}
        sub={live ? `${signedPct(pnlPct)} of capital` : "start to trade"}
        tone={!live || pnl === 0 ? undefined : pnl > 0 ? "up" : "down"}
      />
      <Tile
        label="Sharpe Ratio"
        value={status.sharpe === null ? "n/a" : status.sharpe.toFixed(2)}
        sub={status.sharpe === null ? "needs 5 daily marks" : "annualised, daily"}
      />
      <Tile
        label="Regime Switches"
        value={String(status.regime_switches)}
        sub={`${status.total_trades} trade${status.total_trades === 1 ? "" : "s"}`}
      />
      <Tile
        label="Active Since"
        value={status.started_at && status.status !== "STOPPED" ? since(status.started_at, now) : "n/a"}
        sub={status.symbol ? `${status.symbol} · ${status.mode}` : "idle"}
      />
    </Panel>
  );
}
