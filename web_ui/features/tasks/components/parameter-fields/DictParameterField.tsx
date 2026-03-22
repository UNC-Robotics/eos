import { memo, useState, useEffect } from 'react';
import { ParameterSpec } from '@/lib/types/experiment';
import { validateDict } from '@/lib/validation/parameter-validation';

interface DictParameterFieldProps {
  name: string;
  spec: ParameterSpec;
  value: unknown;
  onChange: (value: unknown) => void;
}

export const DictParameterField = memo(({ name, spec, value, onChange }: DictParameterFieldProps) => {
  const [error, setError] = useState<string | undefined>();
  const [textValue, setTextValue] = useState<string>('');

  // Initialize text value from the actual value
  useEffect(() => {
    if (value !== undefined && value !== null) {
      if (typeof value === 'string') {
        setTextValue(value);
      } else {
        setTextValue(JSON.stringify(value, null, 2));
      }
    } else {
      setTextValue('');
    }
  }, [value]);

  // Validate on value change
  useEffect(() => {
    if (value !== undefined && value !== null && value !== '') {
      const validation = validateDict(value, spec);
      setError(validation.error);
    } else {
      setError(undefined);
    }
  }, [value, spec]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const rawValue = e.target.value;
    setTextValue(rawValue);

    if (rawValue === '') {
      onChange(undefined);
      return;
    }

    // Try to parse JSON
    try {
      const parsed = JSON.parse(rawValue);
      onChange(parsed);
    } catch {
      // Keep the string value if it's not valid JSON yet
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

      <textarea
        value={textValue}
        onChange={handleChange}
        rows={4}
        placeholder='{"key": "value"}'
        className={`w-full px-2.5 py-1.5 text-sm border rounded-md focus:outline-none focus:ring-2 font-mono ${
          error
            ? 'border-red-500 focus:ring-red-500'
            : 'border-gray-300 dark:border-slate-600 focus:ring-blue-500 dark:focus:ring-yellow-500'
        } bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500`}
      />

      {error && <p className="mt-1 text-xs text-red-500 dark:text-red-400">{error}</p>}

      <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
        Enter a JSON object, e.g., {`{"key": "value", "number": 42}`}
      </p>
    </div>
  );
});

DictParameterField.displayName = 'DictParameterField';
