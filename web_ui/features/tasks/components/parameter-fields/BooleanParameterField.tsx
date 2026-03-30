import { memo } from 'react';
import { ParameterSpec } from '@/lib/types/protocol';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';

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
    <div className="border border-gray-200 dark:border-slate-700 rounded-md px-3 py-2 bg-white dark:bg-slate-800 space-y-1">
      <label className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300">
        {name}
        <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-slate-700 text-[10px] font-medium text-gray-500 dark:text-gray-400">
          {spec.type}
        </span>
        {spec.desc && <DescriptionTooltip description={spec.desc} />}
      </label>
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
