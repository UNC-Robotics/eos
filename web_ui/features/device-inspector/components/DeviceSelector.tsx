'use client';

import * as React from 'react';
import { Search } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { ScrollArea } from '@/components/ui/ScrollArea';
import type { Device } from '@/lib/types/management';
import type { SelectedDevice } from '@/lib/types/device-inspector';

interface DeviceSelectorProps {
  devices: Device[];
  selectedDevice: SelectedDevice | null;
  onDeviceSelect: (device: SelectedDevice) => void;
}

export function DeviceSelector({ devices, selectedDevice, onDeviceSelect }: DeviceSelectorProps) {
  const [searchQuery, setSearchQuery] = React.useState('');

  // Group devices by lab
  const devicesByLab = React.useMemo(() => {
    const grouped = devices.reduce(
      (acc, device) => {
        if (!acc[device.lab_name]) {
          acc[device.lab_name] = [];
        }
        acc[device.lab_name].push(device);
        return acc;
      },
      {} as Record<string, Device[]>
    );

    // Sort labs alphabetically
    return Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b));
  }, [devices]);

  // Filter devices based on search query
  const filteredDevicesByLab = React.useMemo(() => {
    if (!searchQuery.trim()) {
      return devicesByLab;
    }

    const query = searchQuery.toLowerCase();
    return devicesByLab
      .map(([lab, labDevices]) => {
        const filtered = labDevices.filter(
          (device) =>
            device.name.toLowerCase().includes(query) ||
            device.type.toLowerCase().includes(query) ||
            lab.toLowerCase().includes(query)
        );
        return [lab, filtered] as [string, Device[]];
      })
      .filter(([, labDevices]) => labDevices.length > 0);
  }, [devicesByLab, searchQuery]);

  const isSelected = (labName: string, deviceName: string) => {
    return selectedDevice?.labName === labName && selectedDevice?.deviceName === deviceName;
  };

  return (
    <div className="flex flex-col h-full">
      {/* Search bar */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <Input
            type="text"
            placeholder="Search devices..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Device list */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-6">
          {filteredDevicesByLab.length === 0 ? (
            <div className="text-center text-gray-500 dark:text-gray-400 py-8">
              {searchQuery ? 'No devices found matching your search' : 'No devices available'}
            </div>
          ) : (
            filteredDevicesByLab.map(([lab, labDevices]) => (
              <div key={lab} className="space-y-2">
                {/* Lab header */}
                <div className="text-sm font-semibold text-gray-700 dark:text-gray-300 px-2">{lab}</div>

                {/* Devices in this lab */}
                <div className="space-y-1">
                  {labDevices.map((device) => (
                    <button
                      key={`${device.lab_name}-${device.name}`}
                      onClick={() =>
                        onDeviceSelect({
                          labName: device.lab_name,
                          deviceName: device.name,
                        })
                      }
                      className={`
                        w-full text-left px-3 py-2 rounded-lg transition-colors
                        ${
                          isSelected(device.lab_name, device.name)
                            ? 'bg-blue-100 dark:bg-yellow-500/10 border border-blue-300 dark:border-yellow-500'
                            : 'hover:bg-gray-100 dark:hover:bg-gray-800 border border-transparent'
                        }
                      `}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">
                            {device.name}
                          </div>
                          <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{device.type}</div>
                        </div>
                        <Badge
                          variant={device.status === 'ACTIVE' ? 'success' : 'default'}
                          className="flex-shrink-0 text-xs"
                        >
                          {device.status}
                        </Badge>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
