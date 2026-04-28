'use client';

import * as React from 'react';
import { MoreHorizontal, X, Copy, Activity } from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useRouter } from 'next/navigation';
import { DataTable, DataTableColumnDef } from '@/components/data-table/DataTable';
import { Button } from '@/components/ui/Button';
import { RefreshControl } from '@/components/ui/RefreshControl';
import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import { ErrorBox } from '@/components/ui/ErrorBox';
import type { Campaign } from '@/lib/types/api';
import type { PaginatedResult } from '@/lib/db/queries';
import type { TaskSpec } from '@/lib/types/protocol';
import type { ProtocolSpec } from '@/lib/api/specs';
import { cancelCampaign, getCampaigns } from '@/features/campaigns/api/campaigns';
import { generateCloneNameForEntity } from '@/lib/utils/naming.server';
import { useServerTable } from '@/hooks/useServerTable';
import { ConfirmDialog } from '@/components/dialogs/ConfirmDialog';
import { SubmitCampaignDialog } from './SubmitCampaignDialog';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';
import { ConditionalJsonSection, DetailField, TimelineSection } from '@/features/protocol-runs/components/shared';
import { SECTION_DIVIDER } from '@/features/protocol-runs/styles';

const SECTION_TITLE = 'text-sm font-medium text-gray-900 dark:text-white';

const CAMPAIGN_COLUMN_ID_MAP: Record<string, string> = {
  protocol: 'protocol',
  created_at: 'createdAt',
};

interface CampaignsTableProps {
  initialData: PaginatedResult<Campaign>;
  protocolSpecs: Record<string, ProtocolSpec>;
  taskSpecs: Record<string, TaskSpec>;
}

export function CampaignsTable({ initialData, protocolSpecs, taskSpecs }: CampaignsTableProps) {
  const router = useRouter();
  const { isConnected } = useOrchestratorConnected();
  const [pollingInterval, setPollingInterval] = React.useState(5000);
  const [submitDialogOpen, setSubmitDialogOpen] = React.useState(false);
  const [cancellingCampaign, setCancellingCampaign] = React.useState<string | null>(null);
  const [selectedCampaign, setSelectedCampaign] = React.useState<Campaign | null>(null);
  const [detailPanelOpen, setDetailPanelOpen] = React.useState(false);
  const [campaignToClone, setCampaignToClone] = React.useState<Campaign | null>(null);
  const [campaignToCancel, setCampaignToCancel] = React.useState<string | null>(null);

  const serverTable = useServerTable({
    fetchFn: getCampaigns,
    initialData,
    columnIdMap: CAMPAIGN_COLUMN_ID_MAP,
  });

  // Auto-polling effect
  React.useEffect(() => {
    if (pollingInterval === 0) return;
    const intervalId = setInterval(() => {
      serverTable.refresh();
    }, pollingInterval);
    return () => clearInterval(intervalId);
  }, [pollingInterval, serverTable.refresh]); // eslint-disable-line react-hooks/exhaustive-deps

  // Update selected campaign from refreshed data
  React.useEffect(() => {
    if (selectedCampaign) {
      const updated = serverTable.data.find((c) => c.name === selectedCampaign.name);
      if (updated) setSelectedCampaign(updated);
    }
  }, [serverTable.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleViewExecution = (campaignName: string) => {
    router.push(`/campaigns/${encodeURIComponent(campaignName)}`);
  };

  const handleCancelCampaign = async () => {
    if (!campaignToCancel) return;
    setCancellingCampaign(campaignToCancel);
    try {
      const result = await cancelCampaign(campaignToCancel);
      if (!result.success) {
        alert(`Failed to cancel campaign: ${result.error}`);
      }
    } finally {
      setCancellingCampaign(null);
      setCampaignToCancel(null);
    }
  };

  const handleRowClick = (campaign: Campaign) => {
    setSelectedCampaign(campaign);
    setDetailPanelOpen(true);
  };

  const handleCloneCampaign = (campaign: Campaign) => {
    setCampaignToClone(campaign);
    setSubmitDialogOpen(true);
  };

  const handleCloseSubmitDialog = (open: boolean) => {
    setSubmitDialogOpen(open);
    if (!open) setCampaignToClone(null);
  };

  const columns: DataTableColumnDef<Campaign>[] = [
    {
      accessorKey: 'name',
      header: 'Name',
      cell: ({ row }) => <div className="font-medium">{row.getValue('name')}</div>,
      enableColumnFilter: true,
      filterType: 'text',
    },
    {
      accessorKey: 'protocol',
      header: 'Protocol',
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
      accessorKey: 'protocol_runs_completed',
      header: 'Progress',
      cell: ({ row }) => {
        const completed = row.getValue('protocol_runs_completed') as number;
        const max = row.original.max_protocol_runs;
        return (
          <div className="text-sm">
            {completed} / {max === 0 ? '∞' : max}
          </div>
        );
      },
    },
    {
      accessorKey: 'optimize',
      header: 'Optimize',
      cell: ({ row }) => {
        const optimize = row.getValue('optimize') as boolean;
        return <Badge variant={optimize ? 'info' : 'default'}>{optimize ? 'Yes' : 'No'}</Badge>;
      },
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
        const campaign = row.original;
        const canCancel = campaign.status === 'RUNNING' || campaign.status === 'CREATED';

        return (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => handleViewExecution(campaign.name)}
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
                  <DropdownMenu.Item
                    className="relative flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-gray-100 dark:hover:bg-slate-700 focus:bg-gray-100 dark:focus:bg-slate-700 dark:text-gray-300"
                    onClick={() => handleCloneCampaign(campaign)}
                  >
                    <Copy className="h-4 w-4" />
                    <span>Clone</span>
                  </DropdownMenu.Item>
                  {canCancel && (
                    <DropdownMenu.Item
                      className="relative flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-gray-100 dark:hover:bg-slate-700 focus:bg-gray-100 dark:focus:bg-slate-700 dark:text-gray-300"
                      onClick={() => setCampaignToCancel(campaign.name)}
                      disabled={cancellingCampaign === campaign.name || !isConnected}
                    >
                      <X className="h-4 w-4" />
                      <span>{cancellingCampaign === campaign.name ? 'Cancelling...' : 'Cancel Campaign'}</span>
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
    />
  );

  return (
    <div className="flex gap-4">
      <div className={`space-y-4 ${detailPanelOpen ? 'flex-1 min-w-0' : 'w-full'}`}>
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Campaigns</h1>
            <p className="text-gray-600 dark:text-gray-400 mt-1">View and manage campaigns</p>
          </div>
          <Button
            variant="primary"
            disabled={!isConnected}
            title={!isConnected ? 'Orchestrator offline' : undefined}
            onClick={() => {
              setCampaignToClone(null);
              setSubmitDialogOpen(true);
            }}
          >
            Submit Campaign
          </Button>
        </div>

        <DataTable
          columns={columns}
          data={serverTable.data}
          searchPlaceholder="Search campaigns..."
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

        <SubmitCampaignDialog
          open={submitDialogOpen}
          onOpenChange={handleCloseSubmitDialog}
          onSuccess={() => setTimeout(() => serverTable.refresh(), 500)}
          protocolSpecs={protocolSpecs}
          taskSpecs={taskSpecs}
          initialCampaign={campaignToClone}
          generateCloneName={(name) => generateCloneNameForEntity('campaigns', name)}
        />
      </div>

      {detailPanelOpen && selectedCampaign && (
        <div className="w-96 border-l border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto self-start">
          <div className="flex items-start justify-between mb-6 gap-2">
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white break-words">
                {selectedCampaign.name}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">Campaign Details</p>
            </div>
            <button
              onClick={() => setDetailPanelOpen(false)}
              className="flex-shrink-0 rounded-sm opacity-70 ring-offset-white dark:ring-offset-slate-900 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 text-gray-900 dark:text-gray-400"
            >
              <X className="h-4 w-4" />
              <span className="sr-only">Close</span>
            </button>
          </div>

          <div className="space-y-6">
            <div className="space-y-3">
              <DetailField label="Protocol" value={selectedCampaign.protocol} />
              <DetailField
                label="Status"
                value={
                  <Badge variant={getStatusBadgeVariant(selectedCampaign.status)}>{selectedCampaign.status}</Badge>
                }
              />
              {selectedCampaign.status === 'FAILED' && selectedCampaign.error_message && (
                <ErrorBox error={selectedCampaign.error_message} />
              )}
              <DetailField label="Owner" value={selectedCampaign.owner} />
              <DetailField label="Priority" value={selectedCampaign.priority} />
            </div>

            <div className={SECTION_DIVIDER}>
              <div className={`${SECTION_TITLE} mb-3`}>Progress</div>
              <div className="space-y-2">
                <DetailField inline label="Completed" value={selectedCampaign.protocol_runs_completed} />
                <DetailField
                  inline
                  label="Max Protocol Runs"
                  value={selectedCampaign.max_protocol_runs === 0 ? '∞' : selectedCampaign.max_protocol_runs}
                />
                <DetailField inline label="Max Concurrent" value={selectedCampaign.max_concurrent_protocol_runs} />
              </div>
            </div>

            <div className={SECTION_DIVIDER}>
              <div className={`${SECTION_TITLE} mb-3`}>Optimization</div>
              <div className="space-y-2">
                <DetailField
                  inline
                  label="Enabled"
                  value={
                    <Badge variant={selectedCampaign.optimize ? 'info' : 'default'}>
                      {selectedCampaign.optimize ? 'Yes' : 'No'}
                    </Badge>
                  }
                />
                {selectedCampaign.optimize && (
                  <DetailField
                    inline
                    label="Optimizer IP"
                    value={<span className="font-mono text-xs break-all">{selectedCampaign.optimizer_ip}</span>}
                  />
                )}
              </div>
            </div>

            <div className={SECTION_DIVIDER}>
              <div className={`${SECTION_TITLE} mb-2`}>Timeline</div>
              <TimelineSection
                entries={[
                  { label: 'Created', timestamp: selectedCampaign.created_at ?? null },
                  { label: 'Started', timestamp: selectedCampaign.start_time ?? null },
                  { label: 'Ended', timestamp: selectedCampaign.end_time ?? null },
                ]}
              />
            </div>

            <ConditionalJsonSection data={selectedCampaign.global_parameters} label="Global Parameters" />
            <ConditionalJsonSection data={selectedCampaign.protocol_run_parameters} label="Protocol Run Parameters" />
            <ConditionalJsonSection data={selectedCampaign.pareto_solutions} label="Pareto Solutions" />
            <ConditionalJsonSection data={selectedCampaign.meta} label="Metadata" />
          </div>
        </div>
      )}

      <ConfirmDialog
        isOpen={campaignToCancel !== null}
        onClose={() => setCampaignToCancel(null)}
        onConfirm={handleCancelCampaign}
        title="Cancel Campaign"
        message={`Are you sure you want to cancel campaign "${campaignToCancel}"? This will stop all running protocol runs.`}
        confirmText="Cancel Campaign"
        cancelText="Keep Running"
        variant="danger"
      />
    </div>
  );
}
