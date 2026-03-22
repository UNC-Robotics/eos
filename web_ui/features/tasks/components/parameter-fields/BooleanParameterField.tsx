import { memo } from 'react';
import { ParameterSpec } from '@/lib/types/experiment';

interface BooleanParameterFieldProps {
  name: string;
  spec: ParameterSpec;
  value: unknown;
  onChange: (value: unknown) => void;
}

export const BooleanParameterField = memo(({ name, spec, value, onChange }: BooleanParameterFieldProps) => {
  const boolValue = Boolean(value);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.checked);
  };

  return (
    <div className="border border-gray-200 dark:border-slate-700 rounded-md p-3 bg-white dark:bg-slate-800">
      <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
        {name}
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">({spec.type})</span>
      </label>

      {spec.desc && <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{spec.desc}</p>}

      <div className="flex items-center">
        <input
          type="checkbox"
          checked={boolValue}
          onChange={handleChange}
          className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 dark:focus:ring-yellow-500"
        />
        <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">{boolValue ? 'True' : 'False'}</span>
      </div>
    </div>
  );
});

BooleanParameterField.displayName = 'BooleanParameterField';
