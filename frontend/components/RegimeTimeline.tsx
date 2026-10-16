"use client";

import { useState } from "react";

import { Panel, PanelLabel } from "@/components/ui/panel";
import { REGIMES } from "@/lib/regime";
import type { TimelineDay } from "@/lib/types";
import { cn, formatDate, signedPct } from "@/lib/utils";

const DAYS = 30;

export function RegimeTimeline({ timeline, loading }: { timeline: TimelineDay[]; loading: boolean }) {
  const days = timeline.slice(-DAYS);
  const [picked, setPicked] = useState<number | null>(null);
  const active = picked !== null ? days[picked] : days[days.length - 1];
  const total = days.reduce((acc, d) => acc * (1 + d.pnl_pct / 100), 1);

  return (
    <Panel className="border">
      <PanelLabel
        right={
          days.length > 0 && (
            <span className="font-mono text-[10px] text-muted">
              replay {DAYS}d{" "}
              <span className={total >= 1 ? "text-accent" : "text-danger"}>
                {signedPct((total - 1) * 100)}
              </span>
            </span>
          )
        }
      >
        Regime Timeline · {DAYS} Days
      </PanelLabel>
      <div className="flex flex-col gap-4 p-4">
        {loading ? (
          <div className="skeleton h-14 w-full" />
        ) : (
          <div className="flex h-14 w-full gap-[2px]" onMouseLeave={() => setPicked(null)}>
            {days.map((d, i) => (
              <button
                key={d.date}
                type="button"
                aria-label={`${d.date} ${d.regime}`}
                onMouseEnter={() => setPicked(i)}
                onFocus={() => setPicked(i)}
                onClick={() => setPicked(i)}
                className={cn(
                  "relative h-full flex-1 transition-opacity focus-visible:outline-none",
                  picked !== null && picked !== i && "opacity-40",
                )}
                style={{ background: REGIMES[d.regime].color }}
              >
                {d.position === 1 && (
                  <span className="absolute bottom-1 left-1/2 h-1 w-1 -translate-x-1/2 bg-black/70" />
                )}
              </button>
            ))}
          </div>
        )}
        {days.length > 0 && (
          <div className="flex justify-between font-mono text-[10px] text-muted">
            <span>{formatDate(days[0]?.date ?? "")}</span>
            <span>dot = long at close</span>
            <span>{formatDate(days[days.length - 1]?.date ?? "")}</span>
          </div>
        )}
        {active && !loading && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 border border-line bg-bg p-3 font-mono text-[11px] sm:grid-cols-4">
            <div>
              <dt className="text-[10px] uppercase tracking-wider text-muted">Date</dt>
              <dd className="text-fg">{formatDate(active.date)}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wider text-muted">Regime</dt>
              <dd className={REGIMES[active.regime].text}>
                {REGIMES[active.regime].label} {Math.round(active.confidence * 100)}%
              </dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wider text-muted">Strategy</dt>
              <dd className="text-fg">{active.strategy}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wider text-muted">Day P&L</dt>
              <dd
                className={
                  active.pnl_pct > 0 ? "text-accent" : active.pnl_pct < 0 ? "text-danger" : "text-muted"
                }
              >
                {signedPct(active.pnl_pct, 2)}
              </dd>
            </div>
          </dl>
        )}
      </div>
    </Panel>
  );
}
