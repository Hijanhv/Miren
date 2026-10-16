import type { RegimeType } from "./types";

export interface RegimeStyle {
  label: string;
  color: string;
  /** Tailwind classes for text, border and tinted background. */
  text: string;
  border: string;
  tint: string;
}

export const REGIMES: Record<RegimeType, RegimeStyle> = {
  TRENDING: {
    label: "Trending",
    color: "#3b82f6",
    text: "text-regime-trending",
    border: "border-regime-trending/50",
    tint: "bg-regime-trending/10",
  },
  MEAN_REVERTING: {
    label: "Mean Reverting",
    color: "#a855f7",
    text: "text-regime-reverting",
    border: "border-regime-reverting/50",
    tint: "bg-regime-reverting/10",
  },
  VOLATILE: {
    label: "Volatile",
    color: "#ef4444",
    text: "text-regime-volatile",
    border: "border-regime-volatile/50",
    tint: "bg-regime-volatile/10",
  },
  CALM: {
    label: "Calm",
    color: "#22c55e",
    text: "text-regime-calm",
    border: "border-regime-calm/50",
    tint: "bg-regime-calm/10",
  },
};

export const REGIME_ORDER: RegimeType[] = ["TRENDING", "MEAN_REVERTING", "VOLATILE", "CALM"];

/** "#3b82f6" + 0.18 -> "rgba(59,130,246,0.18)" */
export function withAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}
