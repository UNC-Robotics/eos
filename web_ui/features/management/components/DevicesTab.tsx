'use client';

import * as React from 'react';
import { RefreshCw, Eye } from 'lucide-react';
import { DataTable, DataTableColumnDef } from '@/components/data-table/DataTable';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/Sheet';
import { JsonDisplay } from '@/components/ui/JsonDisplay';
import { ConfirmationDialog } from './dialogs/ConfirmationDialog';
import { reloadDevices, getDeviceReport } from '../api/devices';
import type { Device, DeviceReport } from '@/lib/types/management';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

interface DevicesTabProps {
  initialDevices: Device[];
}

export function DevicesTab({ initialDevices }: DevicesTabProps) {
  const { isConnected } = useOrchestratorConnected();
  const [selectedRows, setSelectedRows] = React.useState<Device[]>([]);
  const [reloadDialogOpen, setReloadDialogOpen] = React.useState(false);
  const [selectedDevice, setSelectedDevice] = React.useState<Device | null>(null);
  const [detailPanelOpen, setDetailPanelOpen] = React.useState(false);
  const [deviceReport, setDeviceReport] = React.useState<DeviceReport | null>(null);
  const [loadingReport, setLoadingReport] = React.useState(false);

  // Get unique labs for filter options
  const uniqueLabs = Array.from(new Set(initialDevices.map((d) => d.lab_name))).sort();

  const columns: DataTableColumnDef<Device>[] = [
    {
      accessorKey: 'name',
      header: 'Device Name',
      cell: ({ row }) => <div className="font-medium">{row.getValue('name')}</div>,
    },
    {
      accessorKey: 'lab_name',
      header: 'Lab',
      cell: ({ row }) => <div className="text-gray-700 dark:text-gray-300">{row.getValue('lab_name')}</div>,
      enableColumnFilter: true,
      filterType: 'multiselect',
      filterOptions: uniqueLabs,
      filterFn: 'arrIncludesSome',
    },
    {
      accessorKey: 'type',
      header: 'Type',
      cell: ({ row }) => <div className="text-gray-600 dark:text-gray-400">{row.getValue('type')}</div>,
    },
    {
      accessorKey: 'computer',
      header: 'Computer',
      cell: ({ row }) => <div className="text-gray-600 dark:text-gray-400">{row.getValue('computer')}</div>,
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const status = row.getValue('status') as string;
        return <Badge variant={status === 'ACTIVE' ? 'success' : 'default'}>{status}</Badge>;
      },
      enableColumnFilter: true,
      filterType: 'multiselect',
      filterOptions: ['ACTIVE', 'INACTIVE'],
      filterFn: 'arrIncludesSome',
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => {
        const device = row.original;
        return (
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!isConnected}
              onClick={(e) => {
                e.stopPropagation();
                handleViewDevice(device);
              }}
            >
              <Eye className="h-4 w-4 mr-1" />
              View
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!isConnected}
              onClick={(e) => {
                e.stopPropagation();
                handleReloadSingle(device);
              }}
            >
              <RefreshCw className="h-4 w-4 mr-1" />
              Reload
            </Button>
          </div>
        );
      },
    },
  ];

  const handleViewDevice = async (device: Device) => {
    setSelectedDevice(device);
    setDeviceReport(null);
    setDetailPanelOpen(true);
    setLoadingReport(true);

    try {
      const report = await getDeviceReport(device.lab_name, device.name);
      setDeviceReport(report);
    } catch (error) {
      console.error('Failed to fetch device report:', error);
      setDeviceReport({ error: 'Failed to load device report' });
    } finally {
      setLoadingReport(false);
    }
  };

  const handleReloadSingle = (device: Device) => {
    setSelectedRows([device]);
    setReloadDialogOpen(true);
  };

  const handleReloadSelected = () => {
    setReloadDialogOpen(true);
  };

  const handleReloadConfirm = async () => {
    // Group devices by lab
    const devicesByLab = selectedRows.reduce(
      (acc, device) => {
        if (!acc[device.lab_name]) {
          acc[device.lab_name] = [];
        }
        acc[device.lab_name].push(device.name);
        return acc;
      },
      {} as Record<string, string[]>
    );

    // Reload devices for each lab
    const reloadPromises = Object.entries(devicesByLab).map(([labName, deviceNames]) =>
      reloadDevices(labName, deviceNames)
    );

    const results = await Promise.all(reloadPromises);
    const failedResults = results.filter((r) => !r.success);

    if (failedResults.length > 0) {
      throw new Error(failedResults.map((r) => r.error).join(', '));
    }
  };

  const bulkActions = selectedRows.length > 0 && (
    <Button variant="primary" size="sm" onClick={handleReloadSelected} disabled={!isConnected}>
      <RefreshCw className="h-4 w-4 mr-1" />
      Reload Selected
    </Button>
  );

  return (
    <div className="space-y-4">
      <DataTable
        columns={columns}
        data={initialDevices}
        searchPlaceholder="Search devices..."
        enableRowSelection
        onSelectionChange={setSelectedRows}
        bulkActions={bulkActions}
      />

      <ConfirmationDialog
        open={reloadDialogOpen}
        onOpenChange={setReloadDialogOpen}
        title="Reload Devices"
        description="Are you sure you want to reload these devices? The device plugins will be refreshed and reinitialize."
        confirmLabel="Reload"
        variant="default"
        items={selectedRows.map((row) => `${row.lab_name}.${row.name}`)}
        onConfirm={handleReloadConfirm}
      />

      {/* Device Detail Panel */}
      <Sheet open={detailPanelOpen} onOpenChange={setDetailPanelOpen}>
        <SheetContent side="right" className="overflow-y-auto w-[600px]">
          {selectedDevice && (
            <>
              <SheetHeader>
                <SheetTitle>{selectedDevice.name}</SheetTitle>
                <SheetDescription>Device in {selectedDevice.lab_name}</SheetDescription>
              </SheetHeader>

              <div className="mt-6 space-y-6">
                {/* Basic Info */}
                <div className="space-y-3">
                  <div>
                    <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                      Type
                    </div>
                    <div className="mt-1 text-sm text-gray-900 dark:text-gray-100">{selectedDevice.type}</div>
                  </div>

                  <div>
                    <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                      Computer
                    </div>
                    <div className="mt-1 text-sm text-gray-900 dark:text-gray-100">{selectedDevice.computer}</div>
                  </div>

                  <div>
                    <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                      Status
                    </div>
                    <div className="mt-1">
                      <Badge variant={selectedDevice.status === 'ACTIVE' ? 'success' : 'default'}>
                        {selectedDevice.status}
                      </Badge>
                    </div>
                  </div>
                </div>

                {/* Metadata */}
                {selectedDevice.meta && Object.keys(selectedDevice.meta).length > 0 && (
                  <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                    <div className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">Metadata</div>
                    <JsonDisplay data={selectedDevice.meta} />
                  </div>
                )}

                {/* Device Report */}
                <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                  <div className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">Device Report</div>
                  {loadingReport ? (
                    <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                      <RefreshCw className="h-4 w-4 animate-spin" />
                      Loading report...
                    </div>
                  ) : deviceReport ? (
                    <JsonDisplay data={deviceReport} />
                  ) : (
                    <div className="text-sm text-gray-500 dark:text-gray-400 italic">No report available</div>
                  )}
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
