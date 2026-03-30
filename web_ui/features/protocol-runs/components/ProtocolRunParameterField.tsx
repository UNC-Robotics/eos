'use client';

import { useState, useCallback, useEffect, useMemo } from 'react';
import { RotateCcw } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';
import { ParameterSpec, ParameterValue } from '@/lib/types/protocol';
import { isReferenceValue, parseNumberInput, formatInputValue } from '@/lib/utils/protocolHelpers';
import { MODE_BUTTON_BASE, MODE_BUTTON_ACTIVE, MODE_BUTTON_INACTIVE, INPUT_BASE } from '../styles';

interface ProtocolRunParameterFieldProps {
  paramName: string;
  paramSpec: ParameterSpec;
  value: ParameterValue | undefined; // Override value (undefined = use default)
  specDefault: unknown; // Default from protocol spec (can be 'eos_dynamic', reference, or static)
  onChange: (value: ParameterValue) => void;
  onClear: () => void; // Remove override, revert to default
}

// Get effective value and mode based on override and spec default
function getEffectiveValue(
  override: ParameterValue | undefined,
  specDefault: unknown
): { value: unknown; mode: 'static' | 'reference'; isOverride: boolean } {
  // If there's an override, use it
  if (override !== undefined) {
    return { value: override.value, mode: override.mode, isOverride: true };
  }

  // No override - derive from spec default
  // eos_dynamic or undefined: show empty
  if (specDefault === 'eos_dynamic' || specDefault === undefined) {
    return { value: undefined, mode: 'static', isOverride: false };
  }

  if (isReferenceValue(specDefault)) {
    // Reference default
    return { value: specDefault, mode: 'reference', isOverride: false };
  }

  // Static default
  return { value: specDefault, mode: 'static', isOverride: false };
}

export function ProtocolRunParameterField({
  paramName,
  paramSpec,
  value: override,
  specDefault,
  onChange,
  onClear,
}: ProtocolRunParameterFieldProps) {
  const effective = useMemo(() => getEffectiveValue(override, specDefault), [override, specDefault]);

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

  const hasOverride = effective.isOverride;

  return (
    <div
      className={`border rounded-md px-3 py-2 space-y-1.5 ${
        hasOverride
          ? 'border-blue-300 dark:border-blue-600 bg-white dark:bg-slate-800'
          : 'border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <label className="shrink-0 flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap">
          {paramName}
          <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-slate-700 text-[10px] font-medium text-gray-500 dark:text-gray-400">
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

      {selectedMode === 'static' && renderStaticField(paramSpec, effective.value, handleValueChange)}

      {selectedMode === 'reference' && (
        <Input
          value={typeof effective.value === 'string' ? effective.value : ''}
          onChange={(e) => handleValueChange(e.target.value)}
          placeholder="task_name.output_param"
          className="font-mono text-sm"
        />
      )}
    </div>
  );
}

function renderStaticField(spec: ParameterSpec, value: unknown, onChange: (value: unknown) => void): React.ReactNode {
  const normalizedType = spec.type.toLowerCase();

  switch (normalizedType) {
    case 'int':
    case 'integer':
    case 'float':
    case 'number':
    case 'double':
      const isInt = spec.type === 'int';
      return (
        <Input
          type="number"
          value={formatInputValue(value)}
          onChange={(e) => onChange(parseNumberInput(e.target.value, isInt ? 'int' : 'float'))}
          step={isInt ? '1' : 'any'}
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
          placeholder="Enter value"
        />
      );
  }
}
