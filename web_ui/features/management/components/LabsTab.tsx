'use client';

import * as React from 'react';
import { Download, Upload, RefreshCw } from 'lucide-react';
import { DataTable, DataTableColumnDef } from '@/components/data-table/DataTable';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { ConfirmationDialog } from './dialogs/ConfirmationDialog';
import { loadLabs, unloadLabs, reloadLabs } from '../api/labs';
import type { Lab } from '@/lib/types/management';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

interface LabsTabProps {
  initialLabs: Lab[];
}

export function LabsTab({ initialLabs }: LabsTabProps) {
  const { isConnected } = useOrchestratorConnected();
  const [selectedRows, setSelectedRows] = React.useState<Lab[]>([]);
  const [actionDialogOpen, setActionDialogOpen] = React.useState(false);
  const [currentAction, setCurrentAction] = React.useState<'load' | 'unload' | 'reload' | null>(null);

  const columns: DataTableColumnDef<Lab>[] = [
    {
      accessorKey: 'name',
      header: 'Lab Name',
      cell: ({ row }) => <div className="font-medium">{row.getValue('name')}</div>,
    },
    {
      accessorKey: 'loaded',
      header: 'Status',
      cell: ({ row }) => {
        const loaded = row.getValue('loaded') as boolean;
        return <Badge variant={loaded ? 'success' : 'default'}>{loaded ? 'Loaded' : 'Unloaded'}</Badge>;
      },
      enableColumnFilter: true,
      filterType: 'multiselect',
      filterOptions: ['true', 'false'],
      filterFn: (row, columnId, filterValue: string[]) => {
        const value = String(row.getValue(columnId));
        return filterValue.includes(value);
      },
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => {
        const lab = row.original;
        return (
          <div className="flex items-center gap-2">
            {!lab.loaded && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleActionSingle('load', lab.name)}
                disabled={!isConnected}
              >
                <Download className="h-4 w-4 mr-1" />
                Load
              </Button>
            )}
            {lab.loaded && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleActionSingle('unload', lab.name)}
                  disabled={!isConnected}
                >
                  <Upload className="h-4 w-4 mr-1" />
                  Unload
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleActionSingle('reload', lab.name)}
                  disabled={!isConnected}
                >
                  <RefreshCw className="h-4 w-4 mr-1" />
                  Reload
                </Button>
              </>
            )}
          </div>
        );
      },
    },
  ];

  const handleActionSingle = (action: 'load' | 'unload' | 'reload', labName: string) => {
    const lab = initialLabs.find((l) => l.name === labName);
    if (lab) {
      setSelectedRows([lab]);
      setCurrentAction(action);
      setActionDialogOpen(true);
    }
  };

  const handleActionSelected = (action: 'load' | 'unload' | 'reload') => {
    setCurrentAction(action);
    setActionDialogOpen(true);
  };

  const handleActionConfirm = async () => {
    const labNames = selectedRows.map((row) => row.name);
    let result;

    switch (currentAction) {
      case 'load':
        result = await loadLabs(labNames);
        break;
      case 'unload':
        result = await unloadLabs(labNames);
        break;
      case 'reload':
        result = await reloadLabs(labNames);
        break;
      default:
        return;
    }

    if (!result.success) {
      throw new Error(result.error);
    }
  };

  const getDialogConfig = () => {
    switch (currentAction) {
      case 'load':
        return {
          title: 'Load Labs',
          description: 'Are you sure you want to load these labs? This will initialize all lab devices and resources.',
          confirmLabel: 'Load',
          variant: 'default' as const,
        };
      case 'unload':
        return {
          title: 'Unload Labs',
          description:
            'Are you sure you want to unload these labs? This will shut down all lab devices and release resources.',
          confirmLabel: 'Unload',
          variant: 'destructive' as const,
        };
      case 'reload':
        return {
          title: 'Reload Labs',
          description:
            'Are you sure you want to reload these labs? This will restart all lab devices and refresh configurations.',
          confirmLabel: 'Reload',
          variant: 'default' as const,
        };
      default:
        return {
          title: '',
          description: '',
          confirmLabel: 'Confirm',
          variant: 'default' as const,
        };
    }
  };

  // Filter selected rows based on current action validity
  const getValidSelectedRows = () => {
    if (!currentAction) return selectedRows;

    return selectedRows.filter((row) => {
      if (currentAction === 'load') return !row.loaded;
      if (currentAction === 'unload' || currentAction === 'reload') return row.loaded;
      return false;
    });
  };

  const validSelectedRows = getValidSelectedRows();

  const bulkActions = selectedRows.length > 0 && (
    <>
      {selectedRows.some((row) => !row.loaded) && (
        <Button
          variant="primary"
          size="sm"
          onClick={() => handleActionSelected('load')}
          disabled={!selectedRows.some((row) => !row.loaded) || !isConnected}
        >
          <Download className="h-4 w-4 mr-1" />
          Load Selected
        </Button>
      )}
      {selectedRows.some((row) => row.loaded) && (
        <>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleActionSelected('unload')}
            disabled={!selectedRows.some((row) => row.loaded) || !isConnected}
          >
            <Upload className="h-4 w-4 mr-1" />
            Unload Selected
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleActionSelected('reload')}
            disabled={!selectedRows.some((row) => row.loaded) || !isConnected}
          >
            <RefreshCw className="h-4 w-4 mr-1" />
            Reload Selected
          </Button>
        </>
      )}
    </>
  );

  const dialogConfig = getDialogConfig();

  return (
    <div className="space-y-4">
      <DataTable
        columns={columns}
        data={initialLabs}
        searchPlaceholder="Search labs..."
        enableRowSelection
        onSelectionChange={setSelectedRows}
        bulkActions={bulkActions}
      />

      <ConfirmationDialog
        open={actionDialogOpen}
        onOpenChange={setActionDialogOpen}
        title={dialogConfig.title}
        description={dialogConfig.description}
        confirmLabel={dialogConfig.confirmLabel}
        variant={dialogConfig.variant}
        items={validSelectedRows.map((row) => row.name)}
        onConfirm={handleActionConfirm}
      />
    </div>
  );
}
