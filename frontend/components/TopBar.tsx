"use client";

import { Button } from "@/components/ui/button";
import type { Mode } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  running: boolean;
  busy: boolean;
  mode: Mode;
  onMode: (m: Mode) => void;
  onStart: () => void;
  onStop: () => void;
}

export function TopBar({ running, busy, mode, onMode, onStart, onStop }: Props) {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="font-mono text-xl font-black tracking-[0.3em] text-fg">MIREN</span>
          <span
            className={cn("h-2 w-2 rounded-full", running ? "animate-blink bg-accent" : "bg-danger")}
            aria-label={running ? "running" : "stopped"}
          />
          <span className="hidden truncate font-mono text-[10px] uppercase tracking-[0.18em] text-muted sm:inline">
            Autonomous Regime-Adaptive Trading
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex border border-line" role="radiogroup" aria-label="Trading mode">
            {(["PAPER", "LIVE"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={mode === m}
                disabled={running}
                onClick={() => onMode(m)}
                className={cn(
                  "h-8 px-3 font-mono text-[10px] font-bold tracking-[0.14em] transition-colors disabled:cursor-not-allowed",
                  mode === m
                    ? m === "LIVE"
                      ? "bg-warn text-black"
                      : "bg-raised text-fg"
                    : "text-muted hover:text-fg",
                )}
              >
                {m}
              </button>
            ))}
          </div>
          <Button size="sm" variant="primary" onClick={onStart} disabled={running || busy}>
            Start
          </Button>
          <Button size="sm" variant="danger" onClick={onStop} disabled={!running || busy}>
            Stop
          </Button>
        </div>
      </div>
    </header>
  );
}
