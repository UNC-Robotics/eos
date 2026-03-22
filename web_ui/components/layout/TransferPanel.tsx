'use client';

import { useState } from 'react';
import { ArrowDown, ArrowUp, Check, AlertCircle, ChevronDown, ChevronUp, X } from 'lucide-react';
import { useTransferStore } from '@/lib/stores/transferStore';
import { formatBytes } from '@/lib/format';
import type { Transfer } from '@/lib/stores/transferStore';

function TransferRow({ transfer }: { transfer: Transfer }) {
  const removeTransfer = useTransferStore((s) => s.removeTransfer);

  const Icon = transfer.type === 'download' ? ArrowDown : ArrowUp;

  return (
    <div className="flex items-center gap-2 px-3 py-2 text-sm">
      {transfer.status === 'completed' ? (
        <Check className="w-4 h-4 text-green-500 flex-shrink-0" />
      ) : transfer.status === 'error' ? (
        <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
      ) : (
        <Icon className="w-4 h-4 text-blue-500 flex-shrink-0" />
      )}

      <div className="flex-1 min-w-0">
        <div className="truncate text-gray-900 dark:text-gray-100">{transfer.fileName}</div>
        {transfer.status === 'in_progress' && (
          <div className="mt-1 flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-gray-200 dark:bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-300"
                style={{ width: `${transfer.progress}%` }}
              />
            </div>
            <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0 w-8 text-right">
              {transfer.progress}%
            </span>
          </div>
        )}
        {transfer.status === 'in_progress' && transfer.bytesTotal > 0 && (
          <div className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            {formatBytes(transfer.bytesLoaded)} / {formatBytes(transfer.bytesTotal)}
          </div>
        )}
        {transfer.status === 'error' && <div className="text-xs text-red-500 mt-0.5">{transfer.error}</div>}
      </div>

      {(transfer.status === 'completed' || transfer.status === 'error') && (
        <button
          onClick={() => removeTransfer(transfer.id)}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 flex-shrink-0"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

export function TransferPanel() {
  const transfers = useTransferStore((s) => s.transfers);
  const clearCompleted = useTransferStore((s) => s.clearCompleted);
  const [collapsed, setCollapsed] = useState(false);

  if (transfers.length === 0) return null;

  const hasCompleted = transfers.some((t) => t.status === 'completed');

  return (
    <div className="fixed bottom-4 right-4 w-80 bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-lg shadow-xl z-50 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-slate-800 border-b border-gray-200 dark:border-slate-700 cursor-pointer select-none"
        onClick={() => setCollapsed(!collapsed)}
      >
        <span className="text-sm font-medium text-gray-900 dark:text-white">Transfers ({transfers.length})</span>
        <div className="flex items-center gap-1">
          {hasCompleted && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                clearCompleted();
              }}
              className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 mr-1"
            >
              Clear done
            </button>
          )}
          {collapsed ? (
            <ChevronUp className="w-4 h-4 text-gray-500" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-500" />
          )}
        </div>
      </div>

      {/* Transfer list */}
      {!collapsed && (
        <div className="max-h-60 overflow-y-auto divide-y divide-gray-100 dark:divide-slate-800">
          {transfers.map((transfer) => (
            <TransferRow key={transfer.id} transfer={transfer} />
          ))}
        </div>
      )}
    </div>
  );
}
