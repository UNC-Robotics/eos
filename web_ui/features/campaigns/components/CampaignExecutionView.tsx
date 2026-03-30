'use client';

import * as React from 'react';
import dynamic from 'next/dynamic';
import { ArrowLeft, X, TrendingUp, FlaskConical } from 'lucide-react';
import * as Tabs from '@radix-ui/react-tabs';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { RefreshControl } from '@/components/ui/RefreshControl';
import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import { CampaignInfoPanel } from './CampaignInfoPanel';
import { RunningProtocolRunsTable } from './RunningProtocolRunsTable';

import { ChartSkeleton } from '@/components/ui/ChartSkeleton';

const OptimizationProgressChart = dynamic(
  () => import('./OptimizationProgressChart').then((m) => m.OptimizationProgressChart),
  { ssr: false, loading: () => <ChartSkeleton /> }
);
const ParetoFrontChart = dynamic(() => import('./ParetoFrontChart').then((m) => m.ParetoFrontChart), {
  ssr: false,
  loading: () => <ChartSkeleton />,
});
import { ParetoSolutionsTable } from './ParetoSolutionsTable';
import { getCampaignWithDetails, type CampaignSample } from '../api/campaignDetails';
import { cancelCampaign } from '../api/campaigns';
import { BeaconOptimizerPanel } from './BeaconOptimizerPanel';
import { BeaconJournalPanel } from './BeaconJournalPanel';
import { extractBeaconInfo } from '../utils/beaconMeta';
import { ConfirmDialog } from '@/components/dialogs/ConfirmDialog';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';
import type { Campaign, ProtocolRun } from '@/lib/types/api';

interface CampaignExecutionViewProps {
  campaign: Campaign;
  initialSamples: CampaignSample[];
  initialProtocolRuns: ProtocolRun[];
}

export function CampaignExecutionView({ campaign, initialSamples, initialProtocolRuns }: CampaignExecutionViewProps) {
  const router = useRouter();
  const { isConnected } = useOrchestratorConnected();
  const [currentCampaign, setCurrentCampaign] = React.useState<Campaign>(campaign);
  const [samples, setSamples] = React.useState<CampaignSample[]>(initialSamples);
  const [protocolRuns, setProtocolRuns] = React.useState<ProtocolRun[]>(initialProtocolRuns);
  const [pollingInterval, setPollingInterval] = React.useState(campaign.status === 'RUNNING' ? 5000 : 0);
  const [isRefreshing, setIsRefreshing] = React.useState(false);
  const [isCancelling, setIsCancelling] = React.useState(false);
  const [showCancelDialog, setShowCancelDialog] = React.useState(false);

  const handleRefresh = React.useCallback(async () => {
    setIsRefreshing(true);
    try {
      const {
        campaign: freshCampaign,
        samples: freshSamples,
        protocolRuns: freshProtocolRuns,
      } = await getCampaignWithDetails(campaign.name);

      if (freshCampaign) {
        setCurrentCampaign(freshCampaign);
        setSamples(freshSamples);
        setProtocolRuns(freshProtocolRuns);

        if (freshCampaign.status !== 'RUNNING' && pollingInterval !== 0) {
          setPollingInterval(0);
        }
      }
    } catch (error) {
      console.error('Failed to refresh campaign:', error);
    } finally {
      setIsRefreshing(false);
    }
  }, [campaign.name, pollingInterval]);

  React.useEffect(() => {
    if (pollingInterval === 0) return;
    const intervalId = setInterval(handleRefresh, pollingInterval);
    return () => clearInterval(intervalId);
  }, [pollingInterval, handleRefresh]);

  const handleBack = React.useCallback(() => {
    router.push('/campaigns');
  }, [router]);

  const handleCancelCampaign = async () => {
    setIsCancelling(true);
    try {
      const result = await cancelCampaign(currentCampaign.name);
      if (!result.success) {
        alert(`Failed to cancel campaign: ${result.error}`);
      } else {
        handleRefresh();
      }
    } finally {
      setIsCancelling(false);
    }
  };

  // Extract objective names from samples
  const outputNames = React.useMemo(() => {
    if (samples.length === 0) return [];
    return Object.keys(samples[0].outputs);
  }, [samples]);

  const inputNames = React.useMemo(() => {
    if (samples.length === 0) return [];
    return Object.keys(samples[0].inputs);
  }, [samples]);

  const activeCount = React.useMemo(() => {
    return protocolRuns.filter((e) => e.status === 'RUNNING' || e.status === 'CREATED').length;
  }, [protocolRuns]);

  const isRunning = currentCampaign.status === 'RUNNING';
  const canCancel = currentCampaign.status === 'RUNNING' || currentCampaign.status === 'CREATED';
  const hasOptimizationData = currentCampaign.optimize && samples.length > 0;
  const hasParetoSolutions = currentCampaign.pareto_solutions && currentCampaign.pareto_solutions.length > 0;

  // Build optimizer info from persisted campaign meta (avoids hitting the Ray actor)
  const resolvedOptimizerInfo = React.useMemo(() => {
    return extractBeaconInfo(currentCampaign.meta);
  }, [currentCampaign.meta]);

  const isBeacon = resolvedOptimizerInfo?.optimizer_type === 'BeaconOptimizer';

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={handleBack} className="gap-2">
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold text-gray-900 dark:text-white">{currentCampaign.name}</h1>
                <Badge variant={getStatusBadgeVariant(currentCampaign.status)}>{currentCampaign.status}</Badge>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {currentCampaign.protocol} • {currentCampaign.owner}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Cancel button */}
            {canCancel && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowCancelDialog(true)}
                disabled={isCancelling || !isConnected}
                className="gap-2 text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-950"
              >
                <X className="h-4 w-4" />
                {isCancelling ? 'Cancelling...' : 'Cancel'}
              </Button>
            )}

            <RefreshControl
              pollingInterval={pollingInterval}
              onIntervalChange={setPollingInterval}
              onRefresh={handleRefresh}
              isRefreshing={isRefreshing}
              disabled={!isRunning}
            />
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-auto p-4">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* Campaign Info */}
          <CampaignInfoPanel campaign={currentCampaign} activeCount={activeCount} />

          {/* Optimization Section */}
          {currentCampaign.optimize && (
            <div className="bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 p-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                <TrendingUp className="h-5 w-5" />
                Optimization Progress
              </h2>

              {hasOptimizationData ? (
                <Tabs.Root defaultValue="progress" className="w-full">
                  <Tabs.List className="flex border-b border-gray-200 dark:border-slate-700 mb-4">
                    <Tabs.Trigger
                      value="progress"
                      className="px-4 py-2 text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 border-b-2 border-transparent data-[state=active]:border-blue-600 data-[state=active]:text-blue-600 dark:data-[state=active]:border-yellow-500 dark:data-[state=active]:text-yellow-500"
                    >
                      Progress Over Time
                    </Tabs.Trigger>
                    <Tabs.Trigger
                      value="pareto"
                      className="px-4 py-2 text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 border-b-2 border-transparent data-[state=active]:border-blue-600 data-[state=active]:text-blue-600 dark:data-[state=active]:border-yellow-500 dark:data-[state=active]:text-yellow-500"
                    >
                      Pareto Front
                    </Tabs.Trigger>
                    <Tabs.Trigger
                      value="solutions"
                      className="px-4 py-2 text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 border-b-2 border-transparent data-[state=active]:border-blue-600 data-[state=active]:text-blue-600 dark:data-[state=active]:border-yellow-500 dark:data-[state=active]:text-yellow-500"
                    >
                      Pareto Solutions
                    </Tabs.Trigger>
                  </Tabs.List>

                  <Tabs.Content value="progress" className="outline-none">
                    <OptimizationProgressChart
                      samples={samples}
                      outputNames={outputNames}
                      campaignName={campaign.name}
                    />
                  </Tabs.Content>

                  <Tabs.Content value="pareto" className="outline-none">
                    <ParetoFrontChart
                      samples={samples}
                      paretoSolutions={currentCampaign.pareto_solutions || []}
                      outputNames={outputNames}
                    />
                  </Tabs.Content>

                  <Tabs.Content value="solutions" className="outline-none">
                    {hasParetoSolutions ? (
                      <ParetoSolutionsTable
                        solutions={currentCampaign.pareto_solutions!}
                        inputNames={inputNames}
                        outputNames={outputNames}
                      />
                    ) : (
                      <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                        Pareto solutions will be computed when the campaign completes.
                      </p>
                    )}
                  </Tabs.Content>
                </Tabs.Root>
              ) : (
                <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                  No optimization data yet. Data will appear after protocol runs complete.
                </p>
              )}
            </div>
          )}

          {/* Beacon Optimizer Panel */}
          {currentCampaign.optimize && isBeacon && resolvedOptimizerInfo && (
            <BeaconOptimizerPanel
              mode="runtime"
              campaignName={currentCampaign.name}
              optimizerInfo={resolvedOptimizerInfo}
              isRunning={isRunning}
              onRefresh={handleRefresh}
            />
          )}

          {/* Beacon Journal */}
          {currentCampaign.optimize && isBeacon && resolvedOptimizerInfo && (
            <BeaconJournalPanel
              campaignName={currentCampaign.name}
              journal={resolvedOptimizerInfo.journal}
              isRunning={isRunning}
              onRefresh={handleRefresh}
            />
          )}

          {/* Protocol Runs */}
          <div className="bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 p-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
              <FlaskConical className="h-5 w-5" />
              Protocol Runs
            </h2>
            <RunningProtocolRunsTable protocolRuns={protocolRuns} campaignName={campaign.name} />
          </div>
        </div>
      </div>

      <ConfirmDialog
        isOpen={showCancelDialog}
        onClose={() => setShowCancelDialog(false)}
        onConfirm={handleCancelCampaign}
        title="Cancel Campaign"
        message={`Are you sure you want to cancel campaign "${currentCampaign.name}"? This will stop all running protocol runs.`}
        confirmText="Cancel Campaign"
        cancelText="Keep Running"
        variant="danger"
      />
    </div>
  );
}
