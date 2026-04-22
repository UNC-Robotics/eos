import { memo, useState, useEffect } from 'react';
import { ParameterSpec } from '@/lib/types/protocol';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';
import { restoreDefaultIfEmpty } from '@/lib/utils/protocolHelpers';
import { validateString } from '@/lib/validation/parameter-validation';

interface StringParameterFieldProps {
  name: string;
  spec: ParameterSpec;
  value: unknown;
  onChange: (value: unknown) => void;
}

export const StringParameterField = memo(({ name, spec, value, onChange }: StringParameterFieldProps) => {
  const [error, setError] = useState<string | undefined>();
  const displayValue = value !== undefined && value !== null ? String(value) : '';

  // Validate on value change
  useEffect(() => {
    if (value !== undefined && value !== null && value !== '') {
      const validation = validateString(value, spec);
      setError(validation.error);
    } else {
      setError(undefined);
    }
  }, [value, spec]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const rawValue = e.target.value;

    if (rawValue === '') {
      onChange(undefined);
    } else {
      onChange(rawValue);
    }
  };

  return (
    <div className="space-y-1">
      <label className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
        {name}
        <span className="px-1.5 py-0.5 rounded bg-gray-200 dark:bg-slate-600 text-[10px] font-medium text-gray-700 dark:text-gray-200">
          {spec.type}
        </span>
        {spec.desc && <DescriptionTooltip description={spec.desc} />}
      </label>
      <input
        type="text"
        value={displayValue}
        onChange={handleChange}
        onBlur={() => restoreDefaultIfEmpty(value, spec, onChange)}
        placeholder={`Enter ${name}`}
        className={`w-full px-2.5 py-1 text-sm border rounded-md focus:outline-none focus:ring-2 ${
          error
            ? 'border-red-500 focus:ring-red-500'
            : 'border-gray-300 dark:border-slate-600 focus:ring-blue-500 dark:focus:ring-yellow-500'
        } bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500`}
      />
      {error && <p className="mt-1 text-xs text-red-500 dark:text-red-400">{error}</p>}
    </div>
  );
});

StringParameterField.displayName = 'StringParameterField';
