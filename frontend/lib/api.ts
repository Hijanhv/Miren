import axios, { AxiosError } from "axios";

import type {
  ExecutorStatus,
  Health,
  Regime,
  RegimeAnalysis,
  StartBody,
  StartResponse,
  Strategy,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001").replace(/\/$/, "");
export const WS_URL = `${API_URL.replace(/^http/, "ws")}/ws/live`;

const http = axios.create({ baseURL: API_URL, timeout: 60_000 });

interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
}

interface ErrorBody {
  detail?: string | ValidationIssue[];
}

/** Turns axios and FastAPI errors into one readable line. */
export function errorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    if (!err.response) return `Cannot reach the Miren API at ${API_URL}`;
    const detail = (err.response.data as ErrorBody | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]) {
      const issue = detail[0];
      return `${issue.loc.slice(1).join(".")}: ${issue.msg}`;
    }
    return `Request failed (${err.response.status})`;
  }
  return err instanceof Error ? err.message : "Unknown error";
}

export const api = {
  health: async (): Promise<Health> => (await http.get<Health>("/health", { timeout: 5000 })).data,
  start: async (body: StartBody): Promise<StartResponse> =>
    (await http.post<StartResponse>("/start", body)).data,
  stop: async (): Promise<ExecutorStatus> => (await http.post<ExecutorStatus>("/stop")).data,
  status: async (): Promise<ExecutorStatus> => (await http.get<ExecutorStatus>("/status")).data,
  currentRegime: async (symbol: string): Promise<Regime> =>
    (await http.get<Regime>("/regime/current", { params: { symbol } })).data,
  analysis: async (symbol: string): Promise<RegimeAnalysis> =>
    (await http.get<RegimeAnalysis>("/regime/analysis", { params: { symbol } })).data,
  strategies: async (): Promise<Strategy[]> => (await http.get<Strategy[]>("/strategies")).data,
};
