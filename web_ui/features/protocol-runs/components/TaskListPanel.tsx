'use client';

import { useState, useMemo } from 'react';
import { X, Search } from 'lucide-react';
import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import type { TaskStatusInfo } from '../api/protocolRunDetails';

interface TaskListPanelProps {
  taskStatuses: TaskStatusInfo[];
  selectedTaskName: string | null;
  onTaskSelect: (taskName: string) => void;
  onClose: () => void;
}

export function TaskListPanel({ taskStatuses, selectedTaskName, onTaskSelect, onClose }: TaskListPanelProps) {
  const [search, setSearch] = useState('');

  const filteredTasks = useMemo(() => {
    if (!search) return taskStatuses;
    const q = search.toLowerCase();
    return taskStatuses.filter(
      (t) => t.name.toLowerCase().includes(q) || t.type.toLowerCase().includes(q) || t.status.toLowerCase().includes(q)
    );
  }, [taskStatuses, search]);

  return (
    <div className="w-96 border-l border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-y-auto">
      <div className="sticky top-0 bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-700 p-4 z-10 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Tasks</h2>
          <button
            onClick={onClose}
            className="rounded-sm opacity-70 ring-offset-white dark:ring-offset-slate-900 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 text-gray-900 dark:text-gray-400"
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Close</span>
          </button>
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
          <input
            type="text"
            placeholder="Search tasks..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
      </div>

      <div className="p-2">
        {filteredTasks.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 p-2">No tasks found.</p>
        ) : (
          filteredTasks.map((task) => (
            <button
              key={task.name}
              onClick={() => onTaskSelect(task.name)}
              className={`w-full text-left px-3 py-2.5 rounded-md transition-colors ${
                selectedTaskName === task.name
                  ? 'bg-blue-50 dark:bg-blue-900/30'
                  : 'hover:bg-gray-50 dark:hover:bg-slate-800'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-medium text-sm text-gray-900 dark:text-white truncate">{task.name}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{task.type}</div>
                </div>
                <Badge variant={getStatusBadgeVariant(task.status)} className="flex-shrink-0">
                  {task.status}
                </Badge>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
