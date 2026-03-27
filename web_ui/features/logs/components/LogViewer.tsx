'use client';

import * as React from 'react';
import { Trash2, Circle } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { useLogStream, type LogEntry } from '@/hooks/useLogStream';

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-cyan-600 dark:text-cyan-400',
  INFO: 'text-green-600 dark:text-green-400',
  WARNING: 'text-yellow-600 dark:text-yellow-400',
  ERROR: 'text-red-600 dark:text-red-400',
};

const LEVEL_OPTIONS = ['DEBUG', 'INFO', 'WARNING', 'ERROR'] as const;

interface LogViewerProps {
  enabled?: boolean;
  isResizing?: boolean;
  className?: string;
}

function formatTimestamp(epoch: number): string {
  const d = new Date(epoch * 1000);
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function LogLine({ entry }: { entry: LogEntry }) {
  return (
    <div className="flex gap-2 px-2 py-0.5 hover:bg-gray-50 dark:hover:bg-slate-800/50 text-[11px] leading-4">
      <span className="text-gray-400 dark:text-gray-500 shrink-0">{formatTimestamp(entry.t)}</span>
      <span className={`font-medium shrink-0 w-14 ${LEVEL_COLORS[entry.l] || 'text-gray-500'}`}>{entry.l}</span>
      <span className="text-gray-400 dark:text-gray-600 shrink-0">{entry.s}</span>
      <span className="text-gray-800 dark:text-gray-200 break-all">{entry.m}</span>
    </div>
  );
}

export function LogViewer({ enabled = true, isResizing = false, className = '' }: LogViewerProps) {
  const [level, setLevel] = React.useState<string>('INFO');
  const [autoScroll, setAutoScroll] = React.useState(true);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  const { entries, connected, clear } = useLogStream({ level, enabled });

  React.useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries, autoScroll]);

  const handleScroll = React.useCallback(() => {
    if (!scrollRef.current || isResizing) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40);
  }, [isResizing]);

  return (
    <div className={`flex flex-col h-full bg-white dark:bg-slate-900 ${className}`}>
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-2 py-1 border-b border-gray-200 dark:border-slate-700 shrink-0">
        <div className="flex items-center gap-1.5">
          <Circle
            className={`h-2.5 w-2.5 ${connected ? 'fill-green-500 text-green-500' : 'fill-red-500 text-red-500'}`}
          />
          <span className="text-[10px] text-gray-500 dark:text-gray-400">
            {connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>

        <select
          value={level}
          onChange={(e) => setLevel(e.target.value)}
          className="text-[11px] bg-transparent border border-gray-200 dark:border-slate-600 rounded px-1.5 py-0.5 text-gray-700 dark:text-gray-300"
        >
          {LEVEL_OPTIONS.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>

        <span className="text-[10px] text-gray-400 dark:text-gray-500 ml-auto">{entries.length} entries</span>

        <Button variant="ghost" size="sm" onClick={clear} className="h-5 w-5 p-0">
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>

      {/* Log entries */}
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto font-mono">
        {entries.length === 0 ? (
          <div className="flex items-center justify-center h-full text-xs text-gray-400 dark:text-gray-500">
            {enabled ? 'Waiting for log entries...' : 'Log streaming disabled'}
          </div>
        ) : (
          entries.map((entry, idx) => <LogLine key={`${entry.seq}-${idx}`} entry={entry} />)
        )}
      </div>
    </div>
  );
}
