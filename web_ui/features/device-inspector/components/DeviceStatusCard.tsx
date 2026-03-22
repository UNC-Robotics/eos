'use client';

import * as React from 'react';
import { RefreshCw, Clock } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Separator } from '@/components/ui/Separator';
import { toast } from '@/lib/utils/toast';
import { reloadDevice, getDeviceStatus } from '../api/inspector';
import type { SelectedDevice } from '@/lib/types/device-inspector';
import type { Device } from '@/lib/types/management';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

interface DeviceStatusCardProps {
  device: SelectedDevice;
  deviceInfo: Device | null;
  onStatusUpdate?: () => void;
}

export function DeviceStatusCard({ device, deviceInfo, onStatusUpdate }: DeviceStatusCardProps) {
  const { isConnected } = useOrchestratorConnected();
  const [isReloading, setIsReloading] = React.useState(false);
  const [lastUpdated, setLastUpdated] = React.useState<Date>(new Date());
  const [liveStatus, setLiveStatus] = React.useState<string | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = React.useState(false);

  const fetchLiveStatus = React.useCallback(async () => {
    setIsLoadingStatus(true);
    try {
      const status = await getDeviceStatus(device.labName, device.deviceName);
      setLiveStatus(status.status);
      setLastUpdated(new Date());
    } catch (_error) {
      console.error('Failed to fetch live status:', _error);
      // Fall back to device info status if available
      if (deviceInfo) {
        setLiveStatus(deviceInfo.status);
      }
    } finally {
      setIsLoadingStatus(false);
    }
  }, [device.labName, device.deviceName, deviceInfo]);

  // Fetch live status on mount and when device changes
  React.useEffect(() => {
    if (isConnected) fetchLiveStatus();
  }, [fetchLiveStatus, isConnected]);

  const handleReload = async () => {
    setIsReloading(true);
    try {
      const result = await reloadDevice(device.labName, device.deviceName);
      if (result.success) {
        toast.success(`Device ${device.deviceName} reloaded successfully`);
        // Wait a bit for the device to reload, then fetch status
        setTimeout(() => {
          fetchLiveStatus();
          onStatusUpdate?.();
        }, 1000);
      } else {
        toast.error(result.error || 'Failed to reload device');
      }
    } catch {
      toast.error('Failed to reload device');
    } finally {
      setIsReloading(false);
    }
  };

  const getStatusVariant = (status: string) => {
    switch (status.toUpperCase()) {
      case 'IDLE':
        return 'success';
      case 'BUSY':
        return 'warning';
      case 'ERROR':
        return 'error';
      case 'DISABLED':
        return 'default';
      default:
        return 'default';
    }
  };

  const displayStatus = liveStatus || deviceInfo?.status || 'UNKNOWN';

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1 min-w-0">
          <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 truncate">{device.deviceName}</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Lab: <span className="font-medium">{device.labName}</span>
          </p>
          {deviceInfo && (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Type: <span className="font-medium">{deviceInfo.type}</span>
            </p>
          )}
        </div>

        <Button variant="outline" size="sm" onClick={handleReload} disabled={isReloading || !isConnected}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isReloading ? 'animate-spin' : ''}`} />
          Reload
        </Button>
      </div>

      <Separator className="my-4" />

      {/* Status */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Status</span>
          {isLoadingStatus ? (
            <div className="h-6 w-16 bg-gray-200 dark:bg-gray-700 animate-pulse rounded" />
          ) : (
            <Badge variant={getStatusVariant(displayStatus)}>{displayStatus}</Badge>
          )}
        </div>

        {deviceInfo?.computer && (
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Computer</span>
            <span className="text-sm text-gray-600 dark:text-gray-400">{deviceInfo.computer}</span>
          </div>
        )}

        <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
          <div className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            <span>Last updated</span>
          </div>
          <span>{lastUpdated.toLocaleTimeString()}</span>
        </div>
      </div>
    </div>
  );
}
