'use client';

import { useState, useCallback, useEffect, useMemo } from 'react';
import { RotateCcw } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';
import { ParameterSpec, ParameterValue } from '@/lib/types/protocol';
import { coerceForSpec, deepEqual, isReferenceValue, formatInputValue } from '@/lib/utils/protocolHelpers';
import { MODE_BUTTON_BASE, MODE_BUTTON_ACTIVE, MODE_BUTTON_INACTIVE, INPUT_BASE } from '../styles';

interface ProtocolRunParameterFieldProps {
  paramName: string;
  paramSpec: ParameterSpec;
  value: ParameterValue | undefined;
  specDefault: unknown;
  taskSpecDefault: unknown;
  onChange: (value: ParameterValue) => void;
  onClear: () => void;
}

// Fallback chain: override > protocol.yml default > task.yml default > empty.
// eos_dynamic requires an explicit submission value — never back-fill with the task.yml default.
function getEffectiveValue(
  override: ParameterValue | undefined,
  specDefault: unknown,
  taskSpecDefault: unknown
): { value: unknown; mode: 'static' | 'reference'; isOverride: boolean; defaultValue: unknown } {
  const isDynamic = specDefault === 'eos_dynamic';
  let effectiveDefault: unknown;
  if (isDynamic) {
    effectiveDefault = undefined;
  } else if (specDefault === undefined) {
    effectiveDefault = taskSpecDefault;
  } else {
    effectiveDefault = specDefault;
  }

  if (override !== undefined) {
    return { value: override.value, mode: override.mode, isOverride: true, defaultValue: effectiveDefault };
  }

  if (effectiveDefault === undefined) {
    return { value: undefined, mode: 'static', isOverride: false, defaultValue: undefined };
  }

  if (isReferenceValue(effectiveDefault)) {
    return { value: effectiveDefault, mode: 'reference', isOverride: false, defaultValue: effectiveDefault };
  }

  return { value: effectiveDefault, mode: 'static', isOverride: false, defaultValue: effectiveDefault };
}

export function ProtocolRunParameterField({
  paramName,
  paramSpec,
  value: override,
  specDefault,
  taskSpecDefault,
  onChange,
  onClear,
}: ProtocolRunParameterFieldProps) {
  const effective = useMemo(
    () => getEffectiveValue(override, specDefault, taskSpecDefault),
    [override, specDefault, taskSpecDefault]
  );

  const [selectedMode, setSelectedMode] = useState<'static' | 'reference'>(effective.mode);

  useEffect(() => {
    setSelectedMode(effective.mode);
  }, [effective.mode]);

  const handleModeChange = useCallback(
    (newMode: 'static' | 'reference') => {
      setSelectedMode(newMode);
      onChange({ mode: newMode, value: newMode === 'reference' ? '' : undefined });
    },
    [onChange]
  );

  const handleValueChange = useCallback(
    (newValue: unknown) => {
      onChange({ mode: selectedMode, value: newValue });
    },
    [selectedMode, onChange]
  );

  // Drop override on blur if it's empty or matches the effective default
  const handleBlur = useCallback(() => {
    if (override === undefined) return;
    const v = override.value;
    if (v === undefined || v === null || v === '' || deepEqual(coerceForSpec(v, paramSpec), effective.defaultValue)) {
      onClear();
    }
  }, [override, effective.defaultValue, onClear, paramSpec]);

  const hasOverride = effective.isOverride;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <label className="shrink-0 flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap">
          {paramName}
          <span className="px-1.5 py-0.5 rounded bg-gray-200 dark:bg-slate-600 text-[10px] font-medium text-gray-700 dark:text-gray-200">
            {paramSpec.type}
          </span>
          {hasOverride && <span className="text-xs text-blue-600 dark:text-blue-400">(override)</span>}
          {(() => {
            const constraints = [
              paramSpec.unit && `unit: ${paramSpec.unit}`,
              typeof paramSpec.min === 'number' && `min: ${paramSpec.min}`,
              typeof paramSpec.max === 'number' && `max: ${paramSpec.max}`,
            ]
              .filter(Boolean)
              .join(', ');
            return paramSpec.desc || constraints ? (
              <DescriptionTooltip description={paramSpec.desc} constraints={constraints || undefined} />
            ) : null;
          })()}
        </label>
        <div className="flex items-center gap-1.5">
          {hasOverride && (
            <button
              type="button"
              onClick={onClear}
              className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              title="Reset to default"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          )}
          {(['static', 'reference'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => handleModeChange(mode)}
              className={`${MODE_BUTTON_BASE} ${selectedMode === mode ? MODE_BUTTON_ACTIVE : MODE_BUTTON_INACTIVE}`}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {selectedMode === 'static' && renderStaticField(paramSpec, effective.value, handleValueChange, handleBlur)}

      {selectedMode === 'reference' && (
        <Input
          value={typeof effective.value === 'string' ? effective.value : ''}
          onChange={(e) => handleValueChange(e.target.value)}
          onBlur={handleBlur}
          placeholder="task_name.output_param"
          className="font-mono text-sm"
        />
      )}
    </div>
  );
}

function renderStaticField(
  spec: ParameterSpec,
  value: unknown,
  onChange: (value: unknown) => void,
  onBlur: () => void
): React.ReactNode {
  const normalizedType = spec.type.toLowerCase();

  switch (normalizedType) {
    case 'int':
    case 'integer':
    case 'float':
    case 'number':
    case 'double':
      return (
        <Input
          type="number"
          value={formatInputValue(value)}
          onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
          onBlur={onBlur}
          step={spec.type === 'int' ? '1' : 'any'}
          placeholder={`Enter ${spec.type}`}
        />
      );

    case 'str':
    case 'string':
      return (
        <Input
          type="text"
          value={formatInputValue(value)}
          onChange={(e) => onChange(e.target.value || undefined)}
          onBlur={onBlur}
          placeholder={`Enter ${spec.type}`}
        />
      );

    case 'bool':
    case 'boolean':
      return (
        <div className="flex items-center">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
            onBlur={onBlur}
            className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
          />
          <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">{Boolean(value) ? 'True' : 'False'}</span>
        </div>
      );

    case 'choice':
      return (
        <select
          value={formatInputValue(value)}
          onChange={(e) => onChange(e.target.value || undefined)}
          onBlur={onBlur}
          className={INPUT_BASE}
        >
          <option value="">Select value</option>
          {(spec.choices || []).map((choice) => (
            <option key={choice} value={choice}>
              {choice}
            </option>
          ))}
        </select>
      );

    case 'list':
    case 'dict':
    case 'dictionary':
      const textValue =
        value !== undefined && value !== null
          ? typeof value === 'string'
            ? value
            : JSON.stringify(value, null, 2)
          : '';
      return (
        <textarea
          value={textValue}
          onChange={(e) => {
            const rawValue = e.target.value;
            if (rawValue === '') {
              onChange(undefined);
              return;
            }
            try {
              onChange(JSON.parse(rawValue));
            } catch {
              onChange(rawValue);
            }
          }}
          onBlur={onBlur}
          rows={3}
          placeholder={normalizedType === 'list' ? '[...]' : '{"key": "value"}'}
          className={`${INPUT_BASE} font-mono`}
        />
      );

    default:
      return (
        <Input
          type="text"
          value={formatInputValue(value)}
          onChange={(e) => onChange(e.target.value || undefined)}
          onBlur={onBlur}
          placeholder="Enter value"
        />
      );
  }
}
