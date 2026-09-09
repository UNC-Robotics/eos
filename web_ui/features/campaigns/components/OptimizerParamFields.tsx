'use client';

import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';
import { selectClass } from './DomainEditor';
import { JsonTextarea } from './OptimizerPanel';
import type { OptimizerParamSpec } from '@/lib/types/api';

interface OptimizerParamFieldsProps {
  schema: OptimizerParamSpec[];
  /** Current value per key. Falls back to the spec's default when absent. */
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  disabled?: boolean;
  /** Render only parameters marked runtime-tunable. */
  runtimeOnly?: boolean;
}

/** Render one control per parameter descriptor declared by an optimizer's eos_param_schema(). */
export function OptimizerParamFields({ schema, values, onChange, disabled, runtimeOnly }: OptimizerParamFieldsProps) {
  const fields = runtimeOnly ? schema.filter((f) => f.runtime) : schema;
  if (fields.length === 0) return null;

  return (
    <div className="space-y-3">
      {fields.map((field) => {
        const value = field.key in values ? values[field.key] : field.default;
        return (
          <div key={field.key} className="space-y-1">
            <Label className="text-xs">
              {field.label ?? field.key}
              <DescriptionTooltip description={field.description} />
            </Label>
            <ParamControl field={field} value={value} onChange={(v) => onChange(field.key, v)} disabled={disabled} />
          </div>
        );
      })}
    </div>
  );
}

function ParamControl({
  field,
  value,
  onChange,
  disabled,
}: {
  field: OptimizerParamSpec;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
}) {
  switch (field.type) {
    case 'number':
      return (
        <Input
          type="number"
          min={field.min}
          max={field.max}
          step={field.step ?? 'any'}
          value={value == null ? '' : String(value)}
          onChange={(e) => onChange(e.target.value === '' ? null : parseFloat(e.target.value))}
          disabled={disabled}
          className="text-xs h-8"
        />
      );
    case 'select':
      return (
        <select
          value={value == null ? '' : String(value)}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={selectClass}
        >
          {(field.options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      );
    case 'checkbox':
      return (
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          disabled={disabled}
          className="h-4 w-4 rounded border-gray-300 dark:border-slate-600 dark:bg-slate-800 text-blue-600 focus:ring-blue-600"
        />
      );
    case 'json':
      return (
        <JsonTextarea
          value={value}
          onChange={onChange}
          disabled={disabled}
          placeholder="{}"
          className="text-xs min-h-[48px] font-mono"
        />
      );
    default:
      return (
        <Input
          type="text"
          value={value == null ? '' : String(value)}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className="text-xs h-8"
        />
      );
  }
}
