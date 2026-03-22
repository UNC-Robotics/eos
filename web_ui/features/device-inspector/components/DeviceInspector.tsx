'use client';

import * as React from 'react';
import { Microscope } from 'lucide-react';
import { DeviceSelector } from './DeviceSelector';
import { DeviceStatusCard } from './DeviceStatusCard';
import { DeviceStateViewer } from './DeviceStateViewer';
import { DeviceFunctionsPanel } from './DeviceFunctionsPanel';
import { FunctionCallDialog } from './FunctionCallDialog';
import { FunctionHistoryPanel } from './FunctionHistoryPanel';
import { useDeviceInspectorStore } from '@/lib/stores/deviceInspectorStore';
import type { Device } from '@/lib/types/management';
import type { DeviceFunction, SelectedDevice } from '@/lib/types/device-inspector';

interface DeviceInspectorProps {
  initialDevices: Device[];
}

export function DeviceInspector({ initialDevices }: DeviceInspectorProps) {
  const { selectedDevice, setSelectedDevice } = useDeviceInspectorStore();

  const [callDialogOpen, setCallDialogOpen] = React.useState(false);
  const [selectedFunction, setSelectedFunction] = React.useState<{
    name: string;
    def: DeviceFunction;
  } | null>(null);

  // Get device info from the initial devices list
  const selectedDeviceInfo = React.useMemo(() => {
    if (!selectedDevice) return null;
    return (
      initialDevices.find((d) => d.lab_name === selectedDevice.labName && d.name === selectedDevice.deviceName) || null
    );
  }, [selectedDevice, initialDevices]);

  const handleDeviceSelect = (device: SelectedDevice) => {
    setSelectedDevice(device);
  };

  const handleFunctionCall = (functionName: string, functionDef: DeviceFunction) => {
    setSelectedFunction({ name: functionName, def: functionDef });
    setCallDialogOpen(true);
  };

  return (
    <div className="flex h-full gap-6">
      {/* Left sidebar - Device selector */}
      <div className="w-80 flex-shrink-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        <DeviceSelector devices={initialDevices} selectedDevice={selectedDevice} onDeviceSelect={handleDeviceSelect} />
      </div>

      {/* Right panel - Inspector */}
      <div className="flex-1 min-w-0">
        {selectedDevice ? (
          <div className="space-y-6">
            {/* Device status card */}
            <DeviceStatusCard device={selectedDevice} deviceInfo={selectedDeviceInfo} />

            {/* Device state viewer */}
            <DeviceStateViewer device={selectedDevice} />

            {/* Device functions panel */}
            <DeviceFunctionsPanel device={selectedDevice} onFunctionCall={handleFunctionCall} />

            {/* Function call history */}
            <FunctionHistoryPanel />
          </div>
        ) : (
          /* Empty state */
          <div className="h-full flex flex-col items-center justify-center text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
            <Microscope className="h-16 w-16 mb-4 opacity-50" />
            <p className="text-lg font-medium">Select a device to inspect</p>
            <p className="text-sm">Choose a device from the list to view its state and call functions</p>
          </div>
        )}
      </div>

      {/* Function call dialog */}
      {selectedDevice && selectedFunction && (
        <FunctionCallDialog
          device={selectedDevice}
          functionName={selectedFunction.name}
          functionDef={selectedFunction.def}
          open={callDialogOpen}
          onOpenChange={setCallDialogOpen}
        />
      )}
    </div>
  );
}
