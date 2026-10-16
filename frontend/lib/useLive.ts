"use client";

import { useEffect, useRef, useState } from "react";

import { WS_URL } from "./api";
import type { LiveSnapshot } from "./types";

export type WsState = "connecting" | "open" | "closed";

const MAX_BACKOFF_MS = 15_000;

function isSnapshot(v: unknown): v is LiveSnapshot {
  return typeof v === "object" && v !== null && "status" in v && "events" in v;
}

/** Subscribes to /ws/live and reconnects with exponential backoff (1s, 2s, 4s ... 15s). */
export function useLive(): { snapshot: LiveSnapshot | null; state: WsState } {
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [state, setState] = useState<WsState>("connecting");
  const attempt = useRef(0);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;

    const connect = (): void => {
      if (disposed) return;
      setState("connecting");
      ws = new WebSocket(WS_URL);
      ws.onopen = () => {
        attempt.current = 0;
        setState("open");
      };
      ws.onmessage = (msg: MessageEvent<string>) => {
        try {
          const data: unknown = JSON.parse(msg.data);
          if (isSnapshot(data)) setSnapshot(data);
        } catch {
          // ignore malformed frames; the next push replaces them
        }
      };
      ws.onclose = () => {
        setState("closed");
        if (disposed) return;
        const delay = Math.min(1000 * 2 ** attempt.current, MAX_BACKOFF_MS);
        attempt.current += 1;
        timer = setTimeout(connect, delay);
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      ws?.close();
    };
  }, []);

  return { snapshot, state };
}
