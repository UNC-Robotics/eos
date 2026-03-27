import { memo, useState, useEffect } from 'react';
import { ParameterSpec } from '@/lib/types/protocol';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';
import { validateNumeric } from '@/lib/validation/parameter-validation';

interface NumericParameterFieldProps {
  name: string;
  spec: ParameterSpec;
  value: unknown;
  onChange: (value: unknown) => void;
}

export const NumericParameterField = memo(({ name, spec, value, onChange }: NumericParameterFieldProps) => {
  const [error, setError] = useState<string | undefined>();
  const displayValue = value !== undefined && value !== null ? String(value) : '';

  // Validate on value change
  useEffect(() => {
    if (value !== undefined && value !== null && value !== '') {
      const validation = validateNumeric(value, spec);
      setError(validation.error);
    } else {
      setError(undefined);
    }
  }, [value, spec]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const rawValue = e.target.value;

    if (rawValue === '') {
      onChange(undefined);
      return;
    }

    if (spec.type === 'int') {
      const intValue = parseInt(rawValue, 10);
      onChange(isNaN(intValue) ? rawValue : intValue);
    } else {
      const floatValue = parseFloat(rawValue);
      onChange(isNaN(floatValue) ? rawValue : floatValue);
    }
  };

  const constraints = [
    spec.unit && `unit: ${spec.unit}`,
    typeof spec.min === 'number' && `min: ${spec.min}`,
    typeof spec.max === 'number' && `max: ${spec.max}`,
  ]
    .filter(Boolean)
    .join(', ');

  return (
    <div className="border border-gray-200 dark:border-slate-700 rounded-md px-3 py-2 bg-white dark:bg-slate-800 space-y-1">
      <label className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
        {name}
        <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-slate-700 text-[10px] font-medium text-gray-500 dark:text-gray-400">
          {spec.type}
        </span>
        {(spec.desc || constraints) && (
          <DescriptionTooltip description={spec.desc} constraints={constraints || undefined} />
        )}
      </label>
      <input
        type="number"
        value={displayValue}
        onChange={handleChange}
        step={spec.type === 'int' ? '1' : 'any'}
        placeholder={`Enter ${name}${spec.unit ? ` (${spec.unit})` : ''}`}
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

NumericParameterField.displayName = 'NumericParameterField';
