'use client';

import { X } from 'lucide-react';
import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import { DetailField, TimelineSection, ConditionalJsonSection } from './shared';
import { TaskOutputFiles } from '@/features/files/components/TaskOutputFiles';
import { SECTION_DIVIDER } from '../styles';
import type { Task } from '@/lib/types/api';

interface TaskDetailPanelProps {
  task: Task | null;
  onClose: () => void;
}

export function TaskDetailPanel({ task, onClose }: TaskDetailPanelProps) {
  if (!task) return null;

  const timelineEntries = [
    { label: 'Created', timestamp: task.created_at ?? null },
    { label: 'Started', timestamp: task.start_time ?? null },
    { label: 'Ended', timestamp: task.end_time ?? null },
  ];

  return (
    <div className="w-96 border-l border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-y-auto">
      <div className="sticky top-0 bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-700 p-4 z-10">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{task.name}</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">{task.type}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-sm opacity-70 ring-offset-white dark:ring-offset-slate-900 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 text-gray-900 dark:text-gray-400"
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Close</span>
          </button>
        </div>
      </div>

      <div className="p-4 space-y-6">
        <div className="space-y-3">
          <DetailField
            label="Status"
            value={<Badge variant={getStatusBadgeVariant(task.status)}>{task.status}</Badge>}
          />
          {task.status === 'FAILED' && task.error_message && (
            <div className="bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 rounded-lg p-3">
              <div className="text-xs font-medium text-red-800 dark:text-red-300 mb-1">Error</div>
              <p className="text-xs text-red-700 dark:text-red-400 whitespace-pre-wrap break-words font-mono">
                {task.error_message}
              </p>
            </div>
          )}
          <DetailField label="Priority" value={task.priority} />
          {task.protocol_run_name && <DetailField label="Protocol Run" value={task.protocol_run_name} />}
        </div>

        <div className={SECTION_DIVIDER}>
          <div className="text-sm font-medium text-gray-900 dark:text-white mb-2">Timeline</div>
          <TimelineSection entries={timelineEntries} />
        </div>

        <ConditionalJsonSection data={task.input_parameters} label="Input Parameters" />
        <ConditionalJsonSection data={task.input_resources} label="Input Resources" />
        <ConditionalJsonSection data={task.devices} label="Devices" />
        <ConditionalJsonSection data={task.output_parameters} label="Output Parameters" />
        <ConditionalJsonSection data={task.output_resources} label="Output Resources" />
        {task.output_file_names && task.output_file_names.length > 0 && (
          <div className={SECTION_DIVIDER}>
            <TaskOutputFiles
              fileNames={task.output_file_names}
              protocolRunName={task.protocol_run_name ?? null}
              taskName={task.name}
            />
          </div>
        )}
        <ConditionalJsonSection data={task.meta} label="Metadata" />
      </div>
    </div>
  );
}
