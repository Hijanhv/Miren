import { Empty, Panel, PanelLabel } from "@/components/ui/panel";
import { REGIMES } from "@/lib/regime";
import type { EventKind, MirenEvent } from "@/lib/types";
import { cn, formatTime } from "@/lib/utils";

const KIND_CLASS: Partial<Record<EventKind, string>> = {
  ERROR: "text-danger",
  STOP_LOSS: "text-warn",
  REGIME_HELD: "text-muted",
  START: "text-fg",
  STOP: "text-fg",
};

export function EventLog({ events, connected }: { events: MirenEvent[]; connected: boolean }) {
  return (
    <Panel className="border">
      <PanelLabel
        right={
          <span className="inline-flex items-center gap-1.5 font-mono text-[10px] text-muted">
            <span
              className={cn("h-1.5 w-1.5 rounded-full", connected ? "animate-blink bg-accent" : "bg-danger")}
            />
            {connected ? "live" : "reconnecting"}
          </span>
        }
      >
        Event Log
      </PanelLabel>
      <div className="h-[260px] overflow-y-auto">
        {events.length === 0 ? (
          <Empty>No events yet. Press START and Miren logs every regime change, switch and order here.</Empty>
        ) : (
          <ol className="divide-y divide-line">
            {events.map((e, i) => {
              const color = e.regime ? REGIMES[e.regime] : null;
              return (
                <li
                  key={`${e.timestamp}-${i}`}
                  className="flex gap-3 border-l-2 px-3 py-2 font-mono text-[11px] leading-relaxed"
                  style={{ borderLeftColor: color ? color.color : "transparent" }}
                >
                  <span className="shrink-0 text-muted">[{formatTime(e.timestamp)}]</span>
                  <span
                    className={cn(
                      "min-w-0 break-words",
                      KIND_CLASS[e.kind] ?? (color ? color.text : "text-fg"),
                    )}
                  >
                    {e.message}
                  </span>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </Panel>
  );
}
