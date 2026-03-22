'use client';

import * as React from 'react';
import { Column } from '@tanstack/react-table';
import { Input } from '@/components/ui/Input';
import * as Select from '@radix-ui/react-select';
import { Check, ChevronDown } from 'lucide-react';

interface ColumnFilterProps<TData> {
  column: Column<TData, unknown>;
  filterType?: 'text' | 'select' | 'multiselect';
  filterOptions?: string[];
}

export function ColumnFilter<TData>({ column, filterType = 'text', filterOptions = [] }: ColumnFilterProps<TData>) {
  // Use state to track filter value for proper reactivity
  const [filterValue, setFilterValue] = React.useState(() => column.getFilterValue());

  // Sync with column filter value changes
  React.useEffect(() => {
    setFilterValue(column.getFilterValue());
  }, [column]);

  const handleTextChange = (value: string) => {
    setFilterValue(value);
    column.setFilterValue(value || undefined);
  };

  if (filterType === 'text') {
    return (
      <Input
        placeholder={`Filter ${column.id}...`}
        value={(filterValue as string) ?? ''}
        onChange={(e) => handleTextChange(e.target.value)}
        className="h-8 text-sm"
      />
    );
  }

  if (filterType === 'select' || filterType === 'multiselect') {
    const selectedValues = filterType === 'multiselect' ? ((filterValue as string[]) ?? []) : [];
    const singleValue = filterType === 'select' ? ((filterValue as string) ?? '') : '';

    if (filterType === 'multiselect') {
      return (
        <div className="space-y-1">
          {filterOptions.map((option) => (
            <label
              key={option}
              className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 dark:hover:bg-slate-700 px-2 py-1 rounded"
            >
              <input
                type="checkbox"
                checked={selectedValues.includes(option)}
                onChange={(e) => {
                  const newValue = e.target.checked
                    ? [...selectedValues, option]
                    : selectedValues.filter((v) => v !== option);
                  column.setFilterValue(newValue.length > 0 ? newValue : undefined);
                }}
                className="rounded border-gray-300 dark:border-slate-600 text-blue-600 dark:text-blue-500 focus:ring-blue-500 dark:bg-slate-700"
              />
              <span className="text-sm dark:text-gray-300">{option}</span>
            </label>
          ))}
        </div>
      );
    }

    return (
      <Select.Root value={singleValue} onValueChange={(value) => column.setFilterValue(value || undefined)}>
        <Select.Trigger className="flex h-8 w-full items-center justify-between rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 dark:focus:ring-blue-500">
          <Select.Value placeholder={`Select ${column.id}...`} />
          <Select.Icon>
            <ChevronDown className="h-4 w-4 opacity-50" />
          </Select.Icon>
        </Select.Trigger>
        <Select.Portal>
          <Select.Content className="overflow-hidden rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-md z-50">
            <Select.Viewport className="p-1">
              <Select.Item
                value=""
                className="relative flex cursor-pointer select-none items-center rounded-sm px-8 py-1.5 text-sm text-gray-900 dark:text-gray-100 outline-none hover:bg-gray-100 dark:hover:bg-slate-700 focus:bg-gray-100 dark:focus:bg-slate-700"
              >
                <Select.ItemText>All</Select.ItemText>
              </Select.Item>
              {filterOptions.map((option) => (
                <Select.Item
                  key={option}
                  value={option}
                  className="relative flex cursor-pointer select-none items-center rounded-sm px-8 py-1.5 text-sm text-gray-900 dark:text-gray-100 outline-none hover:bg-gray-100 dark:hover:bg-slate-700 focus:bg-gray-100 dark:focus:bg-slate-700"
                >
                  <Select.ItemIndicator className="absolute left-2 inline-flex items-center">
                    <Check className="h-4 w-4" />
                  </Select.ItemIndicator>
                  <Select.ItemText>{option}</Select.ItemText>
                </Select.Item>
              ))}
            </Select.Viewport>
          </Select.Content>
        </Select.Portal>
      </Select.Root>
    );
  }

  return null;
}
