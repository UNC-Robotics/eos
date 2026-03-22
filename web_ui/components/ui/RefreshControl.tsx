'use client';

import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { RefreshCw, ChevronDown } from 'lucide-react';

const DEFAULT_INTERVALS = [
  { label: 'Off', value: 0 },
  { label: '1s', value: 1000 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
];

interface RefreshControlProps {
  pollingInterval: number;
  onIntervalChange: (value: number) => void;
  onRefresh: () => void;
  isRefreshing?: boolean;
  disabled?: boolean;
  intervals?: { label: string; value: number }[];
}

export function RefreshControl({
  pollingInterval,
  onIntervalChange,
  onRefresh,
  isRefreshing = false,
  disabled = false,
  intervals = DEFAULT_INTERVALS,
}: RefreshControlProps) {
  const currentLabel = intervals.find((i) => i.value === pollingInterval)?.label || 'Off';

  return (
    <div className="inline-flex items-center rounded-md border border-gray-300 dark:border-slate-600 overflow-hidden">
      <button
        onClick={onRefresh}
        disabled={disabled || isRefreshing}
        className="inline-flex items-center gap-1.5 h-8 px-2.5 text-sm font-medium transition-colors bg-transparent hover:bg-gray-100 dark:hover:bg-slate-800 dark:text-gray-300 disabled:pointer-events-none disabled:opacity-50"
      >
        <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
        Refresh
      </button>

      <div className="w-px h-5 bg-gray-300 dark:bg-slate-600" />

      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            disabled={disabled}
            className="inline-flex items-center gap-1 h-8 px-2 text-sm font-medium transition-colors bg-transparent hover:bg-gray-100 dark:hover:bg-slate-800 dark:text-gray-300 disabled:pointer-events-none disabled:opacity-50"
          >
            <span className="text-xs">{currentLabel}</span>
            <ChevronDown className="h-3 w-3" />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            className="w-32 rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-1 shadow-md z-50"
          >
            <div className="px-2 py-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">Auto-refresh</div>
            {intervals.map((interval) => (
              <DropdownMenu.Item
                key={interval.value}
                className={`relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-gray-100 dark:hover:bg-slate-700 focus:bg-gray-100 dark:focus:bg-slate-700 dark:text-gray-300 ${
                  pollingInterval === interval.value ? 'bg-gray-100 dark:bg-slate-700 font-medium' : ''
                }`}
                onClick={() => onIntervalChange(interval.value)}
              >
                {interval.label}
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </div>
  );
}
