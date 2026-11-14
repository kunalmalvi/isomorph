"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, tokenStore } from "@/services/api";
import { streamWithReconnect } from "@/services/sse";
import type { Progress } from "@/services/types";

export interface AsyncState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
}

/** Fetch on mount and whenever `deps` change. Ignores results from superseded requests. */
export function useAsync<T>(fn: () => Promise<T>, deps: ReadonlyArray<unknown>): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fnRef.current().then(
      (d) => {
        if (!cancelled) {
          setData(d);
          setLoading(false);
        }
      },
      (e) => {
        if (!cancelled) {
          setError(e);
          setLoading(false);
        }
      },
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

/** Subscribe to the discovery SSE endpoint. `progress` events carry the real stage statuses. */
export function useDiscoveryProgress(id: string | null, restartKey = 0): { progress: Progress | null; streamError: string | null } {
  const [progress, setProgress] = useState<Progress | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  useEffect(() => {
    if (!id) return;
    const ctrl = new AbortController();
    setStreamError(null);
    streamWithReconnect(
      api.discoveries.eventsUrl(id),
      tokenStore.get(),
      (m) => {
        if (m.event === "progress") setProgress(m.data as Progress);
        if (m.event === "error") setStreamError(String((m.data as { message?: string }).message ?? "stream error"));
      },
      ctrl.signal,
    ).catch((e: unknown) => {
      if (!ctrl.signal.aborted) setStreamError(e instanceof Error ? e.message : "stream failed");
    });
    return () => ctrl.abort();
  }, [id, restartKey]);
  return { progress, streamError };
}

/** Small localStorage backed state for browser only annotations. */
export function useLocalState<T>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(initial);
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw) setValue(JSON.parse(raw) as T);
    } catch {
      /* ignore corrupt value */
    }
  }, [key]);
  const set = useCallback(
    (v: T) => {
      setValue(v);
      window.localStorage.setItem(key, JSON.stringify(v));
    },
    [key],
  );
  return [value, set];
}
