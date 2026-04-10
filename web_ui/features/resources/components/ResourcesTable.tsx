'use client';

import * as React from 'react';
import { RotateCcw, X } from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { DataTable, DataTableColumnDef } from '@/components/data-table/DataTable';
import { Button } from '@/components/ui/Button';
import { JsonDisplay } from '@/components/ui/JsonDisplay';
import { RefreshControl } from '@/components/ui/RefreshControl';
import { ConfirmDialog } from '@/components/dialogs/ConfirmDialog';
import { useServerTable } from '@/hooks/useServerTable';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';
import { getResources, resetResources } from '../api/resources';
import type { PaginatedResult, ResourceRow } from '@/lib/db/queries';

interface ResourcesTableProps {
  initialData: PaginatedResult<ResourceRow>;
}

export function ResourcesTable({ initialData }: ResourcesTableProps) {
  const { isConnected: _isConnected } = useOrchestratorConnected();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  const isConnected = mounted ? _isConnected : true;

  const [pollingInterval, setPollingInterval] = React.useState(5000);
  const [isResetting, setIsResetting] = React.useState(false);
  const [selectedResource, setSelectedResource] = React.useState<ResourceRow | null>(null);
  const [detailPanelOpen, setDetailPanelOpen] = React.useState(false);
  const [selectedRows, setSelectedRows] = React.useState<ResourceRow[]>([]);
  const [confirmDialog, setConfirmDialog] = React.useState<{
    title: string;
    message: string;
    resourceNames: string[];
  } | null>(null);
  const [resetError, setResetError] = React.useState<string | null>(null);

  const serverTable = useServerTable({
    fetchFn: getResources,
    initialData,
  });

  React.useEffect(() => {
    if (pollingInterval === 0) return;
    const intervalId = setInterval(() => {
      serverTable.refresh();
    }, pollingInterval);
    return () => clearInterval(intervalId);
  }, [pollingInterval, serverTable.refresh]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep detail panel in sync with refreshed data
  React.useEffect(() => {
    if (selectedResource) {
      const updated = serverTable.data.find((r) => r.name === selectedResource.name);
      if (updated) setSelectedResource(updated);
    }
  }, [serverTable.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleReset = React.useCallback(
    async (resourceNames: string[]) => {
      setIsResetting(true);
      try {
        const result = await resetResources(resourceNames);
        if (!result.success) {
          setResetError(result.error ?? 'Failed to reset resources');
          return;
        }
        setTimeout(() => serverTable.refresh(), 500);
        setTimeout(() => serverTable.refresh(), 500);
      } finally {
        setIsResetting(false);
      }
    },
    [serverTable]
  );

  const handleRowClick = (resource: ResourceRow) => {
    setSelectedResource(resource);
    setDetailPanelOpen(true);
  };

  const labs = React.useMemo(
    () => [...new Set(serverTable.data.map((r) => r.lab).filter(Boolean))].sort() as string[],
    [serverTable.data]
  );

  const columns: DataTableColumnDef<ResourceRow>[] = [
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
      accessorKey: 'lab',
      header: 'Lab',
      cell: ({ row }) => {
        const lab = row.getValue('lab') as string | null;
        return lab ?? <span className="text-gray-400">—</span>;
      },
      enableColumnFilter: true,
      filterType: 'text',
    },
    {
      id: 'meta',
      header: 'Metadata',
      cell: ({ row }) => {
        const text = JSON.stringify(row.original.meta);
        return (
          <code
            className="text-xs bg-gray-100 dark:bg-slate-800 px-2 py-1 rounded text-gray-700 dark:text-gray-300 block max-w-[300px] truncate"
            title={text}
          >
            {text}
          </code>
        );
      },
      enableSorting: false,
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          disabled={!isConnected || isResetting}
          onClick={(e) => {
            e.stopPropagation();
            setConfirmDialog({
              title: `Reset ${row.original.name}`,
              message: `Reset "${row.original.name}" to its default metadata?`,
              resourceNames: [row.original.name],
            });
          }}
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Reset
        </Button>
      ),
      enableSorting: false,
    },
  ];

  const bulkActions = (
    <Button
      variant="outline"
      size="sm"
      disabled={!isConnected || isResetting}
      onClick={() =>
        setConfirmDialog({
          title: `Reset ${selectedRows.length} resource(s)`,
          message: `Reset ${selectedRows.length} selected resource(s) to default metadata?`,
          resourceNames: selectedRows.map((r) => r.name),
        })
      }
    >
      <RotateCcw className="w-3.5 h-3.5" />
      Reset Selected
    </Button>
  );

  const toolbarActions = (
    <div className="flex items-center gap-2">
      {labs.length > 1 ? (
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <Button variant="outline" size="sm" disabled={!isConnected || isResetting}>
              Reset Lab
            </Button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              className="min-w-[160px] bg-white dark:bg-slate-800 rounded-md shadow-lg border border-gray-200 dark:border-slate-700 p-1 z-50"
              sideOffset={4}
            >
              {labs.map((lab) => (
                <DropdownMenu.Item
                  key={lab}
                  className="text-sm px-3 py-2 rounded cursor-pointer hover:bg-gray-100 dark:hover:bg-slate-700 text-gray-900 dark:text-gray-100 outline-none"
                  onSelect={() => {
                    const labResources = serverTable.data.filter((r) => r.lab === lab).map((r) => r.name);
                    setConfirmDialog({
                      title: `Reset ${lab} resources`,
                      message: `Reset all ${labResources.length} resource(s) in "${lab}" to default metadata?`,
                      resourceNames: labResources,
                    });
                  }}
                >
                  {lab}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      ) : labs.length === 1 ? (
        <Button
          variant="outline"
          size="sm"
          disabled={!isConnected || isResetting}
          onClick={() => {
            const labResources = serverTable.data.filter((r) => r.lab === labs[0]).map((r) => r.name);
            setConfirmDialog({
              title: `Reset ${labs[0]} resources`,
              message: `Reset all ${labResources.length} resource(s) in "${labs[0]}" to default metadata?`,
              resourceNames: labResources,
            });
          }}
        >
          Reset Lab
        </Button>
      ) : null}

      <Button
        variant="primary"
        size="sm"
        disabled={!isConnected || isResetting || serverTable.data.length === 0}
        onClick={() =>
          setConfirmDialog({
            title: 'Reset all resources',
            message: `Reset all ${serverTable.totalRows} resource(s) to default metadata?`,
            resourceNames: serverTable.data.map((r) => r.name),
          })
        }
      >
        Reset All
      </Button>

      <RefreshControl
        pollingInterval={pollingInterval}
        onIntervalChange={setPollingInterval}
        onRefresh={serverTable.refresh}
        isRefreshing={serverTable.isLoading}
      />
    </div>
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Resources</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1">View and reset resource state</p>
      </div>

      <div className="flex gap-4">
        <div className={`space-y-4 ${detailPanelOpen ? 'flex-1' : 'w-full'}`}>
          <DataTable
            columns={columns}
            data={serverTable.data}
            searchPlaceholder="Search resources..."
            onRowClick={mounted ? handleRowClick : undefined}
            enableRowSelection={mounted}
            onSelectionChange={setSelectedRows}
            bulkActions={bulkActions}
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
        </div>

        {detailPanelOpen && selectedResource && (
          <div className="w-96 border-l border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto self-start">
            <div className="flex items-start justify-between mb-6">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{selectedResource.name}</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">Resource Details</p>
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
              <div className="space-y-3">
                <div>
                  <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Type
                  </div>
                  <div className="mt-1 text-sm text-gray-900 dark:text-gray-100">{selectedResource.type}</div>
                </div>

                <div>
                  <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Lab
                  </div>
                  <div className="mt-1 text-sm text-gray-900 dark:text-gray-100">{selectedResource.lab ?? '—'}</div>
                </div>
              </div>

              {Object.keys(selectedResource.meta).length > 0 && (
                <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                  <JsonDisplay data={selectedResource.meta} label="Metadata" />
                </div>
              )}

              <div className="border-t border-gray-200 dark:border-slate-700 pt-4">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full"
                  disabled={!isConnected || isResetting}
                  onClick={() =>
                    setConfirmDialog({
                      title: `Reset ${selectedResource.name}`,
                      message: `Reset "${selectedResource.name}" to its default metadata?`,
                      resourceNames: [selectedResource.name],
                    })
                  }
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Reset to Default
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      <ConfirmDialog
        isOpen={confirmDialog !== null}
        onClose={() => setConfirmDialog(null)}
        onConfirm={() => {
          if (confirmDialog) handleReset(confirmDialog.resourceNames);
        }}
        title={confirmDialog?.title ?? ''}
        message={confirmDialog?.message ?? ''}
        confirmText="Reset"
        variant="warning"
      />

      <ConfirmDialog
        isOpen={resetError !== null}
        onClose={() => setResetError(null)}
        onConfirm={() => setResetError(null)}
        title="Reset Failed"
        message={resetError ?? ''}
        confirmText="OK"
        variant="danger"
      />
    </div>
  );
}
