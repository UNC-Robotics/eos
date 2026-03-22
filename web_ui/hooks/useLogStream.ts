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

const ORCHESTRATOR_URL = process.env.NEXT_PUBLIC_ORCHESTRATOR_API_URL || 'http://localhost:8070/api';

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

    const params = new URLSearchParams();
    if (level) params.set('level', level);

    const url = `${ORCHESTRATOR_URL}/logs/stream?${params.toString()}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => setConnected(true);

    es.addEventListener('log', (event) => {
      const entry: LogEntry = JSON.parse(event.data);
      setEntries((prev) => {
        const next = [...prev, entry];
        return next.length > maxEntries ? next.slice(-maxEntries) : next;
      });
    });

    es.onerror = () => {
      setConnected(false);
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, [level, enabled, maxEntries]);

  return { entries, connected, clear };
}
