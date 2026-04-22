import { memo, useState, useEffect } from 'react';
import { ParameterSpec } from '@/lib/types/protocol';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';
import { restoreDefaultIfEmpty } from '@/lib/utils/protocolHelpers';
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
    const raw = e.target.value;
    onChange(raw === '' ? undefined : raw);
  };

  const constraints = [
    spec.unit && `unit: ${spec.unit}`,
    typeof spec.min === 'number' && `min: ${spec.min}`,
    typeof spec.max === 'number' && `max: ${spec.max}`,
  ]
    .filter(Boolean)
    .join(', ');

  return (
    <div className="space-y-1">
      <label className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
        {name}
        <span className="px-1.5 py-0.5 rounded bg-gray-200 dark:bg-slate-600 text-[10px] font-medium text-gray-700 dark:text-gray-200">
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
        onBlur={() => restoreDefaultIfEmpty(value, spec, onChange)}
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
