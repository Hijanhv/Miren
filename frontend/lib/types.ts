/** Mirrors backend/models.py. */

export type RegimeType = "TRENDING" | "MEAN_REVERTING" | "VOLATILE" | "CALM";
export type Signal = "BUY" | "SELL" | "HOLD";
export type Mode = "PAPER" | "LIVE";
export type RunState = "IDLE" | "DETECTING" | "RUNNING" | "STOPPED" | "ERROR";
export type EventKind = "START" | "STOP" | "REGIME_CHANGE" | "REGIME_HELD" | "ORDER" | "STOP_LOSS" | "ERROR";

export type FeatureValue = number | string | boolean | null;

export interface Regime {
  type: RegimeType;
  confidence: number;
  detected_at: string;
  features: Record<string, FeatureValue>;
}

export interface Strategy {
  name: string;
  regime: RegimeType;
  description: string;
  parameters: Record<string, number>;
}

export interface SignalRecord {
  timestamp: string;
  signal: Signal;
  price: number;
  strategy: string;
}

export interface StrategyView extends Strategy {
  recent_signals: SignalRecord[];
}

export interface ExecutorStatus {
  symbol: string | null;
  mode: Mode;
  active_regime: RegimeType | null;
  active_strategy: string | null;
  status: RunState;
  current_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  capital: number;
  position_qty: number;
  position_avg_price: number | null;
  last_price: number | null;
  sharpe: number | null;
  total_trades: number;
  regime_switches: number;
  started_at: string | null;
  last_tick_at: string | null;
  next_tick_at: string | null;
  error: string | null;
}

export interface MirenEvent {
  timestamp: string;
  kind: EventKind;
  message: string;
  regime: RegimeType | null;
}

export interface LiveSnapshot {
  status: ExecutorStatus;
  regime: Regime | null;
  strategy: StrategyView | null;
  events: MirenEvent[];
}

export interface Bar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface TimelineDay {
  date: string;
  close: number;
  regime: RegimeType;
  confidence: number;
  strategy: string;
  position: number;
  pnl_pct: number;
}

export interface RegimeAnalysis {
  symbol: string;
  bars: Bar[];
  timeline: TimelineDay[];
  current: Regime;
  replay_return_pct: number;
  buy_hold_return_pct: number;
  note: string;
}

export interface Health {
  status: string;
  executor_running: boolean;
  dhan_configured: boolean;
}

export interface StartBody {
  symbol: string;
  capital: number;
  mode: Mode;
  security_id?: string;
  confirm_live?: boolean;
}

export interface StartResponse {
  status: string;
  symbol: string;
  mode: Mode;
}
