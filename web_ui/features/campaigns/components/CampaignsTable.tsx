'use client';

import * as React from 'react';
import { MoreHorizontal, X, Copy, Activity } from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useRouter } from 'next/navigation';
import { DataTable, DataTableColumnDef } from '@/components/data-table/DataTable';
import { Button } from '@/components/ui/Button';
import { RefreshControl } from '@/components/ui/RefreshControl';
import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import { JsonDisplay } from '@/components/ui/JsonDisplay';
import type { Campaign } from '@/lib/types/api';
import type { TaskSpec } from '@/lib/types/experiment';
import type { ExperimentSpec } from '@/lib/api/specs';
import { cancelCampaign, getCampaigns } from '@/features/campaigns/api/campaigns';
import { ConfirmDialog } from '@/components/dialogs/ConfirmDialog';
import { SubmitCampaignDialog } from './SubmitCampaignDialog';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

// Detail panel style constants
const STYLES = {
  label: 'text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide',
  value: 'mt-1 text-sm text-gray-900 dark:text-gray-100',
  textMuted: 'text-gray-500 dark:text-gray-400',
  textNormal: 'text-gray-900 dark:text-gray-100',
  section: 'border-t border-gray-200 dark:border-slate-700 pt-4',
  sectionTitle: 'text-sm font-medium text-gray-900 dark:text-white',
} as const;

// Helper to check if data should be displayed
const hasData = (data: unknown): boolean => {
  if (!data) return false;
  if (Array.isArray(data)) return data.length > 0;
  if (typeof data === 'object') return Object.keys(data).length > 0;
  return true;
};

interface CampaignsTableProps {
  initialCampaigns: Campaign[];
  experimentSpecs: Record<string, ExperimentSpec>;
  taskSpecs: Record<string, TaskSpec>;
}

export function CampaignsTable({ initialCampaigns, experimentSpecs, taskSpecs }: CampaignsTableProps) {
  const router = useRouter();
  const { isConnected } = useOrchestratorConnected();
  const [campaigns, setCampaigns] = React.useState<Campaign[]>(initialCampaigns);
  const [isRefreshing, setIsRefreshing] = React.useState(false);
  const [pollingInterval, setPollingInterval] = React.useState(5000); // Default: 5s
  const [submitDialogOpen, setSubmitDialogOpen] = React.useState(false);
  const [cancellingCampaign, setCancellingCampaign] = React.useState<string | null>(null);
  const [selectedCampaign, setSelectedCampaign] = React.useState<Campaign | null>(null);
  const [detailPanelOpen, setDetailPanelOpen] = React.useState(false);
  const [campaignToClone, setCampaignToClone] = React.useState<Campaign | null>(null);
  const [campaignToCancel, setCampaignToCancel] = React.useState<string | null>(null);

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
    if (!open) {
      // Clear clone state when dialog closes
      setCampaignToClone(null);
    }
  };

  const handleRefresh = React.useCallback(async () => {
    setIsRefreshing(true);
    try {
      const freshCampaigns = await getCampaigns();
      setCampaigns(freshCampaigns);

      // Update selected campaign if it's still in the list
      if (selectedCampaign) {
        const updatedCampaign = freshCampaigns.find((c) => c.name === selectedCampaign.name);
        if (updatedCampaign) {
          setSelectedCampaign(updatedCampaign);
        }
      }
    } catch (error) {
      console.error('Failed to refresh campaigns:', error);
    } finally {
      setIsRefreshing(false);
    }
  }, [selectedCampaign]);

  // Auto-polling effect
  React.useEffect(() => {
    if (pollingInterval === 0) {
      return; // Polling disabled
    }

    const intervalId = setInterval(() => {
      handleRefresh();
    }, pollingInterval);

    return () => clearInterval(intervalId);
  }, [pollingInterval, handleRefresh]);

  const columns: DataTableColumnDef<Campaign>[] = [
    {
      accessorKey: 'name',
      header: 'Name',
      cell: ({ row }) => <div className="font-medium">{row.getValue('name')}</div>,
      enableColumnFilter: true,
      filterType: 'text',
    },
    {
      accessorKey: 'experiment_type',
      header: 'Experiment Type',
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
      accessorKey: 'experiments_completed',
      header: 'Progress',
      cell: ({ row }) => {
        const completed = row.getValue('experiments_completed') as number;
        const max = row.original.max_experiments;
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
        return <span className="text-gray-600">{date.toLocaleString()}</span>;
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
      onRefresh={handleRefresh}
      isRefreshing={isRefreshing}
    />
  );

  return (
    <div className="flex gap-4">
      <div className={`space-y-4 ${detailPanelOpen ? 'flex-1' : 'w-full'}`}>
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Campaigns</h1>
            <p className="text-gray-600 dark:text-gray-400 mt-1">View and manage campaign execution</p>
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
          data={campaigns}
          searchPlaceholder="Search campaigns..."
          onRowClick={handleRowClick}
          toolbarActions={toolbarActions}
        />

        <SubmitCampaignDialog
          open={submitDialogOpen}
          onOpenChange={handleCloseSubmitDialog}
          experimentSpecs={experimentSpecs}
          taskSpecs={taskSpecs}
          initialCampaign={campaignToClone}
          existingCampaignNames={campaigns.map(c => c.name)}
        />
      </div>

      {detailPanelOpen && selectedCampaign && (
        <div className="w-96 border-l border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto self-start">
          <div className="flex items-start justify-between mb-6">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{selectedCampaign.name}</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">Campaign Details</p>
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
                <div className={STYLES.label}>Experiment Type</div>
                <div className={STYLES.value}>{selectedCampaign.experiment_type}</div>
              </div>

              <div>
                <div className={STYLES.label}>Status</div>
                <div className="mt-1">
                  <Badge variant={getStatusBadgeVariant(selectedCampaign.status)}>{selectedCampaign.status}</Badge>
                </div>
              </div>

              {selectedCampaign.status === 'FAILED' && selectedCampaign.error_message && (
                <div className="bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 rounded-lg p-3">
                  <div className="text-xs font-medium text-red-800 dark:text-red-300 mb-1">Error</div>
                  <p className="text-xs text-red-700 dark:text-red-400 whitespace-pre-wrap break-words font-mono">
                    {selectedCampaign.error_message}
                  </p>
                </div>
              )}

              <div>
                <div className={STYLES.label}>Owner</div>
                <div className={STYLES.value}>{selectedCampaign.owner}</div>
              </div>

              <div>
                <div className={STYLES.label}>Priority</div>
                <div className={STYLES.value}>{selectedCampaign.priority}</div>
              </div>
            </div>

            {/* Progress */}
            <div className={STYLES.section}>
              <div className={`${STYLES.sectionTitle} mb-3`}>Progress</div>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className={STYLES.textMuted}>Completed:</span>
                  <span className={`${STYLES.textNormal} font-medium`}>{selectedCampaign.experiments_completed}</span>
                </div>
                <div className="flex justify-between">
                  <span className={STYLES.textMuted}>Max Experiments:</span>
                  <span className={`${STYLES.textNormal} font-medium`}>
                    {selectedCampaign.max_experiments === 0 ? '∞' : selectedCampaign.max_experiments}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className={STYLES.textMuted}>Max Concurrent:</span>
                  <span className={`${STYLES.textNormal} font-medium`}>
                    {selectedCampaign.max_concurrent_experiments}
                  </span>
                </div>
              </div>
            </div>

            {/* Optimization */}
            <div className={STYLES.section}>
              <div className={`${STYLES.sectionTitle} mb-3`}>Optimization</div>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className={STYLES.textMuted}>Enabled:</span>
                  <Badge variant={selectedCampaign.optimize ? 'info' : 'default'}>
                    {selectedCampaign.optimize ? 'Yes' : 'No'}
                  </Badge>
                </div>
                {selectedCampaign.optimize && (
                  <div className="flex justify-between">
                    <span className={STYLES.textMuted}>Optimizer IP:</span>
                    <span className={`${STYLES.textNormal} font-mono text-xs`}>{selectedCampaign.optimizer_ip}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Timestamps */}
            <div className={`${STYLES.section} space-y-2`}>
              <div className={STYLES.sectionTitle}>Timeline</div>
              <div className="space-y-1 text-xs">
                <div>
                  <span className={STYLES.textMuted}>Created:</span>{' '}
                  <span className={STYLES.textNormal}>{new Date(selectedCampaign.created_at).toLocaleString()}</span>
                </div>
                {selectedCampaign.start_time && (
                  <div>
                    <span className={STYLES.textMuted}>Started:</span>{' '}
                    <span className={STYLES.textNormal}>{new Date(selectedCampaign.start_time).toLocaleString()}</span>
                  </div>
                )}
                {selectedCampaign.end_time && (
                  <div>
                    <span className={STYLES.textMuted}>Ended:</span>{' '}
                    <span className={STYLES.textNormal}>{new Date(selectedCampaign.end_time).toLocaleString()}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Global Parameters */}
            {hasData(selectedCampaign.global_parameters) && (
              <div className={STYLES.section}>
                <JsonDisplay data={selectedCampaign.global_parameters} label="Global Parameters" />
              </div>
            )}

            {/* Experiment Parameters */}
            {hasData(selectedCampaign.experiment_parameters) && (
              <div className={STYLES.section}>
                <JsonDisplay data={selectedCampaign.experiment_parameters} label="Experiment Parameters" />
              </div>
            )}

            {/* Pareto Solutions */}
            {hasData(selectedCampaign.pareto_solutions) && (
              <div className={STYLES.section}>
                <JsonDisplay data={selectedCampaign.pareto_solutions} label="Pareto Solutions" />
              </div>
            )}

            {/* Metadata */}
            {hasData(selectedCampaign.meta) && (
              <div className={STYLES.section}>
                <JsonDisplay data={selectedCampaign.meta} label="Metadata" />
              </div>
            )}
          </div>
        </div>
      )}

      <ConfirmDialog
        isOpen={campaignToCancel !== null}
        onClose={() => setCampaignToCancel(null)}
        onConfirm={handleCancelCampaign}
        title="Cancel Campaign"
        message={`Are you sure you want to cancel campaign "${campaignToCancel}"? This will stop all running experiments.`}
        confirmText="Cancel Campaign"
        cancelText="Keep Running"
        variant="danger"
      />
    </div>
  );
}
