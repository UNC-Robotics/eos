'use client';

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import type { TaskStatus } from '@/lib/types/api';

export interface TaskStatusNodeData extends Record<string, unknown> {
  name: string;
  type: string;
  status: TaskStatus;
}

const STATUS_COLORS: Record<TaskStatus, { border: string; bg: string; text: string }> = {
  CREATED: {
    border: 'border-gray-400 dark:border-gray-500',
    bg: 'bg-gray-50 dark:bg-gray-800',
    text: 'text-gray-700 dark:text-gray-300',
  },
  RUNNING: {
    border: 'border-blue-500 dark:border-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-900',
    text: 'text-blue-700 dark:text-blue-300',
  },
  COMPLETED: {
    border: 'border-green-500 dark:border-green-400',
    bg: 'bg-green-50 dark:bg-green-900',
    text: 'text-green-700 dark:text-green-300',
  },
  FAILED: {
    border: 'border-red-500 dark:border-red-400',
    bg: 'bg-red-50 dark:bg-red-900',
    text: 'text-red-700 dark:text-red-300',
  },
  CANCELLED: {
    border: 'border-orange-500 dark:border-orange-400',
    bg: 'bg-orange-50 dark:bg-orange-900',
    text: 'text-orange-700 dark:text-orange-300',
  },
};

const TaskStatusNodeComponent = ({ data, selected }: NodeProps) => {
  const { name, type, status } = data as TaskStatusNodeData;
  const colors = STATUS_COLORS[status];

  return (
    <div
      className={`
        relative px-4 py-3 rounded-lg border-2 min-w-[180px] transition-all cursor-pointer
        ${colors.border} ${colors.bg}
        ${selected ? 'ring-2 ring-blue-500 ring-offset-2 shadow-lg' : 'shadow-md hover:shadow-lg'}
      `}
    >
      {/* Target handle (left side) for incoming dependencies */}
      <Handle
        type="target"
        position={Position.Left}
        style={{
          width: 8,
          height: 8,
          background: '#3b82f6',
          border: '2px solid white',
        }}
      />

      <div className="flex flex-col gap-1">
        <div className={`font-semibold text-sm ${colors.text}`}>{name}</div>
        <div className="text-xs text-gray-500 dark:text-gray-400">{type}</div>
        <div className={`text-xs font-medium ${colors.text} uppercase tracking-wide`}>{status}</div>
      </div>

      {/* Source handle (right side) for outgoing dependencies */}
      <Handle
        type="source"
        position={Position.Right}
        style={{
          width: 8,
          height: 8,
          background: '#3b82f6',
          border: '2px solid white',
        }}
      />
    </div>
  );
};

export const TaskStatusNode = memo(TaskStatusNodeComponent);
