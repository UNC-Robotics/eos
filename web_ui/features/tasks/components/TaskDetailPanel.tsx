'use client';

import * as ScrollArea from '@radix-ui/react-scroll-area';
import { X } from 'lucide-react';
import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import { JsonDisplay } from '@/components/ui/JsonDisplay';
import { TaskOutputFiles } from '@/features/files/components/TaskOutputFiles';
import type { Task } from '@/lib/types/api';

interface TaskDetailPanelProps {
  task: Task | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TaskDetailPanel({ task, open, onOpenChange }: TaskDetailPanelProps) {
  if (!task) return null;

  return (
    <div
      className={`absolute right-0 top-0 bottom-0 bg-white dark:bg-slate-900 shadow-2xl border-l border-gray-200 dark:border-slate-700 z-40 transition-transform duration-300 ease-in-out ${
        open ? 'translate-x-0' : 'translate-x-full'
      }`}
      style={{ width: '400px' }}
    >
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-gray-200 dark:border-slate-700 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">{task.name}</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">Task Details</p>
        </div>
        <button
          onClick={() => onOpenChange(false)}
          className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <ScrollArea.Root className="h-[calc(100%-57px)]">
        <ScrollArea.Viewport className="w-full h-full">
          <div className="p-4 space-y-6">
            {/* Basic Info */}
            <div className="space-y-3">
              <div>
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Type</div>
                <div className="mt-1 text-sm text-gray-900 dark:text-gray-100">{task.type}</div>
              </div>

              <div>
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Status
                </div>
                <div className="mt-1">
                  <Badge variant={getStatusBadgeVariant(task.status)}>{task.status}</Badge>
                </div>
              </div>

              {task.protocol_run_name && (
                <div>
                  <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Protocol Run
                  </div>
                  <div className="mt-1 text-sm text-gray-900 dark:text-gray-100">{task.protocol_run_name}</div>
                </div>
              )}

              <div>
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Priority
                </div>
                <div className="mt-1 text-sm text-gray-900 dark:text-gray-100">{task.priority}</div>
              </div>

              <div>
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Allocation Timeout
                </div>
                <div className="mt-1 text-sm text-gray-900 dark:text-gray-100">{task.allocation_timeout}s</div>
              </div>
            </div>

            {/* Timestamps */}
            <div className="border-t border-gray-200 dark:border-slate-700 pt-4 space-y-2">
              <div className="text-sm font-medium text-gray-900 dark:text-white">Timeline</div>
              <div className="space-y-1 text-xs">
                <div>
                  <span className="text-gray-500 dark:text-gray-400">Created:</span>{' '}
                  <span className="text-gray-900 dark:text-gray-100">{new Date(task.created_at).toLocaleString()}</span>
                </div>
                {task.start_time && (
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Started:</span>{' '}
                    <span className="text-gray-900 dark:text-gray-100">
                      {new Date(task.start_time).toLocaleString()}
                    </span>
                  </div>
                )}
                {task.end_time && (
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Ended:</span>{' '}
                    <span className="text-gray-900 dark:text-gray-100">{new Date(task.end_time).toLocaleString()}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Devices */}
            {task.devices && Object.keys(task.devices).length > 0 && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <JsonDisplay data={task.devices} label="Devices" />
              </div>
            )}

            {/* Input Parameters */}
            {task.input_parameters && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <JsonDisplay data={task.input_parameters} label="Input Parameters" />
              </div>
            )}

            {/* Input Resources */}
            {task.input_resources && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <JsonDisplay data={task.input_resources} label="Input Resources" />
              </div>
            )}

            {/* Output Parameters */}
            {task.output_parameters && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <JsonDisplay data={task.output_parameters} label="Output Parameters" />
              </div>
            )}

            {/* Output Resources */}
            {task.output_resources && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <JsonDisplay data={task.output_resources} label="Output Resources" />
              </div>
            )}

            {/* Output Files */}
            {task.output_file_names && task.output_file_names.length > 0 && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <TaskOutputFiles
                  fileNames={task.output_file_names}
                  protocolRunName={task.protocol_run_name ?? null}
                  taskName={task.name}
                />
              </div>
            )}

            {/* Metadata */}
            {task.meta && Object.keys(task.meta).length > 0 && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <JsonDisplay data={task.meta} label="Metadata" />
              </div>
            )}
          </div>
        </ScrollArea.Viewport>
        <ScrollArea.Scrollbar
          className="flex select-none touch-none p-0.5 bg-gray-100 dark:bg-slate-800 transition-colors duration-150 ease-out hover:bg-gray-200 dark:hover:bg-slate-700 data-[orientation=vertical]:w-2.5 data-[orientation=horizontal]:flex-col data-[orientation=horizontal]:h-2.5"
          orientation="vertical"
        >
          <ScrollArea.Thumb className="flex-1 bg-gray-400 dark:bg-slate-600 rounded-[10px] relative before:content-[''] before:absolute before:top-1/2 before:left-1/2 before:-translate-x-1/2 before:-translate-y-1/2 before:w-full before:h-full before:min-w-[44px] before:min-h-[44px]" />
        </ScrollArea.Scrollbar>
      </ScrollArea.Root>
    </div>
  );
}
