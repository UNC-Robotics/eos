'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

export interface LogEntry {
  seq: number;
  t: number; // timestamp (epoch seconds)
  l: string; // level
  m: string; // message
  s: string; // source (filename:lineno)
}

interface UseLogStreamOptions {
  level?: string;
  enabled?: boolean;
  maxEntries?: number;
}

export function useLogStream(options: UseLogStreamOptions = {}) {
  const { level = 'INFO', enabled = true, maxEntries = 1000 } = options;
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  const clear = useCallback(() => setEntries([]), []);

  useEffect(() => {
    if (!enabled) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
        setConnected(false);
      }
      return;
    }

    // Start fresh on (re)subscribe so a level change re-filters the visible log
    // instead of leaving stale entries from the previous level.
    setEntries([]);

    const params = new URLSearchParams();
    if (level) params.set('level', level);

    // Same-origin proxy (app/api/logs/stream) injects the bearer token server-side; EventSource can't set headers
    const url = `/api/logs/stream?${params.toString()}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    // Batch incoming events so a burst yields one render per animation frame
    // instead of one per entry.
    let pending: LogEntry[] = [];
    let rafId: number | null = null;

    const flush = () => {
      rafId = null;
      if (pending.length === 0) return;
      const batch = pending;
      pending = [];
      setEntries((prev) => {
        const next =
          prev.length + batch.length > maxEntries ? [...prev, ...batch].slice(-maxEntries) : [...prev, ...batch];
        return next;
      });
    };

    es.onopen = () => setConnected(true);

    es.addEventListener('log', (event) => {
      const entry: LogEntry = JSON.parse(event.data);
      pending.push(entry);
      if (rafId === null) rafId = requestAnimationFrame(flush);
    });

    es.onerror = () => {
      setConnected(false);
    };

    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      pending = [];
      es.close();
      setConnected(false);
    };
  }, [level, enabled, maxEntries]);

  return { entries, connected, clear };
}
