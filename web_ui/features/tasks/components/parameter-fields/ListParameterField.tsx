import { memo, useState, useEffect } from 'react';
import { ParameterSpec } from '@/lib/types/protocol';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';
import { validateList } from '@/lib/validation/parameter-validation';

interface ListParameterFieldProps {
  name: string;
  spec: ParameterSpec;
  value: unknown;
  onChange: (value: unknown) => void;
}

export const ListParameterField = memo(({ name, spec, value, onChange }: ListParameterFieldProps) => {
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
      const validation = validateList(value, spec);
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

  const constraints = [
    spec.element_type && `element type: ${spec.element_type}`,
    spec.length !== undefined && `length: ${spec.length}`,
  ]
    .filter(Boolean)
    .join(', ');

  const getPlaceholder = () => {
    if (spec.element_type) {
      const elementType = spec.element_type.toLowerCase();
      if (elementType === 'int' || elementType === 'integer' || elementType === 'float' || elementType === 'number') {
        return '[1, 2, 3]';
      } else if (elementType === 'str' || elementType === 'string') {
        return '["a", "b", "c"]';
      } else if (elementType === 'bool' || elementType === 'boolean') {
        return '[true, false, true]';
      }
    }
    return '[...]';
  };

  return (
    <div className="border border-gray-200 dark:border-slate-700 rounded-md px-3 py-2 bg-white dark:bg-slate-800">
      <label className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
        {name}
        <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-slate-700 text-[10px] font-medium text-gray-500 dark:text-gray-400">
          {spec.type}
        </span>
        {(spec.desc || constraints) && (
          <DescriptionTooltip description={spec.desc} constraints={constraints || undefined} />
        )}
      </label>

      <textarea
        value={textValue}
        onChange={handleChange}
        rows={2}
        placeholder={getPlaceholder()}
        className={`w-full px-2.5 py-1 text-sm border rounded-md focus:outline-none focus:ring-2 font-mono ${
          error
            ? 'border-red-500 focus:ring-red-500'
            : 'border-gray-300 dark:border-slate-600 focus:ring-blue-500 dark:focus:ring-yellow-500'
        } bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500`}
      />

      {error && <p className="mt-1 text-xs text-red-500 dark:text-red-400">{error}</p>}
    </div>
  );
});

ListParameterField.displayName = 'ListParameterField';
