'use client';

import * as React from 'react';
import { MoreHorizontal, X, Copy, Activity } from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useRouter } from 'next/navigation';
import { DataTable, DataTableColumnDef } from '@/components/data-table/DataTable';
import { Button } from '@/components/ui/Button';
import { RefreshControl } from '@/components/ui/RefreshControl';
import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import { ExperimentDetail } from './shared';
import { DROPDOWN_ITEM } from '../styles';
import type { Experiment } from '@/lib/types/api';
import type { PaginatedResult } from '@/lib/db/queries';
import type { TaskSpec } from '@/lib/types/experiment';
import type { ExperimentSpec, LabSpec } from '@/lib/api/specs';
import { cancelExperiment, getExperiments } from '@/features/experiments/api/experiments';
import { generateCloneNameForEntity } from '@/lib/utils/naming.server';
import { useServerTable } from '@/hooks/useServerTable';
import { ConfirmDialog } from '@/components/dialogs/ConfirmDialog';
import { SubmitExperimentDialog } from './SubmitExperimentDialog';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

const EXPERIMENTS_POLLING_INTERVALS = [
  { label: 'Off', value: 0 },
  { label: '1s', value: 1000 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
];

const EXPERIMENT_COLUMN_ID_MAP: Record<string, string> = {
  created_at: 'createdAt',
};

interface ExperimentsTableProps {
  initialData: PaginatedResult<Experiment>;
  experimentSpecs: Record<string, ExperimentSpec>;
  taskSpecs: Record<string, TaskSpec>;
  labSpecs: Record<string, LabSpec>;
}

export function ExperimentsTable({ initialData, experimentSpecs, taskSpecs, labSpecs }: ExperimentsTableProps) {
  const router = useRouter();
  const { isConnected } = useOrchestratorConnected();
  const [pollingInterval, setPollingInterval] = React.useState(5000);
  const [submitDialogOpen, setSubmitDialogOpen] = React.useState(false);
  const [cancellingExperiment, setCancellingExperiment] = React.useState<string | null>(null);
  const [selectedExperiment, setSelectedExperiment] = React.useState<Experiment | null>(null);
  const [detailPanelOpen, setDetailPanelOpen] = React.useState(false);
  const [experimentToClone, setExperimentToClone] = React.useState<Experiment | null>(null);
  const [experimentToCancel, setExperimentToCancel] = React.useState<string | null>(null);

  const serverTable = useServerTable({
    fetchFn: getExperiments,
    initialData,
    columnIdMap: EXPERIMENT_COLUMN_ID_MAP,
  });

  React.useEffect(() => {
    if (pollingInterval === 0) return;
    const intervalId = setInterval(() => {
      serverTable.refresh();
    }, pollingInterval);
    return () => clearInterval(intervalId);
  }, [pollingInterval, serverTable.refresh]); // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    if (selectedExperiment) {
      const updated = serverTable.data.find((e) => e.name === selectedExperiment.name);
      if (updated) setSelectedExperiment(updated);
    }
  }, [serverTable.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCancelExperiment = async () => {
    if (!experimentToCancel) return;
    setCancellingExperiment(experimentToCancel);
    try {
      const result = await cancelExperiment(experimentToCancel);
      if (!result.success) {
        alert(`Failed to cancel experiment: ${result.error}`);
      }
    } finally {
      setCancellingExperiment(null);
      setExperimentToCancel(null);
    }
  };

  const handleRowClick = (experiment: Experiment) => {
    setSelectedExperiment(experiment);
    setDetailPanelOpen(true);
  };

  const handleViewExecution = (experimentName: string) => {
    router.push(`/experiments/${encodeURIComponent(experimentName)}`);
  };

  const handleCloneExperiment = (experiment: Experiment) => {
    setExperimentToClone(experiment);
    setSubmitDialogOpen(true);
  };

  const handleCloseSubmitDialog = (open: boolean) => {
    setSubmitDialogOpen(open);
    if (!open) setExperimentToClone(null);
  };

  const columns: DataTableColumnDef<Experiment>[] = [
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
        return <span className="text-gray-600">{date.toLocaleString()}</span>;
      },
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => {
        const experiment = row.original;
        const canCancel = experiment.status === 'RUNNING' || experiment.status === 'CREATED';

        return (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => handleViewExecution(experiment.name)}
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
                  <DropdownMenu.Item className={DROPDOWN_ITEM} onClick={() => handleCloneExperiment(experiment)}>
                    <Copy className="h-4 w-4" />
                    <span>Clone</span>
                  </DropdownMenu.Item>
                  {canCancel && (
                    <DropdownMenu.Item
                      className={DROPDOWN_ITEM}
                      onClick={() => setExperimentToCancel(experiment.name)}
                      disabled={cancellingExperiment === experiment.name || !isConnected}
                    >
                      <X className="h-4 w-4" />
                      <span>{cancellingExperiment === experiment.name ? 'Cancelling...' : 'Cancel Experiment'}</span>
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
      intervals={EXPERIMENTS_POLLING_INTERVALS}
    />
  );

  return (
    <div className="flex gap-4">
      <div className={`space-y-4 ${detailPanelOpen ? 'flex-1' : 'w-full'}`}>
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Experiments</h1>
            <p className="text-gray-600 dark:text-gray-400 mt-1">View and manage experiment execution</p>
          </div>
          <Button
            variant="primary"
            disabled={!isConnected}
            title={!isConnected ? 'Orchestrator offline' : undefined}
            onClick={() => {
              setExperimentToClone(null);
              setSubmitDialogOpen(true);
            }}
          >
            Submit Experiment
          </Button>
        </div>

        <DataTable
          columns={columns}
          data={serverTable.data}
          searchPlaceholder="Search experiments..."
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

        <SubmitExperimentDialog
          open={submitDialogOpen}
          onOpenChange={handleCloseSubmitDialog}
          experimentSpecs={experimentSpecs}
          taskSpecs={taskSpecs}
          labSpecs={labSpecs}
          initialExperiment={experimentToClone}
          generateCloneName={(name) => generateCloneNameForEntity('experiments', name)}
        />
      </div>

      {detailPanelOpen && selectedExperiment && (
        <div className="w-96 border-l border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto self-start">
          <div className="flex items-start justify-between mb-6">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{selectedExperiment.name}</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">Experiment Details</p>
            </div>
            <button
              onClick={() => setDetailPanelOpen(false)}
              className="rounded-sm opacity-70 ring-offset-white dark:ring-offset-slate-900 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 text-gray-900 dark:text-gray-400"
            >
              <X className="h-4 w-4" />
              <span className="sr-only">Close</span>
            </button>
          </div>
          <ExperimentDetail experiment={selectedExperiment} />
        </div>
      )}

      <ConfirmDialog
        isOpen={experimentToCancel !== null}
        onClose={() => setExperimentToCancel(null)}
        onConfirm={handleCancelExperiment}
        title="Cancel Experiment"
        message={`Are you sure you want to cancel experiment "${experimentToCancel}"? This will stop all running tasks.`}
        confirmText="Cancel Experiment"
        cancelText="Keep Running"
        variant="danger"
      />
    </div>
  );
}
