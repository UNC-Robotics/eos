import { useState, useCallback, useEffect, useRef, useTransition } from 'react';
import type { SortingState, ColumnFiltersState } from '@tanstack/react-table';
import { DEFAULT_PAGE_SIZE, type TableQueryOptions, type ColumnFilterOption, type SortOption } from '@/lib/types/table';
import type { PaginatedResult } from '@/lib/db/queries';
import { useDebouncedValue } from './useDebouncedValue';

interface UseServerTableOptions<T> {
  fetchFn: (options: TableQueryOptions) => Promise<PaginatedResult<T>>;
  initialData: PaginatedResult<T>;
  pageSize?: number;
  /** Map TanStack accessor keys to DB column names (only for keys that differ) */
  columnIdMap?: Record<string, string>;
}

export interface UseServerTableReturn<T> {
  data: T[];
  totalRows: number;
  pageIndex: number;
  pageSize: number;
  isLoading: boolean;
  onPaginationChange: (pageIndex: number, pageSize: number) => void;
  onSortingChange: (sorting: SortingState) => void;
  onColumnFiltersChange: (filters: ColumnFiltersState) => void;
  onGlobalFilterChange: (search: string) => void;
  refresh: () => Promise<void>;
}

function mapColumnId(id: string, columnIdMap?: Record<string, string>): string {
  return columnIdMap?.[id] ?? id;
}

function toSortOption(sorting: SortingState, columnIdMap?: Record<string, string>): SortOption | undefined {
  if (sorting.length === 0) return undefined;
  const { id, desc } = sorting[0];
  return { column: mapColumnId(id, columnIdMap), direction: desc ? 'desc' : 'asc' };
}

function toColumnFilters(filters: ColumnFiltersState, columnIdMap?: Record<string, string>): ColumnFilterOption[] {
  return filters
    .filter((f) => {
      if (Array.isArray(f.value)) return f.value.length > 0;
      return typeof f.value === 'string' && f.value.length > 0;
    })
    .map((f) => ({
      column: mapColumnId(f.id, columnIdMap),
      value: f.value as string | string[],
    }));
}

export function useServerTable<T>({
  fetchFn,
  initialData,
  pageSize: defaultPageSize = DEFAULT_PAGE_SIZE,
  columnIdMap,
}: UseServerTableOptions<T>): UseServerTableReturn<T> {
  const [data, setData] = useState<T[]>(initialData.data);
  const [totalRows, setTotalRows] = useState(initialData.total);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(defaultPageSize);
  const [isPending, startTransition] = useTransition();

  // Filter/sort state (TanStack format, converted on fetch)
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState('');

  // Debounce text inputs (global search and text column filters)
  const debouncedSearch = useDebouncedValue(globalFilter, 300);
  const debouncedFilters = useDebouncedValue(columnFilters, 300);

  // Track whether this is the initial mount to skip the first fetch
  const isInitialMount = useRef(true);

  // Build query options from current state
  const buildOptions = useCallback(
    (overridePageIndex?: number): TableQueryOptions => ({
      limit: pageSize,
      offset: (overridePageIndex ?? pageIndex) * pageSize,
      sort: toSortOption(sorting, columnIdMap),
      filters: toColumnFilters(debouncedFilters, columnIdMap),
      search: debouncedSearch || undefined,
    }),
    [pageSize, pageIndex, sorting, debouncedFilters, debouncedSearch, columnIdMap]
  );

  // Fetch data from server
  const fetchData = useCallback(
    async (options: TableQueryOptions) => {
      startTransition(async () => {
        try {
          const result = await fetchFn(options);
          setData(result.data);
          setTotalRows(result.total);
        } catch (error) {
          console.error('Failed to fetch table data:', error);
        }
      });
    },
    [fetchFn]
  );

  // Re-fetch when debounced filters/search/sort change — reset to page 0
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    setPageIndex(0);
    fetchData(buildOptions(0));
  }, [debouncedSearch, debouncedFilters, sorting]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-fetch when page changes (but not on filter/sort reset above)
  const prevPageRef = useRef(pageIndex);
  useEffect(() => {
    if (prevPageRef.current !== pageIndex) {
      prevPageRef.current = pageIndex;
      fetchData(buildOptions());
    }
  }, [pageIndex]); // eslint-disable-line react-hooks/exhaustive-deps

  // Polling refresh — re-fetches with current state
  const refresh = useCallback(async () => {
    await fetchData(buildOptions());
  }, [fetchData, buildOptions]);

  const onPaginationChange = useCallback((newPageIndex: number, newPageSize: number) => {
    setPageSize(newPageSize);
    setPageIndex(newPageIndex);
  }, []);

  return {
    data,
    totalRows,
    pageIndex,
    pageSize,
    isLoading: isPending,
    onPaginationChange,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    refresh,
  };
}
