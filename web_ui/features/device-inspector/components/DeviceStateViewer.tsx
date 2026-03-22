'use client';

import * as React from 'react';
import { RefreshCw, Play, Pause, ChevronDown, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { JsonDisplay } from '@/components/ui/JsonDisplay';
import { toast } from '@/lib/utils/toast';
import { getDeviceState } from '../api/inspector';
import { useDeviceInspectorStore } from '@/lib/stores/deviceInspectorStore';
import type { SelectedDevice } from '@/lib/types/device-inspector';
import type { DeviceReport } from '@/lib/types/management';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

interface DeviceStateViewerProps {
  device: SelectedDevice;
}

export function DeviceStateViewer({ device }: DeviceStateViewerProps) {
  const { isConnected } = useOrchestratorConnected();
  const [deviceState, setDeviceState] = React.useState<DeviceReport | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [isExpanded, setIsExpanded] = React.useState(true);

  const { autoRefreshEnabled, refreshInterval, setAutoRefreshEnabled, updateLastRefreshTime } =
    useDeviceInspectorStore();

  // Fetch device state
  const fetchState = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const state = await getDeviceState(device.labName, device.deviceName);
      setDeviceState(state);
      updateLastRefreshTime();
    } catch (error) {
      console.error('Failed to fetch device state:', error);
      toast.error('Failed to fetch device state');
    } finally {
      setIsLoading(false);
    }
  }, [device.labName, device.deviceName, updateLastRefreshTime]);

  // Fetch state on mount and when device changes
  React.useEffect(() => {
    if (isConnected) fetchState();
  }, [fetchState, isConnected]);

  // Auto-refresh effect
  React.useEffect(() => {
    if (!autoRefreshEnabled || !isConnected) {
      return;
    }

    const intervalId = setInterval(() => {
      fetchState();
    }, refreshInterval);

    return () => {
      clearInterval(intervalId);
    };
  }, [autoRefreshEnabled, refreshInterval, fetchState, isConnected]);

  const handleToggleAutoRefresh = () => {
    setAutoRefreshEnabled(!autoRefreshEnabled);
    if (!autoRefreshEnabled) {
      toast.success(`Auto-refresh enabled (every ${refreshInterval / 1000}s)`);
    } else {
      toast.success('Auto-refresh disabled');
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-gray-100 hover:text-gray-700 dark:hover:text-gray-300"
        >
          {isExpanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
          Device State
        </button>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleToggleAutoRefresh}
            title={autoRefreshEnabled ? 'Pause auto-refresh' : 'Enable auto-refresh'}
          >
            {autoRefreshEnabled ? (
              <>
                <Pause className="h-4 w-4 mr-2" />
                Pause
              </>
            ) : (
              <>
                <Play className="h-4 w-4 mr-2" />
                Auto
              </>
            )}
          </Button>

          <Button variant="outline" size="sm" onClick={fetchState} disabled={isLoading || !isConnected}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Content */}
      {isExpanded && (
        <div className="p-4">
          {isLoading && !deviceState ? (
            <div className="space-y-2">
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-3/4" />
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded animate-pulse w-1/2" />
            </div>
          ) : deviceState && Object.keys(deviceState).length > 0 ? (
            <div className="relative">
              {isLoading && (
                <div className="absolute top-2 right-2">
                  <RefreshCw className="h-4 w-4 text-blue-500 dark:text-yellow-400 animate-spin" />
                </div>
              )}
              <JsonDisplay data={deviceState} />
            </div>
          ) : (
            <div className="text-center text-gray-500 dark:text-gray-400 py-8">No state data available</div>
          )}
        </div>
      )}
    </div>
  );
}
