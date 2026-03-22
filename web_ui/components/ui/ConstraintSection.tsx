import { X } from 'lucide-react';
import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';

interface ConstraintSectionProps<T> {
  label: string;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
  items: T[];
  onAdd: (value: string) => void;
  onRemove: (item: T) => void;
  options: ComboboxOption[];
  placeholder: string;
  emptyText: string;
  renderItem: (item: T) => string;
  getKey: (item: T) => string;
  color: 'blue' | 'green';
}

export function ConstraintSection<T>({
  label,
  enabled,
  onToggle,
  items,
  onAdd,
  onRemove,
  options,
  placeholder,
  emptyText,
  renderItem,
  getKey,
  color,
}: ConstraintSectionProps<T>) {
  const bgColor =
    color === 'blue'
      ? 'bg-blue-100 dark:bg-yellow-900/30 text-blue-700 dark:text-yellow-400'
      : 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400';

  return (
    <div>
      <label className="flex items-center gap-2 text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          className="rounded border-gray-300 dark:border-slate-600"
        />
        {label}
      </label>
      {enabled && (
        <div className="space-y-2">
          <Combobox options={options} value="" onChange={onAdd} placeholder={placeholder} emptyText={emptyText} />
          <div className="flex flex-wrap gap-1.5">
            {items.map((item) => (
              <span
                key={getKey(item)}
                className={`inline-flex items-center gap-1 px-2 py-1 text-xs ${bgColor} rounded`}
              >
                {renderItem(item)}
                <button type="button" onClick={() => onRemove(item)} className="hover:opacity-75">
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
