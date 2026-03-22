import { memo, useState, useEffect } from 'react';
import { ParameterSpec } from '@/lib/types/experiment';
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
    <div className="border border-gray-200 dark:border-slate-700 rounded-md p-3 bg-white dark:bg-slate-800">
      <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
        {name}
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">({spec.type})</span>
      </label>

      {spec.desc && <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{spec.desc}</p>}

      <input
        type="text"
        value={displayValue}
        onChange={handleChange}
        placeholder={`Enter ${name}`}
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

StringParameterField.displayName = 'StringParameterField';
