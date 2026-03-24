export const DEFAULT_PAGE_SIZE = 30;

export type SortDirection = 'asc' | 'desc';

export interface SortOption {
  column: string;
  direction: SortDirection;
}

export interface ColumnFilterOption {
  column: string;
  value: string | string[]; // string = text ILIKE, string[] = multiselect IN
}

export interface TableQueryOptions {
  limit?: number;
  offset?: number;
  sort?: SortOption;
  filters?: ColumnFilterOption[];
  search?: string;
}
