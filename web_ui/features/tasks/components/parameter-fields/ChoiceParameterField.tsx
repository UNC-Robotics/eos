import { memo, useState, useEffect } from 'react';
import { ParameterSpec } from '@/lib/types/protocol';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';
import { validateChoice } from '@/lib/validation/parameter-validation';

interface ChoiceParameterFieldProps {
  name: string;
  spec: ParameterSpec;
  value: unknown;
  onChange: (value: unknown) => void;
}

export const ChoiceParameterField = memo(({ name, spec, value, onChange }: ChoiceParameterFieldProps) => {
  const [error, setError] = useState<string | undefined>();
  const displayValue = value !== undefined && value !== null ? String(value) : '';

  // Validate on value change
  useEffect(() => {
    if (value !== undefined && value !== null && value !== '') {
      const validation = validateChoice(value, spec);
      setError(validation.error);
    } else {
      setError(undefined);
    }
  }, [value, spec]);

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const rawValue = e.target.value;

    if (rawValue === '') {
      onChange(undefined);
    } else {
      onChange(rawValue);
    }
  };

  const choices = spec.choices || [];

  return (
    <div className="border border-gray-200 dark:border-slate-700 rounded-md px-3 py-2 bg-white dark:bg-slate-800 space-y-1">
      <label className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
        {name}
        <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-slate-700 text-[10px] font-medium text-gray-500 dark:text-gray-400">
          {spec.type}
        </span>
        {spec.desc && <DescriptionTooltip description={spec.desc} />}
      </label>
      <select
        value={displayValue}
        onChange={handleChange}
        className={`w-full px-2.5 py-1 text-sm border rounded-md focus:outline-none focus:ring-2 ${
          error
            ? 'border-red-500 focus:ring-red-500'
            : 'border-gray-300 dark:border-slate-600 focus:ring-blue-500 dark:focus:ring-yellow-500'
        } bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100`}
      >
        <option value="">Select {name}</option>
        {choices.map((choice) => (
          <option key={choice} value={choice}>
            {choice}
          </option>
        ))}
      </select>
      {error && <p className="mt-1 text-xs text-red-500 dark:text-red-400">{error}</p>}
      {choices.length === 0 && (
        <p className="mt-1 text-xs text-amber-500 dark:text-amber-400">No choices defined for this parameter</p>
      )}
    </div>
  );
});

ChoiceParameterField.displayName = 'ChoiceParameterField';
