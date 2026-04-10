'use client';

import * as React from 'react';
import {
  ColumnDef,
  ColumnFiltersState,
  SortingState,
  VisibilityState,
  RowSelectionState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ChevronDown, Search, Filter, X } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { ColumnFilter } from './ColumnFilters';
import type { Table, Column } from '@tanstack/react-table';

// Helper to get a human-readable column name from the header definition
function getColumnDisplayName<TData>(column: Column<TData, unknown>): string {
  const header = column.columnDef.header;
  if (typeof header === 'string') {
    return header;
  }
  // Fallback to column id if header is a function
  return column.id;
}

// Extended column definition with filter metadata
export type DataTableColumnDef<TData, TValue = unknown> = ColumnDef<TData, TValue> & {
  enableColumnFilter?: boolean;
  filterType?: 'text' | 'select' | 'multiselect';
  filterOptions?: string[];
};

// Component for the select all checkbox header
function SelectAllCheckbox<TData>({ table }: { table: Table<TData> }) {
  const checkboxRef = React.useRef<HTMLInputElement>(null);
  const isSomePageRowsSelected = table.getIsSomePageRowsSelected();

  React.useEffect(() => {
    if (checkboxRef.current) {
      checkboxRef.current.indeterminate = isSomePageRowsSelected;
    }
  }, [isSomePageRowsSelected]);

  return (
    <input
      ref={checkboxRef}
      type="checkbox"
      checked={table.getIsAllPageRowsSelected()}
      onChange={table.getToggleAllPageRowsSelectedHandler()}
      aria-label="Select all rows"
      className="h-4 w-4 rounded border-gray-300 dark:border-slate-600 text-blue-600 dark:text-blue-500 focus:ring-2 focus:ring-blue-500 dark:bg-slate-700"
    />
  );
}

interface DataTableProps<TData, TValue> {
  columns: DataTableColumnDef<TData, TValue>[];
  data: TData[];
  searchPlaceholder?: string;
  searchColumn?: string;
  onRowClick?: (row: TData) => void;
  // Row selection props
  enableRowSelection?: boolean;
  onSelectionChange?: (selectedRows: TData[]) => void;
  // Bulk action toolbar
  bulkActions?: React.ReactNode;
  // Toolbar actions (always shown to the right of filters)
  toolbarActions?: React.ReactNode;
  // Server-side pagination props (opt-in)
  manualPagination?: boolean;
  totalRows?: number;
  pageIndex?: number;
  pageSize?: number;
  onPaginationChange?: (pageIndex: number, pageSize: number) => void;
  onSortingChange?: (sorting: SortingState) => void;
  onColumnFiltersChange?: (filters: ColumnFiltersState) => void;
  onGlobalFilterChange?: (search: string) => void;
}

export function DataTable<TData, TValue>({
  columns,
  data,
  searchPlaceholder = 'Search...',
  searchColumn: _searchColumn,
  onRowClick,
  enableRowSelection = false,
  onSelectionChange,
  bulkActions,
  toolbarActions,
  manualPagination = false,
  totalRows,
  pageIndex: controlledPageIndex,
  pageSize: controlledPageSize,
  onPaginationChange,
  onSortingChange: onSortingChangeProp,
  onColumnFiltersChange: onColumnFiltersChangeProp,
  onGlobalFilterChange: onGlobalFilterChangeProp,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({});
  const [globalFilter, setGlobalFilter] = React.useState('');
  const [showFilters, setShowFilters] = React.useState(false);
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});

  const effectivePageSize = manualPagination ? (controlledPageSize ?? 20) : 20;

  // Add checkbox column if row selection is enabled
  const columnsWithSelection = React.useMemo(() => {
    if (!enableRowSelection) return columns;

    return [
      {
        id: 'select',
        header: ({ table }) => <SelectAllCheckbox table={table} />,
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            aria-label="Select row"
            className="h-4 w-4 rounded border-gray-300 dark:border-slate-600 text-blue-600 dark:text-blue-500 focus:ring-2 focus:ring-blue-500 dark:bg-slate-700"
          />
        ),
        enableSorting: false,
        enableHiding: false,
      },
      ...columns,
    ] as DataTableColumnDef<TData, TValue>[];
  }, [columns, enableRowSelection]);

  // Forward state changes to parent via effects (not inside state setters, which causes
  // "Cannot update a component while rendering a different component" errors)
  React.useEffect(() => {
    if (manualPagination) onSortingChangeProp?.(sorting);
  }, [sorting]); // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    if (manualPagination) onColumnFiltersChangeProp?.(columnFilters);
  }, [columnFilters]); // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    if (manualPagination) onGlobalFilterChangeProp?.(globalFilter);
  }, [globalFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const table = useReactTable({
    data,
    columns: columnsWithSelection,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    ...(!manualPagination
      ? {
          getPaginationRowModel: getPaginationRowModel(),
          getSortedRowModel: getSortedRowModel(),
          getFilteredRowModel: getFilteredRowModel(),
        }
      : {}),
    ...(manualPagination
      ? {
          manualPagination: true,
          manualFiltering: true,
          manualSorting: true,
          pageCount: totalRows != null ? Math.ceil(totalRows / effectivePageSize) : -1,
        }
      : {}),
    onColumnVisibilityChange: setColumnVisibility,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: setRowSelection,
    globalFilterFn: 'includesString',
    filterFns: {
      arrIncludesSome: (row, columnId, filterValue: string[]) => {
        const value = row.getValue(columnId) as string;
        return filterValue.includes(value);
      },
    },
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      globalFilter,
      rowSelection,
      ...(manualPagination
        ? {
            pagination: {
              pageIndex: controlledPageIndex ?? 0,
              pageSize: effectivePageSize,
            },
          }
        : {}),
    },
    ...(!manualPagination
      ? {
          initialState: {
            pagination: { pageSize: 20 },
          },
        }
      : {}),
    enableRowSelection,
  });

  // Get filterable columns (excluding checkbox column)
  const filterableColumns = table
    .getAllColumns()
    .filter((column) => column.id !== 'select')
    .filter((column) => {
      const columnDef = column.columnDef as DataTableColumnDef<TData>;
      return columnDef.enableColumnFilter;
    });

  // Count active filters
  const activeFilterCount = columnFilters.length;

  // Get selected rows count
  const selectedCount = Object.keys(rowSelection).length;

  // Notify parent of selection changes
  React.useEffect(() => {
    if (onSelectionChange && enableRowSelection) {
      const selectedRows = table.getSelectedRowModel().rows.map((row) => row.original);
      onSelectionChange(selectedRows);
    }
  }, [rowSelection, onSelectionChange, enableRowSelection, table]);

  // Pagination helpers
  const displayedTotal = manualPagination ? (totalRows ?? 0) : table.getFilteredRowModel().rows.length;

  const currentPageIndex = manualPagination ? (controlledPageIndex ?? 0) : table.getState().pagination.pageIndex;

  const pageCount = table.getPageCount();

  const canPreviousPage = manualPagination ? currentPageIndex > 0 : table.getCanPreviousPage();

  const canNextPage = manualPagination ? currentPageIndex < pageCount - 1 : table.getCanNextPage();

  const goToPreviousPage = () => {
    if (manualPagination && onPaginationChange) {
      onPaginationChange(currentPageIndex - 1, effectivePageSize);
    } else {
      table.previousPage();
    }
  };

  const goToNextPage = () => {
    if (manualPagination && onPaginationChange) {
      onPaginationChange(currentPageIndex + 1, effectivePageSize);
    } else {
      table.nextPage();
    }
  };

  return (
    <div className="w-full space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 flex-1">
          {enableRowSelection && selectedCount > 0 ? (
            <div className="flex items-center gap-4">
              <span className="text-sm text-gray-700 dark:text-gray-300 font-medium">
                {selectedCount} row{selectedCount > 1 ? 's' : ''} selected
              </span>
              {bulkActions}
              <Button variant="outline" size="sm" onClick={() => table.resetRowSelection()} className="ml-2">
                Clear Selection
              </Button>
            </div>
          ) : (
            <div className="relative w-full max-w-sm">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-gray-500" />
              <Input
                placeholder={searchPlaceholder}
                value={globalFilter ?? ''}
                onChange={(event) => setGlobalFilter(event.target.value)}
                className="pl-9"
              />
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {filterableColumns.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => setShowFilters(!showFilters)} className="relative">
              <Filter className="mr-2 h-4 w-4" />
              Filters
              {activeFilterCount > 0 && (
                <span className="ml-2 flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 dark:bg-yellow-500 text-xs text-white dark:text-slate-900">
                  {activeFilterCount}
                </span>
              )}
            </Button>
          )}
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button variant="outline" size="sm">
                Columns <ChevronDown className="ml-2 h-4 w-4" />
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content className="w-48 rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-1 shadow-md z-50">
                {table
                  .getAllColumns()
                  .filter((column) => column.getCanHide())
                  .map((column) => {
                    return (
                      <DropdownMenu.CheckboxItem
                        key={column.id}
                        className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-gray-100 dark:hover:bg-slate-700 focus:bg-gray-100 dark:focus:bg-slate-700 data-[disabled]:pointer-events-none data-[disabled]:opacity-50 dark:text-gray-300"
                        checked={column.getIsVisible()}
                        onCheckedChange={(value) => column.toggleVisibility(!!value)}
                      >
                        <span className="flex-1">{getColumnDisplayName(column)}</span>
                        <DropdownMenu.ItemIndicator className="ml-2">
                          <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                            <path
                              fillRule="evenodd"
                              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                              clipRule="evenodd"
                            />
                          </svg>
                        </DropdownMenu.ItemIndicator>
                      </DropdownMenu.CheckboxItem>
                    );
                  })}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
          {toolbarActions}
        </div>
      </div>

      {/* Filter Panel */}
      {showFilters && filterableColumns.length > 0 && (
        <div className="rounded-md border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white">Column Filters</h3>
            {activeFilterCount > 0 && (
              <Button variant="ghost" size="sm" onClick={() => table.resetColumnFilters()} className="h-7 text-xs">
                Clear All
              </Button>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filterableColumns.map((column) => {
              const { filterType, filterOptions } = column.columnDef as DataTableColumnDef<TData>;
              return (
                <div key={column.id} className="space-y-1">
                  <label className="text-xs font-medium text-gray-700 dark:text-gray-300">
                    {getColumnDisplayName(column)}
                  </label>
                  <ColumnFilter column={column} filterType={filterType} filterOptions={filterOptions} />
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Active Filter Chips */}
      {activeFilterCount > 0 && (
        <div className="flex flex-wrap gap-2">
          {columnFilters.map((filter) => {
            const column = table.getColumn(filter.id);
            if (!column) return null;

            const value = filter.value;

            // Format the filter value for display
            let displayValue: string;
            if (Array.isArray(value)) {
              displayValue = value.join(', ');
            } else {
              displayValue = String(value);
            }

            return (
              <div
                key={filter.id}
                className="inline-flex items-center gap-1 rounded-md bg-blue-50 dark:bg-yellow-900/40 border border-blue-200 dark:border-yellow-700 px-2 py-1 text-xs font-medium text-blue-700 dark:text-yellow-300"
              >
                <span>{getColumnDisplayName(column)}:</span>
                <span className="font-normal">{displayValue}</span>
                <button
                  onClick={() => column.setFilterValue(undefined)}
                  className="ml-1 rounded-sm hover:bg-blue-100 dark:hover:bg-yellow-800 p-0.5"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Table */}
      <div className="rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50 dark:bg-slate-900 border-b border-gray-200 dark:border-slate-700">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  return (
                    <th
                      key={header.id}
                      className="h-12 px-4 text-left align-middle font-medium text-gray-700 dark:text-gray-300 text-sm"
                    >
                      {header.isPlaceholder ? null : (
                        <div
                          {...{
                            className: header.column.getCanSort()
                              ? 'cursor-pointer select-none flex items-center gap-2'
                              : '',
                            onClick: header.column.getToggleSortingHandler(),
                          }}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {{
                            asc: ' 🔼',
                            desc: ' 🔽',
                          }[header.column.getIsSorted() as string] ?? null}
                        </div>
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-slate-700">
            {table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className={`hover:bg-gray-50 dark:hover:bg-slate-700 transition-colors ${
                    row.getIsSelected() ? 'bg-blue-50 dark:bg-blue-900/30' : ''
                  } ${onRowClick ? 'cursor-pointer' : ''}`}
                  onClick={(e) => {
                    const target = e.target as HTMLElement;
                    if (onRowClick && target.tagName !== 'INPUT' && !target.closest('button')) {
                      onRowClick(row.original);
                    }
                  }}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3 text-sm dark:text-gray-300">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={columnsWithSelection.length} className="h-24 text-center text-gray-500 dark:text-gray-400">
                  No results found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-700 dark:text-gray-300">{displayedTotal} row(s) total.</div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={goToPreviousPage} disabled={!canPreviousPage}>
            Previous
          </Button>
          <div className="text-sm text-gray-700 dark:text-gray-300">
            Page {currentPageIndex + 1} of {pageCount}
          </div>
          <Button variant="outline" size="sm" onClick={goToNextPage} disabled={!canNextPage}>
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
