'use client';

import * as React from 'react';
import * as Popover from '@radix-ui/react-popover';
import { Check, ChevronDown, Search } from 'lucide-react';
import { cn } from '@/lib/utils/cn';

export interface ComboboxOption {
  value: string;
  label: string;
  description?: string;
  disabled?: boolean;
  /** Group label for visual grouping. Consecutive options with the same group get a shared header. */
  group?: string;
}

export interface ComboboxProps {
  options: ComboboxOption[];
  value?: string;
  onChange: (value: string) => void;
  placeholder?: string;
  emptyText?: string;
  searchPlaceholder?: string;
  className?: string;
  disabled?: boolean;
  /** When true, allows typing a custom value that isn't in the options list. */
  allowCustomValue?: boolean;
}

export function Combobox({
  options,
  value,
  onChange,
  placeholder = 'Select...',
  emptyText = 'No results found',
  searchPlaceholder = 'Search...',
  className,
  disabled = false,
  allowCustomValue = false,
}: ComboboxProps) {
  const [open, setOpen] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState('');
  const searchInputRef = React.useRef<HTMLInputElement>(null);

  const filteredOptions = React.useMemo(() => {
    if (!searchQuery) return options;
    const query = searchQuery.toLowerCase();
    return options.filter(
      (opt) =>
        opt.label.toLowerCase().includes(query) ||
        opt.description?.toLowerCase().includes(query) ||
        opt.value.toLowerCase().includes(query) ||
        opt.group?.toLowerCase().includes(query)
    );
  }, [options, searchQuery]);

  // Whether the search query exactly matches an existing option value
  const queryMatchesOption = React.useMemo(
    () => options.some((opt) => opt.value === searchQuery.trim()),
    [options, searchQuery]
  );

  // Show "Use: ..." entry when custom values are allowed and query doesn't match an option
  const showCustomEntry = allowCustomValue && searchQuery.trim() && !queryMatchesOption;

  const selectedOption = React.useMemo(() => options.find((opt) => opt.value === value), [options, value]);

  // For allowCustomValue, show the raw value if it doesn't match any option
  const displayLabel = selectedOption?.label || (allowCustomValue && value ? value : undefined);

  React.useEffect(() => {
    if (open) setTimeout(() => searchInputRef.current?.focus(), 0);
    else setSearchQuery('');
  }, [open]);

  const handleSelect = React.useCallback(
    (optionValue: string) => {
      onChange(optionValue);
      setOpen(false);
    },
    [onChange]
  );

  const handleKeyDown = React.useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
      else if (e.key === 'Enter') {
        e.preventDefault();
        if (showCustomEntry) {
          handleSelect(searchQuery.trim());
        } else if (filteredOptions.length > 0) {
          const firstEnabled = filteredOptions.find((opt) => !opt.disabled);
          if (firstEnabled) handleSelect(firstEnabled.value);
        }
      }
    },
    [filteredOptions, handleSelect, showCustomEntry, searchQuery]
  );

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            'flex h-10 w-full items-center justify-between rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100',
            'focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50',
            className
          )}
        >
          <span className={cn('truncate', !displayLabel && 'text-gray-400 dark:text-gray-500')}>
            {displayLabel || placeholder}
          </span>
          <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </button>
      </Popover.Trigger>

      <Popover.Portal>
        <Popover.Content
          className="z-50 w-[var(--radix-popover-trigger-width)] rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-md"
          align="start"
          sideOffset={4}
          onWheel={(e) => e.stopPropagation()}
        >
          <div className="flex items-center border-b border-gray-200 dark:border-slate-700 px-3 py-2">
            <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
            <input
              ref={searchInputRef}
              type="text"
              placeholder={searchPlaceholder}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              className="w-full text-sm outline-none placeholder:text-gray-400 dark:placeholder:text-gray-500 bg-transparent text-gray-900 dark:text-gray-100"
            />
          </div>

          <div className="max-h-[300px] overflow-y-auto p-1" onWheel={(e) => e.stopPropagation()}>
            {/* Custom value entry */}
            {showCustomEntry && (
              <button
                type="button"
                onClick={() => handleSelect(searchQuery.trim())}
                className={cn(
                  'relative flex w-full items-center rounded-sm px-2 py-2 text-sm outline-none',
                  'hover:bg-gray-100 dark:hover:bg-slate-700 focus:bg-gray-100 dark:focus:bg-slate-700'
                )}
              >
                <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                  {value === searchQuery.trim() && <Check className="h-4 w-4 text-blue-600 dark:text-blue-400" />}
                </span>
                <div className="ml-3 flex flex-col items-start min-w-0 flex-1">
                  <span className="font-medium text-gray-900 dark:text-gray-100">Use: {searchQuery.trim()}</span>
                  <span className="text-xs text-gray-500 dark:text-gray-400">Custom model</span>
                </div>
              </button>
            )}

            {filteredOptions.length === 0 && !showCustomEntry ? (
              <div className="py-6 text-center text-sm text-gray-500 dark:text-gray-400">{emptyText}</div>
            ) : (
              filteredOptions.map((option, i) => {
                const prevGroup = i > 0 ? filteredOptions[i - 1].group : undefined;
                const showGroupHeader = option.group && option.group !== prevGroup;
                return (
                  <React.Fragment key={option.value}>
                    {showGroupHeader && (
                      <div
                        className={cn(
                          'px-3 py-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400 select-none',
                          i > 0 && 'border-t border-gray-200 dark:border-slate-700 mt-1 pt-2'
                        )}
                      >
                        {option.group}
                      </div>
                    )}
                    <button
                      type="button"
                      disabled={option.disabled}
                      onClick={() => !option.disabled && handleSelect(option.value)}
                      className={cn(
                        'relative flex w-full items-center rounded-sm px-2 py-2 text-sm outline-none',
                        'hover:bg-gray-100 dark:hover:bg-slate-700 focus:bg-gray-100 dark:focus:bg-slate-700 disabled:pointer-events-none disabled:opacity-50',
                        value === option.value && 'bg-gray-50 dark:bg-slate-700/50'
                      )}
                    >
                      <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                        {value === option.value && <Check className="h-4 w-4 text-blue-600 dark:text-blue-400" />}
                      </span>
                      <div className="ml-3 flex flex-col items-start min-w-0 flex-1">
                        <span className="font-medium text-gray-900 dark:text-gray-100">{option.label}</span>
                        {option.description && (
                          <span
                            className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-full"
                            title={option.description}
                          >
                            {option.description}
                          </span>
                        )}
                      </div>
                    </button>
                  </React.Fragment>
                );
              })
            )}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
