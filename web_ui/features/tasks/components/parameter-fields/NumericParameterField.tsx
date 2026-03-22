import { memo, useState, useEffect } from 'react';
import { ParameterSpec } from '@/lib/types/experiment';
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

  const getMinMaxHint = () => {
    const hints: string[] = [];

    if (typeof spec.min === 'number') {
      hints.push(`min: ${spec.min}`);
    }

    if (typeof spec.max === 'number') {
      hints.push(`max: ${spec.max}`);
    }

    return hints.length > 0 ? ` (${hints.join(', ')})` : '';
  };

  return (
    <div className="border border-gray-200 dark:border-slate-700 rounded-md p-3 bg-white dark:bg-slate-800">
      <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
        {name}
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">
          ({spec.type}
          {spec.unit && `, ${spec.unit}`}
          {getMinMaxHint()})
        </span>
      </label>

      {spec.desc && <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{spec.desc}</p>}

      <input
        type="number"
        value={displayValue}
        onChange={handleChange}
        step={spec.type === 'int' ? '1' : 'any'}
        placeholder={`Enter ${name}${spec.unit ? ` (${spec.unit})` : ''}`}
        className={`w-full px-2.5 py-1.5 text-sm border rounded-md focus:outline-none focus:ring-2 ${
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
