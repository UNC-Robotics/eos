'use client';

import * as React from 'react';
import { RefreshCw } from 'lucide-react';
import { DataTable, DataTableColumnDef } from '@/components/data-table/DataTable';
import { Button } from '@/components/ui/Button';
import { ConfirmationDialog } from './dialogs/ConfirmationDialog';
import { reloadTaskPlugins } from '../api/taskPlugins';
import type { TaskPluginInfo } from '@/lib/types/management';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

interface TaskPluginsTabProps {
  initialTaskPlugins: TaskPluginInfo[];
}

export function TaskPluginsTab({ initialTaskPlugins }: TaskPluginsTabProps) {
  const { isConnected } = useOrchestratorConnected();
  const [selectedRows, setSelectedRows] = React.useState<TaskPluginInfo[]>([]);
  const [reloadDialogOpen, setReloadDialogOpen] = React.useState(false);

  const columns: DataTableColumnDef<TaskPluginInfo>[] = [
    {
      accessorKey: 'type',
      header: 'Task Type',
      cell: ({ row }) => <div className="font-medium">{row.getValue('type')}</div>,
    },
    {
      accessorKey: 'description',
      header: 'Description',
      cell: ({ row }) => {
        const description = row.getValue('description') as string | undefined;
        return (
          <div className="text-gray-600 dark:text-gray-400">
            {description || <span className="italic text-gray-400 dark:text-gray-500">No description</span>}
          </div>
        );
      },
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => (
        <Button
          variant="outline"
          size="sm"
          onClick={() => handleReloadSingle(row.original.type)}
          disabled={!isConnected}
        >
          <RefreshCw className="h-4 w-4 mr-1" />
          Reload
        </Button>
      ),
    },
  ];

  const handleReloadSingle = (taskType: string) => {
    setSelectedRows([{ type: taskType }]);
    setReloadDialogOpen(true);
  };

  const handleReloadSelected = () => {
    setReloadDialogOpen(true);
  };

  const handleReloadConfirm = async () => {
    const taskTypes = selectedRows.map((row) => row.type);
    const result = await reloadTaskPlugins(taskTypes);

    if (!result.success) {
      throw new Error(result.error);
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
        data={initialTaskPlugins}
        searchPlaceholder="Search task types..."
        enableRowSelection
        onSelectionChange={setSelectedRows}
        bulkActions={bulkActions}
      />

      <ConfirmationDialog
        open={reloadDialogOpen}
        onOpenChange={setReloadDialogOpen}
        title="Reload Task Plugins"
        description="Are you sure you want to reload these task plugins? The plugin code will be refreshed."
        confirmLabel="Reload"
        variant="default"
        items={selectedRows.map((row) => row.type)}
        onConfirm={handleReloadConfirm}
      />
    </div>
  );
}
