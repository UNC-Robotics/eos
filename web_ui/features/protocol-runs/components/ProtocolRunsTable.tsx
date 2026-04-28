'use client';

import * as React from 'react';
import { MoreHorizontal, X, Copy, Activity } from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useRouter } from 'next/navigation';
import { DataTable, DataTableColumnDef } from '@/components/data-table/DataTable';
import { Button } from '@/components/ui/Button';
import { RefreshControl } from '@/components/ui/RefreshControl';
import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import { ProtocolRunDetail } from './shared';
import { DROPDOWN_ITEM } from '../styles';
import type { ProtocolRun } from '@/lib/types/api';
import type { PaginatedResult } from '@/lib/db/queries';
import type { TaskSpec } from '@/lib/types/protocol';
import type { ProtocolSpec, LabSpec } from '@/lib/api/specs';
import { cancelProtocolRun, getProtocolRuns } from '@/features/protocol-runs/api/protocolRuns';
import { generateCloneNameForEntity } from '@/lib/utils/naming.server';
import { useServerTable } from '@/hooks/useServerTable';
import { ConfirmDialog } from '@/components/dialogs/ConfirmDialog';
import { SubmitProtocolRunDialog } from './SubmitProtocolRunDialog';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

const PROTOCOL_RUNS_POLLING_INTERVALS = [
  { label: 'Off', value: 0 },
  { label: '1s', value: 1000 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
];

const PROTOCOL_RUN_COLUMN_ID_MAP: Record<string, string> = {
  created_at: 'createdAt',
};

interface ProtocolRunsTableProps {
  initialData: PaginatedResult<ProtocolRun>;
  protocolSpecs: Record<string, ProtocolSpec>;
  taskSpecs: Record<string, TaskSpec>;
  labSpecs: Record<string, LabSpec>;
}

export function ProtocolRunsTable({ initialData, protocolSpecs, taskSpecs, labSpecs }: ProtocolRunsTableProps) {
  const router = useRouter();
  const { isConnected } = useOrchestratorConnected();
  const [pollingInterval, setPollingInterval] = React.useState(5000);
  const [submitDialogOpen, setSubmitDialogOpen] = React.useState(false);
  const [cancellingProtocolRun, setCancellingProtocolRun] = React.useState<string | null>(null);
  const [selectedProtocolRun, setSelectedProtocolRun] = React.useState<ProtocolRun | null>(null);
  const [detailPanelOpen, setDetailPanelOpen] = React.useState(false);
  const [protocolRunToClone, setProtocolRunToClone] = React.useState<ProtocolRun | null>(null);
  const [protocolRunToCancel, setProtocolRunToCancel] = React.useState<string | null>(null);

  const serverTable = useServerTable({
    fetchFn: getProtocolRuns,
    initialData,
    columnIdMap: PROTOCOL_RUN_COLUMN_ID_MAP,
  });

  React.useEffect(() => {
    if (pollingInterval === 0) return;
    const intervalId = setInterval(() => {
      serverTable.refresh();
    }, pollingInterval);
    return () => clearInterval(intervalId);
  }, [pollingInterval, serverTable.refresh]); // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    if (selectedProtocolRun) {
      const updated = serverTable.data.find((e) => e.name === selectedProtocolRun.name);
      if (updated) setSelectedProtocolRun(updated);
    }
  }, [serverTable.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCancelProtocolRun = async () => {
    if (!protocolRunToCancel) return;
    setCancellingProtocolRun(protocolRunToCancel);
    try {
      const result = await cancelProtocolRun(protocolRunToCancel);
      if (!result.success) {
        alert(`Failed to cancel protocol run: ${result.error}`);
      }
    } finally {
      setCancellingProtocolRun(null);
      setProtocolRunToCancel(null);
    }
  };

  const handleRowClick = (protocolRun: ProtocolRun) => {
    setSelectedProtocolRun(protocolRun);
    setDetailPanelOpen(true);
  };

  const handleViewExecution = (protocolRunName: string) => {
    router.push(`/protocol-runs/${encodeURIComponent(protocolRunName)}`);
  };

  const handleCloneProtocolRun = (protocolRun: ProtocolRun) => {
    setProtocolRunToClone(protocolRun);
    setSubmitDialogOpen(true);
  };

  const handleCloseSubmitDialog = (open: boolean) => {
    setSubmitDialogOpen(open);
    if (!open) setProtocolRunToClone(null);
  };

  const columns: DataTableColumnDef<ProtocolRun>[] = [
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
      accessorKey: 'campaign',
      header: 'Campaign',
      cell: ({ row }) => {
        const campaign = row.getValue('campaign') as string | null;
        return campaign ? (
          <span className="text-gray-900 dark:text-gray-100">{campaign}</span>
        ) : (
          <span className="text-gray-400 dark:text-gray-500">—</span>
        );
      },
      enableColumnFilter: true,
      filterType: 'text',
    },
    {
      accessorKey: 'owner',
      header: 'Owner',
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
        const protocolRun = row.original;
        const canCancel = protocolRun.status === 'RUNNING' || protocolRun.status === 'CREATED';

        return (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => handleViewExecution(protocolRun.name)}
              title="View Execution"
            >
              <Activity className="h-4 w-4" />
            </Button>
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                  <span className="sr-only">Open menu</span>
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content className="w-48 rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-1 shadow-md z-50">
                  <DropdownMenu.Item className={DROPDOWN_ITEM} onClick={() => handleCloneProtocolRun(protocolRun)}>
                    <Copy className="h-4 w-4" />
                    <span>Clone</span>
                  </DropdownMenu.Item>
                  {canCancel && (
                    <DropdownMenu.Item
                      className={DROPDOWN_ITEM}
                      onClick={() => setProtocolRunToCancel(protocolRun.name)}
                      disabled={cancellingProtocolRun === protocolRun.name || !isConnected}
                    >
                      <X className="h-4 w-4" />
                      <span>
                        {cancellingProtocolRun === protocolRun.name ? 'Cancelling...' : 'Cancel Protocol Run'}
                      </span>
                    </DropdownMenu.Item>
                  )}
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
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
      intervals={PROTOCOL_RUNS_POLLING_INTERVALS}
    />
  );

  return (
    <div className="flex gap-4">
      <div className={`space-y-4 ${detailPanelOpen ? 'flex-1' : 'w-full'}`}>
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Protocol Runs</h1>
            <p className="text-gray-600 dark:text-gray-400 mt-1">View and manage protocol runs</p>
          </div>
          <Button
            variant="primary"
            disabled={!isConnected}
            title={!isConnected ? 'Orchestrator offline' : undefined}
            onClick={() => {
              setProtocolRunToClone(null);
              setSubmitDialogOpen(true);
            }}
          >
            Submit Protocol Run
          </Button>
        </div>

        <DataTable
          columns={columns}
          data={serverTable.data}
          searchPlaceholder="Search protocol runs..."
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

        <SubmitProtocolRunDialog
          open={submitDialogOpen}
          onOpenChange={handleCloseSubmitDialog}
          onSuccess={() => setTimeout(() => serverTable.refresh(), 500)}
          protocolSpecs={protocolSpecs}
          taskSpecs={taskSpecs}
          labSpecs={labSpecs}
          initialProtocolRun={protocolRunToClone}
          generateCloneName={(name) => generateCloneNameForEntity('protocolRuns', name)}
        />
      </div>

      {detailPanelOpen && selectedProtocolRun && (
        <div className="w-96 min-w-0 border-l border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto overflow-x-hidden self-start">

          <div className="flex items-start justify-between mb-6 min-w-0">
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white break-words">
                {selectedProtocolRun.name}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Protocol Run Details
              </p>
            </div>
            <button
              onClick={() => setDetailPanelOpen(false)}
              className="rounded-sm opacity-70 ring-offset-white dark:ring-offset-slate-900 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 text-gray-900 dark:text-gray-400"
            >
              <X className="h-4 w-4" />
              <span className="sr-only">Close</span>
            </button>
          </div>
          <ProtocolRunDetail protocolRun={selectedProtocolRun} />
        </div>
      )}

      <ConfirmDialog
        isOpen={protocolRunToCancel !== null}
        onClose={() => setProtocolRunToCancel(null)}
        onConfirm={handleCancelProtocolRun}
        title="Cancel Protocol Run"
        message={`Are you sure you want to cancel protocol run "${protocolRunToCancel}"? This will stop all running tasks.`}
        confirmText="Cancel Protocol Run"
        cancelText="Keep Running"
        variant="danger"
      />
    </div>
  );
}
