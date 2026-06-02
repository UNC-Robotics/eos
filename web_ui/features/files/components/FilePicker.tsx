'use client';

import * as React from 'react';
import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';
import { searchFiles } from '@/features/files/api/files';

interface FilePickerProps {
  value?: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

/**
 * Combobox of SeaweedFS keys with debounced async search. Typing a custom key is
 * allowed (useful for on-demand tasks).
 */
export function FilePicker({ value, onChange, placeholder }: FilePickerProps) {
  const [options, setOptions] = React.useState<ComboboxOption[]>([]);
  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const search = React.useCallback((query: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      searchFiles(query)
        .then((entries) =>
          setOptions(entries.filter((e) => !e.key.startsWith('rag/')).map((e) => ({ value: e.key, label: e.key })))
        )
        .catch(() => setOptions([]));
    }, 250);
  }, []);

  // Populate once on mount; subsequent searches are driven by the search box.
  React.useEffect(() => {
    search(value ?? '');
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Combobox
      options={options}
      value={value}
      onChange={onChange}
      onSearchChange={search}
      allowCustomValue
      customValueHint="Custom key"
      placeholder={placeholder ?? 'Select or type a file key'}
      searchPlaceholder="Search files..."
      emptyText="No matching files"
    />
  );
}
