'use client';

import * as React from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { ArrowLeft, X, List } from 'lucide-react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { RefreshControl } from '@/components/ui/RefreshControl';
import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import { ProtocolRunFlowCanvas } from './ProtocolRunFlowCanvas';
import { TaskDetailPanel } from './TaskDetailPanel';
import { TaskDetailPanelSkeleton } from './TaskDetailPanelSkeleton';
import { TaskListPanel } from './TaskListPanel';
import { getProtocolRunWithTaskStatuses, getTaskDetails, type TaskStatusInfo } from '../api/protocolRunDetails';
import { cancelProtocolRun } from '../api/protocolRuns';
import { ConfirmDialog } from '@/components/dialogs/ConfirmDialog';
import type { ProtocolRun, Task, TaskDeviceConfig } from '@/lib/types/api';
import type { ProtocolSpec } from '@/lib/api/specs';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

const PROTOCOL_RUN_POLLING_INTERVALS = [
  { label: 'Off', value: 0 },
  { label: '1s', value: 1000 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
];

interface ProtocolRunExecutionViewProps {
  protocolRun: ProtocolRun;
  initialTaskStatuses: TaskStatusInfo[];
  protocolSpec: ProtocolSpec;
}

export function ProtocolRunExecutionView({
  protocolRun,
  initialTaskStatuses,
  protocolSpec,
}: ProtocolRunExecutionViewProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isConnected } = useOrchestratorConnected();
  const [taskStatuses, setTaskStatuses] = React.useState<TaskStatusInfo[]>(initialTaskStatuses);
  const [selectedTaskName, setSelectedTaskName] = React.useState<string | null>(null);
  const [currentProtocolRun, setCurrentProtocolRun] = React.useState<ProtocolRun>(protocolRun);
  const [pollingInterval, setPollingInterval] = React.useState(protocolRun.status === 'RUNNING' ? 5000 : 0);
  const [isRefreshing, setIsRefreshing] = React.useState(false);
  const [taskDetailsCache, setTaskDetailsCache] = React.useState<Record<string, Task>>({});
  const taskDetailsCacheRef = React.useRef(taskDetailsCache);
  taskDetailsCacheRef.current = taskDetailsCache;
  const [isLoadingTaskDetails, setIsLoadingTaskDetails] = React.useState(false);
  const [isCancelling, setIsCancelling] = React.useState(false);
  const [showCancelDialog, setShowCancelDialog] = React.useState(false);
  const [showTaskList, setShowTaskList] = React.useState(false);

  const selectedTaskDetails = selectedTaskName ? taskDetailsCache[selectedTaskName] : null;
  const canCancel = currentProtocolRun.status === 'RUNNING' || currentProtocolRun.status === 'CREATED';

  const handleRefresh = React.useCallback(async () => {
    setIsRefreshing(true);
    try {
      const { protocolRun: freshProtocolRun, taskStatuses: freshStatuses } = await getProtocolRunWithTaskStatuses(
        protocolRun.name
      );
      if (freshProtocolRun) {
        setCurrentProtocolRun(freshProtocolRun);
        setTaskStatuses(freshStatuses);

        // Disable polling if protocol run is no longer running
        if (freshProtocolRun.status !== 'RUNNING' && pollingInterval !== 0) {
          setPollingInterval(0);
        }
      }
    } catch (error) {
      console.error('Failed to refresh protocol run:', error);
    } finally {
      setIsRefreshing(false);
    }
  }, [protocolRun.name, pollingInterval]);

  React.useEffect(() => {
    if (pollingInterval === 0) return;
    const intervalId = setInterval(handleRefresh, pollingInterval);
    return () => clearInterval(intervalId);
  }, [pollingInterval, handleRefresh]);

  const handleTaskSelect = React.useCallback(
    async (taskName: string | null) => {
      setSelectedTaskName(taskName);
      if (!taskName || taskDetailsCacheRef.current[taskName]) return;

      setIsLoadingTaskDetails(true);
      try {
        const taskDetails = await getTaskDetails(taskName, protocolRun.name);
        if (taskDetails) {
          setTaskDetailsCache((prev) => ({
            ...prev,
            [taskName]: taskDetails,
          }));
        } else {
          // Task not yet in DB — build a minimal Task from spec data
          const specTask = protocolSpec.tasks.find((t) => t.name === taskName);
          if (specTask) {
            const statusInfo = taskStatuses.find((t) => t.name === taskName);
            const fallbackTask: Task = {
              name: specTask.name,
              type: specTask.type,
              protocol_run_name: protocolRun.name,
              status: statusInfo?.status || 'CREATED',
              created_at: protocolRun.created_at,
              devices: specTask.devices as Record<string, TaskDeviceConfig> | undefined,
              input_parameters: (specTask.parameters as Record<string, unknown>) ?? null,
            };
            setTaskDetailsCache((prev) => ({
              ...prev,
              [taskName]: fallbackTask,
            }));
          }
        }
      } catch (error) {
        console.error('Failed to fetch task details:', error);
      } finally {
        setIsLoadingTaskDetails(false);
      }
    },
    [protocolRun.name, protocolRun.created_at, protocolSpec.tasks, taskStatuses]
  );

  const handleClosePanel = React.useCallback(() => {
    setSelectedTaskName(null);
  }, []);

  const handleCloseTaskList = React.useCallback(() => {
    setShowTaskList(false);
    setSelectedTaskName(null);
  }, []);

  const handleBack = React.useCallback(() => {
    const from = searchParams.get('from');
    const campaignName = searchParams.get('campaign');

    if (from === 'campaign' && campaignName) {
      router.push(`/campaigns/${encodeURIComponent(campaignName)}`);
    } else {
      router.push('/protocol-runs');
    }
  }, [router, searchParams]);

  const handleCancelProtocolRun = async () => {
    setIsCancelling(true);
    try {
      const result = await cancelProtocolRun(currentProtocolRun.name);
      if (!result.success) {
        alert(`Failed to cancel protocol run: ${result.error}`);
      } else {
        handleRefresh();
      }
    } finally {
      setIsCancelling(false);
    }
  };

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
                <h1 className="text-lg font-bold text-gray-900 dark:text-white">{currentProtocolRun.name}</h1>
                <Badge variant={getStatusBadgeVariant(currentProtocolRun.status)}>{currentProtocolRun.status}</Badge>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {currentProtocolRun.type} • {currentProtocolRun.owner}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Task list toggle */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowTaskList((prev) => !prev)}
              className={`gap-2 ${showTaskList ? 'bg-gray-100 dark:bg-slate-700' : ''}`}
            >
              <List className="h-4 w-4" />
              Tasks
            </Button>

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
              disabled={currentProtocolRun.status !== 'RUNNING'}
              intervals={PROTOCOL_RUN_POLLING_INTERVALS}
            />
          </div>
        </div>
      </div>

      {/* Main content: Flow canvas + Task detail panel + Logs */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1">
          <ReactFlowProvider>
            <ProtocolRunFlowCanvas
              protocolTasks={protocolSpec.tasks}
              taskStatuses={taskStatuses}
              onTaskSelect={handleTaskSelect}
              selectedTaskName={selectedTaskName}
              onShowTaskList={() => setShowTaskList(true)}
            />
          </ReactFlowProvider>
        </div>
        {showTaskList && (
          <TaskListPanel
            taskStatuses={taskStatuses}
            selectedTaskName={selectedTaskName}
            onTaskSelect={handleTaskSelect}
            onClose={handleCloseTaskList}
          />
        )}
        {selectedTaskName &&
          (isLoadingTaskDetails && !selectedTaskDetails ? (
            <TaskDetailPanelSkeleton taskName={selectedTaskName} onClose={handleClosePanel} />
          ) : selectedTaskDetails ? (
            <TaskDetailPanel task={selectedTaskDetails} onClose={handleClosePanel} />
          ) : null)}
      </div>

      <ConfirmDialog
        isOpen={showCancelDialog}
        onClose={() => setShowCancelDialog(false)}
        onConfirm={handleCancelProtocolRun}
        title="Cancel Protocol Run"
        message={`Are you sure you want to cancel protocol run "${currentProtocolRun.name}"? This will stop all running tasks.`}
        confirmText="Cancel Protocol Run"
        cancelText="Keep Running"
        variant="danger"
      />
    </div>
  );
}
