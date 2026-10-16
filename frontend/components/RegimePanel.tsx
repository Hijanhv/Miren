import { Panel, PanelLabel } from "@/components/ui/panel";
import { REGIMES } from "@/lib/regime";
import type { FeatureValue, Regime } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Row {
  label: string;
  value: string;
  tag: string;
  hot: boolean;
}

function num(v: FeatureValue | undefined): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Plain-language reading of the raw features that fed the detector. */
function rows(f: Record<string, FeatureValue>): Row[] {
  const out: Row[] = [];
  const adx = num(f.adx);
  if (adx !== null)
    out.push({
      label: "ADX",
      value: adx.toFixed(1),
      tag: adx > 25 ? "HIGH" : adx < 20 ? "LOW" : "MID",
      hot: adx > 25,
    });
  const ac = num(f.autocorrelation);
  if (ac !== null)
    out.push({
      label: "Autocorr",
      value: ac.toFixed(2),
      tag: ac > 0.1 ? "TRENDING" : ac < -0.1 ? "REVERTING" : "NEUTRAL",
      hot: Math.abs(ac) > 0.1,
    });
  const vol = num(f.realized_vol);
  if (vol !== null)
    out.push({
      label: "Realized Vol",
      value: `${(vol * 100).toFixed(1)}%`,
      tag: vol > 0.3 ? "HIGH" : vol < 0.15 ? "LOW" : "MID",
      hot: vol > 0.3,
    });
  const atr = num(f.atr_ratio);
  if (atr !== null)
    out.push({
      label: "ATR / Price",
      value: `${(atr * 100).toFixed(2)}%`,
      tag: atr > 0.025 ? "WIDE" : "NORMAL",
      hot: atr > 0.025,
    });
  const bbw = num(f.bb_width);
  if (bbw !== null)
    out.push({
      label: "BB Width",
      value: `${(bbw * 100).toFixed(1)}%`,
      tag: bbw < 0.06 ? "SQUEEZE" : "OPEN",
      hot: bbw < 0.06,
    });
  const rsi = num(f.rsi);
  if (rsi !== null)
    out.push({
      label: "RSI(14)",
      value: rsi.toFixed(1),
      tag: rsi > 70 ? "OVERBOUGHT" : rsi < 30 ? "OVERSOLD" : "NEUTRAL",
      hot: rsi > 70 || rsi < 30,
    });
  const vr = num(f.volume_ratio);
  if (vr !== null)
    out.push({
      label: "Volume Ratio",
      value: `${vr.toFixed(2)}x`,
      tag: vr > 1.5 ? "SURGE" : "NORMAL",
      hot: vr > 1.5,
    });
  return out;
}

export function RegimePanel({ regime, loading }: { regime: Regime | null; loading: boolean }) {
  if (loading || !regime) return <RegimeSkeleton />;
  const style = REGIMES[regime.type];
  const pct = Math.round(regime.confidence * 100);
  const kmeans = typeof regime.features.kmeans_regime === "string" ? regime.features.kmeans_regime : null;
  const agree = regime.features.models_agree === true;
  const asOf = typeof regime.features.as_of === "string" ? regime.features.as_of : null;

  return (
    <Panel className="border lg:col-span-2">
      <PanelLabel right={asOf && <span className="font-mono text-[10px] text-muted">bar {asOf}</span>}>
        Current Regime
      </PanelLabel>
      <div className="grid gap-5 p-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="flex flex-col gap-4">
          <span
            className={cn(
              "inline-flex w-fit items-center gap-2 rounded-full border px-4 py-2 font-mono text-lg font-bold uppercase tracking-[0.12em]",
              style.border,
              style.text,
              style.tint,
            )}
          >
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: style.color }} />
            {style.label}
          </span>
          <div>
            <div className="mb-1.5 flex justify-between font-mono text-[11px] text-muted">
              <span>HMM confidence</span>
              <span className="tabular text-fg">{pct}% confidence</span>
            </div>
            <div className="h-2 w-full bg-raised">
              <div className="h-full transition-all" style={{ width: `${pct}%`, background: style.color }} />
            </div>
          </div>
          {kmeans && (
            <p className="font-mono text-[11px] leading-relaxed text-muted">
              KMeans cross-check:{" "}
              <span className={agree ? "text-accent" : "text-warn"}>
                {kmeans.replace("_", " ")} {agree ? "(agrees)" : "(disagrees)"}
              </span>
            </p>
          )}
        </div>
        <table className="w-full font-mono text-[11px]">
          <tbody>
            {rows(regime.features).map((r) => (
              <tr key={r.label} className="border-b border-line last:border-0">
                <td className="py-1.5 text-muted">{r.label}</td>
                <td className="tabular py-1.5 text-right text-fg">{r.value}</td>
                <td
                  className={cn(
                    "py-1.5 pl-3 text-right text-[10px] tracking-wider",
                    r.hot ? style.text : "text-muted",
                  )}
                >
                  {r.tag}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function RegimeSkeleton() {
  return (
    <Panel className="border lg:col-span-2">
      <PanelLabel>Current Regime</PanelLabel>
      <div className="grid gap-5 p-4 sm:grid-cols-2">
        <div className="flex flex-col gap-4">
          <div className="skeleton h-11 w-44 rounded-full" />
          <div className="skeleton h-2 w-full" />
          <p className="font-mono text-[11px] text-muted">Fitting HMM and KMeans on the latest window...</p>
        </div>
        <div className="flex flex-col gap-2">
          {Array.from({ length: 7 }, (_, i) => (
            <div key={i} className="skeleton h-4 w-full" />
          ))}
        </div>
      </div>
    </Panel>
  );
}
