"use client";

import { ColorType, createChart, type Time } from "lightweight-charts";
import { useEffect, useRef } from "react";

import { REGIMES, REGIME_ORDER, withAlpha } from "@/lib/regime";
import type { RegimeAnalysis, RegimeType } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  analysis: RegimeAnalysis;
  /** Live regime from the executor, if running; otherwise the analysis' latest label is shown. */
  liveRegime: RegimeType | null;
}

export function PriceChart({ analysis, liveRegime }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const bandsRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        // transparent so the regime band canvas underneath shows through
        background: { type: ColorType.Solid, color: "rgba(0,0,0,0)" },
        textColor: "#888888",
        fontFamily: "var(--font-mono), monospace",
        fontSize: 10,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "#161616" } },
      rightPriceScale: { borderColor: "#1f1f1f" },
      timeScale: { borderColor: "#1f1f1f" },
      crosshair: {
        vertLine: { color: "#2f2f2f", labelBackgroundColor: "#1f1f1f" },
        horzLine: { color: "#2f2f2f", labelBackgroundColor: "#1f1f1f" },
      },
      handleScale: { axisPressedMouseMove: false },
    });

    const price = chart.addAreaSeries({
      lineColor: "#e5e5e5",
      topColor: "rgba(229,229,229,0.10)",
      bottomColor: "rgba(0,0,0,0)",
      lineWidth: 2,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    price.setData(analysis.bars.map((b) => ({ time: b.date as Time, value: b.close })));

    // regime bands: contiguous runs of one regime, painted on a canvas behind the series
    const runs: { from: string; to: string; regime: RegimeType }[] = [];
    for (const d of analysis.timeline) {
      const last = runs[runs.length - 1];
      if (last && last.regime === d.regime) last.to = d.date;
      else runs.push({ from: d.date, to: d.date, regime: d.regime });
    }
    const canvas = bandsRef.current;
    const paint = (): void => {
      if (!canvas) return;
      const ts = chart.timeScale();
      const dpr = window.devicePixelRatio || 1;
      const w = el.clientWidth;
      const h = el.clientHeight - ts.height();
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const plotWidth = w - chart.priceScale("right").width();
      const half = ts.options().barSpacing / 2;
      for (const r of runs) {
        const x1 = ts.timeToCoordinate(r.from as Time);
        const x2 = ts.timeToCoordinate(r.to as Time);
        if (x1 === null || x2 === null) continue;
        const left = Math.max(0, x1 - half);
        const right = Math.min(plotWidth, x2 + half);
        if (right <= left) continue;
        ctx.fillStyle = withAlpha(REGIMES[r.regime].color, 0.14);
        ctx.fillRect(left, 0, right - left, h);
      }
    };
    // repaints are batched into one animation frame and skipped once the chart is disposed,
    // otherwise a frame queued before chart.remove() touches a dead chart
    let frame = 0;
    let disposed = false;
    const repaint = (): void => {
      if (disposed) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (!disposed) paint();
      });
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(repaint);
    const ro = new ResizeObserver(repaint);
    ro.observe(el);
    chart.timeScale().fitContent();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      ro.disconnect();
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(repaint);
      chart.remove();
    };
  }, [analysis]);

  const current = liveRegime ?? analysis.current.type;
  const style = REGIMES[current];

  return (
    <div className="relative h-[300px] w-full bg-surface sm:h-[380px]">
      <canvas ref={bandsRef} className="pointer-events-none absolute left-0 top-0" />
      <div ref={ref} className="relative h-full w-full" />
      <div
        className={cn(
          "pointer-events-none absolute right-16 top-10 border sm:top-3 px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.16em] backdrop-blur",
          style.border,
          style.text,
          style.tint,
        )}
      >
        Now: {style.label}
      </div>
      <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
        {REGIME_ORDER.map((r) => (
          <span key={r} className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2" style={{ background: REGIMES[r].color }} />
            {REGIMES[r].label}
          </span>
        ))}
      </div>
    </div>
  );
}
