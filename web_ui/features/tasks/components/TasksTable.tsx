'use client';

import * as React from 'react';
import { MoreHorizontal, X, Copy } from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { DataTable, DataTableColumnDef } from '@/components/data-table/DataTable';
import { Button } from '@/components/ui/Button';
import { RefreshControl } from '@/components/ui/RefreshControl';
import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import { JsonDisplay } from '@/components/ui/JsonDisplay';
import type { Task } from '@/lib/types/api';
import type { PaginatedResult } from '@/lib/db/queries';
import { cancelTask, getTasks } from '@/features/tasks/api/tasks';
import { generateCloneNameForEntity } from '@/lib/utils/naming.server';
import { useServerTable } from '@/hooks/useServerTable';
import { ConfirmDialog } from '@/components/dialogs/ConfirmDialog';
import { ErrorBox } from '@/components/ui/ErrorBox';
import { SubmitTaskDialog } from './SubmitTaskDialog';
import { TaskOutputFiles } from '@/features/files/components/TaskOutputFiles';
import type { TaskSpec } from '@/lib/types/protocol';
import type { LabSpec } from '@/lib/api/specs';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

const TASK_COLUMN_ID_MAP: Record<string, string> = {
  protocol_run_name: 'protocolRunName',
  created_at: 'createdAt',
};

interface TasksTableProps {
  initialData: PaginatedResult<Task>;
  taskSpecs: Record<string, TaskSpec>;
  labSpecs: Record<string, LabSpec>;
}

export function TasksTable({ initialData, taskSpecs, labSpecs }: TasksTableProps) {
  const { isConnected: _isConnected } = useOrchestratorConnected();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  const isConnected = mounted ? _isConnected : true; // Avoid hydration mismatch
  const [pollingInterval, setPollingInterval] = React.useState(5000);
  const [submitDialogOpen, setSubmitDialogOpen] = React.useState(false);
  const [cancellingTask, setCancellingTask] = React.useState<string | null>(null);
  const [selectedTask, setSelectedTask] = React.useState<Task | null>(null);
  const [detailPanelOpen, setDetailPanelOpen] = React.useState(false);
  const [taskToClone, setTaskToClone] = React.useState<Task | null>(null);
  const [taskToCancel, setTaskToCancel] = React.useState<{ name: string; protocolRunName: string | null } | null>(null);

  const serverTable = useServerTable({
    fetchFn: getTasks,
    initialData,
    columnIdMap: TASK_COLUMN_ID_MAP,
  });

  React.useEffect(() => {
    if (pollingInterval === 0) return;
    const intervalId = setInterval(() => {
      serverTable.refresh();
    }, pollingInterval);
    return () => clearInterval(intervalId);
  }, [pollingInterval, serverTable.refresh]); // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    if (selectedTask) {
      const updated = serverTable.data.find((t) => t.name === selectedTask.name);
      if (updated) setSelectedTask(updated);
    }
  }, [serverTable.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCancelTask = async () => {
    if (!taskToCancel) return;
    setCancellingTask(taskToCancel.name);
    try {
      const result = await cancelTask(taskToCancel.name, taskToCancel.protocolRunName);
      if (!result.success) {
        alert(`Failed to cancel task: ${result.error}`);
      }
    } finally {
      setCancellingTask(null);
      setTaskToCancel(null);
    }
  };

  const handleRowClick = (task: Task) => {
    setSelectedTask(task);
    setDetailPanelOpen(true);
  };

  const handleCloneTask = (task: Task) => {
    setTaskToClone(task);
    setSubmitDialogOpen(true);
  };

  const handleCloseSubmitDialog = (open: boolean) => {
    setSubmitDialogOpen(open);
  };

  const columns: DataTableColumnDef<Task>[] = [
    {
      accessorKey: 'name',
      header: 'Name',
      cell: ({ row }) => <div className="font-medium">{row.getValue('name')}</div>,
      enableColumnFilter: true,
      filterType: 'text',
    },
    {
      accessorKey: 'type',
      header: 'Type',
      enableColumnFilter: true,
      filterType: 'text',
    },
    {
      accessorKey: 'protocol_run_name',
      header: 'Protocol Run',
      cell: ({ row }) => {
        const exp = row.getValue('protocol_run_name') as string | null;
        return exp ? exp : <span className="text-gray-400">-</span>;
      },
      enableColumnFilter: true,
      filterType: 'text',
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const status = row.getValue('status') as string;
        return <Badge variant={getStatusBadgeVariant(status)}>{status}</Badge>;
      },
      enableColumnFilter: true,
      filterType: 'multiselect',
      filterOptions: ['CREATED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'],
      filterFn: 'arrIncludesSome',
    },
    {
      accessorKey: 'priority',
      header: 'Priority',
      enableColumnFilter: true,
      filterType: 'text',
    },
    {
      accessorKey: 'created_at',
      header: 'Created',
      cell: ({ row }) => {
        const date = new Date(row.getValue('created_at'));
        return date.toLocaleString();
      },
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => {
        const task = row.original;
        const canCancel = task.status === 'RUNNING' || task.status === 'CREATED';

        return (
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                <span className="sr-only">Open menu</span>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content className="w-48 rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-1 shadow-md z-50">
                <DropdownMenu.Item
                  className="relative flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-gray-100 dark:hover:bg-slate-700 focus:bg-gray-100 dark:focus:bg-slate-700 dark:text-gray-300"
                  onClick={() => handleCloneTask(task)}
                >
                  <Copy className="h-4 w-4" />
                  <span>Clone</span>
                </DropdownMenu.Item>
                {canCancel && (
                  <DropdownMenu.Item
                    className="relative flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-gray-100 dark:hover:bg-slate-700 focus:bg-gray-100 dark:focus:bg-slate-700 dark:text-gray-300"
                    onClick={() =>
                      setTaskToCancel({ name: task.name, protocolRunName: task.protocol_run_name ?? null })
                    }
                    disabled={cancellingTask === task.name || !isConnected}
                  >
                    <X className="h-4 w-4" />
                    <span>{cancellingTask === task.name ? 'Cancelling...' : 'Cancel Task'}</span>
                  </DropdownMenu.Item>
                )}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        );
      },
    },
  ];

  const toolbarActions = (
    <RefreshControl
      pollingInterval={pollingInterval}
      onIntervalChange={setPollingInterval}
      onRefresh={serverTable.refresh}
      isRefreshing={serverTable.isLoading}
    />
  );

  return (
    <div className="flex gap-4">
      <div className={`space-y-4 ${detailPanelOpen ? 'flex-1' : 'w-full'}`}>
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Tasks</h1>
            <p className="text-gray-600 dark:text-gray-400 mt-1">View and manage tasks</p>
          </div>
          <Button
            variant="primary"
            disabled={!isConnected}
            title={!isConnected ? 'Orchestrator offline' : undefined}
            onClick={() => {
              setTaskToClone(null);
              setSubmitDialogOpen(true);
            }}
          >
            Submit Task
          </Button>
        </div>

        <DataTable
          columns={columns}
          data={serverTable.data}
          searchPlaceholder="Search tasks..."
          onRowClick={handleRowClick}
          toolbarActions={toolbarActions}
          manualPagination
          totalRows={serverTable.totalRows}
          pageIndex={serverTable.pageIndex}
          pageSize={serverTable.pageSize}
          onPaginationChange={serverTable.onPaginationChange}
          onSortingChange={serverTable.onSortingChange}
          onColumnFiltersChange={serverTable.onColumnFiltersChange}
          onGlobalFilterChange={serverTable.onGlobalFilterChange}
        />

        <SubmitTaskDialog
          open={submitDialogOpen}
          onOpenChange={handleCloseSubmitDialog}
          onSuccess={() => setTimeout(() => serverTable.refresh(), 500)}
          taskSpecs={taskSpecs}
          labSpecs={labSpecs}
          initialTask={taskToClone}
          generateCloneName={(name) => generateCloneNameForEntity('tasks', name)}
        />
      </div>

      {detailPanelOpen && selectedTask && (
        <div className="w-96 border-l border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto self-start">
          <div className="flex items-start justify-between mb-6">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{selectedTask.name}</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">Task Details</p>
            </div>
            <button
              onClick={() => setDetailPanelOpen(false)}
              className="rounded-sm opacity-70 ring-offset-white dark:ring-offset-slate-900 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 text-gray-900 dark:text-gray-400"
            >
              <X className="h-4 w-4" />
              <span className="sr-only">Close</span>
            </button>
          </div>

          <div className="space-y-6">
            {/* Basic Info */}
            <div className="space-y-3">
              <div>
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Type</div>
                <div className="mt-1 text-sm text-gray-900 dark:text-gray-100">{selectedTask.type}</div>
              </div>

              <div>
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Status
                </div>
                <div className="mt-1">
                  <Badge variant={getStatusBadgeVariant(selectedTask.status)}>{selectedTask.status}</Badge>
                </div>
              </div>

              {selectedTask.status === 'FAILED' && selectedTask.error_message && (
                <ErrorBox error={selectedTask.error_message} />
              )}

              {selectedTask.protocol_run_name && (
                <div>
                  <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Protocol Run
                  </div>
                  <div className="mt-1 text-sm text-gray-900 dark:text-gray-100">{selectedTask.protocol_run_name}</div>
                </div>
              )}

              <div>
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Priority
                </div>
                <div className="mt-1 text-sm text-gray-900 dark:text-gray-100">{selectedTask.priority}</div>
              </div>

              <div>
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Allocation Timeout
                </div>
                <div className="mt-1 text-sm text-gray-900 dark:text-gray-100">{selectedTask.allocation_timeout}s</div>
              </div>
            </div>

            {/* Timestamps */}
            <div className="border-t border-gray-200 dark:border-slate-700 pt-4 space-y-2">
              <div className="text-sm font-medium text-gray-900 dark:text-white">Timeline</div>
              <div className="space-y-1 text-xs">
                <div>
                  <span className="text-gray-500 dark:text-gray-400">Created:</span>{' '}
                  <span className="text-gray-900 dark:text-gray-100">
                    {new Date(selectedTask.created_at).toLocaleString()}
                  </span>
                </div>
                {selectedTask.start_time && (
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Started:</span>{' '}
                    <span className="text-gray-900 dark:text-gray-100">
                      {new Date(selectedTask.start_time).toLocaleString()}
                    </span>
                  </div>
                )}
                {selectedTask.end_time && (
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Ended:</span>{' '}
                    <span className="text-gray-900 dark:text-gray-100">
                      {new Date(selectedTask.end_time).toLocaleString()}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Devices */}
            {selectedTask.devices && Object.keys(selectedTask.devices).length > 0 && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <JsonDisplay data={selectedTask.devices} label="Devices" />
              </div>
            )}

            {/* Input Parameters */}
            {selectedTask.input_parameters && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <JsonDisplay data={selectedTask.input_parameters} label="Input Parameters" />
              </div>
            )}

            {/* Input Resources */}
            {selectedTask.input_resources && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <JsonDisplay data={selectedTask.input_resources} label="Input Resources" />
              </div>
            )}

            {/* Output Parameters */}
            {selectedTask.output_parameters && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <JsonDisplay data={selectedTask.output_parameters} label="Output Parameters" />
              </div>
            )}

            {/* Output Resources */}
            {selectedTask.output_resources && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <JsonDisplay data={selectedTask.output_resources} label="Output Resources" />
              </div>
            )}

            {/* Output Files */}
            {selectedTask.output_file_names && selectedTask.output_file_names.length > 0 && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <TaskOutputFiles
                  fileNames={selectedTask.output_file_names}
                  protocolRunName={selectedTask.protocol_run_name ?? null}
                  taskName={selectedTask.name}
                />
              </div>
            )}

            {/* Metadata */}
            {selectedTask.meta && Object.keys(selectedTask.meta).length > 0 && (
              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <JsonDisplay data={selectedTask.meta} label="Metadata" />
              </div>
            )}
          </div>
        </div>
      )}

      <ConfirmDialog
        isOpen={taskToCancel !== null}
        onClose={() => setTaskToCancel(null)}
        onConfirm={handleCancelTask}
        title="Cancel Task"
        message={`Are you sure you want to cancel task "${taskToCancel?.name}"?`}
        confirmText="Cancel Task"
        cancelText="Keep Running"
        variant="danger"
      />
    </div>
  );
}
