'use client';

import { memo } from 'react';
import { X, AlertTriangle, Globe } from 'lucide-react';
import { useEditorStore } from '@/lib/stores/editorStore';

interface ValidationErrorsPanelProps {
  onSelectTask: (taskName: string) => void;
}

export const ValidationErrorsPanel = memo(function ValidationErrorsPanel({ onSelectTask }: ValidationErrorsPanelProps) {
  const validationErrors = useEditorStore((state) => state.validationErrors);
  const isValidationPanelOpen = useEditorStore((state) => state.isValidationPanelOpen);
  const setIsValidationPanelOpen = useEditorStore((state) => state.setIsValidationPanelOpen);

  if (!isValidationPanelOpen || validationErrors.length === 0) return null;

  // Group errors: per-task and general
  const taskErrors: Record<string, string[]> = {};
  const generalErrors: string[] = [];

  for (const error of validationErrors) {
    if (error.task) {
      if (!taskErrors[error.task]) taskErrors[error.task] = [];
      taskErrors[error.task].push(error.message);
    } else {
      generalErrors.push(error.message);
    }
  }

  return (
    <div className="border-t border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 max-h-48 overflow-y-auto">
      {/* Header */}
      <div className="sticky top-0 z-10 flex items-center justify-between px-4 py-1.5 bg-red-50 dark:bg-red-950/30 border-b border-red-200 dark:border-red-900/50">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-red-600 dark:text-red-400" />
          <span className="text-xs font-semibold text-red-700 dark:text-red-400">
            {validationErrors.length} validation {validationErrors.length === 1 ? 'error' : 'errors'}
          </span>
        </div>
        <button
          onClick={() => setIsValidationPanelOpen(false)}
          className="text-red-400 dark:text-red-500 hover:text-red-600 dark:hover:text-red-300 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Error list */}
      <div className="divide-y divide-gray-100 dark:divide-slate-800">
        {/* General errors */}
        {generalErrors.map((message, i) => (
          <div key={`general-${i}`} className="flex items-start gap-2 px-4 py-2">
            <Globe className="w-3.5 h-3.5 mt-0.5 text-red-500 dark:text-red-400 flex-shrink-0" />
            <span className="text-xs text-red-700 dark:text-red-300">{message}</span>
          </div>
        ))}

        {/* Per-task errors */}
        {Object.entries(taskErrors).map(([taskName, messages]) => (
          <div key={taskName} className="px-4 py-2">
            <button
              onClick={() => onSelectTask(taskName)}
              className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline mb-1"
            >
              {taskName}
            </button>
            {messages.map((message, i) => (
              <div key={i} className="flex items-start gap-2 ml-2">
                <span className="text-red-400 dark:text-red-500 mt-0.5 flex-shrink-0">-</span>
                <span className="text-xs text-red-700 dark:text-red-300">{message}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
});
