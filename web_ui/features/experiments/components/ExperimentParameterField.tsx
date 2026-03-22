'use client';

import { useState, useCallback, useEffect, useMemo } from 'react';
import { RotateCcw } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { ParameterSpec, ParameterValue } from '@/lib/types/experiment';
import { isReferenceValue, parseNumberInput, formatInputValue } from '@/lib/utils/experimentHelpers';
import { MODE_BUTTON_BASE, MODE_BUTTON_ACTIVE, MODE_BUTTON_INACTIVE, INPUT_BASE } from '../styles';

interface ExperimentParameterFieldProps {
  paramName: string;
  paramSpec: ParameterSpec;
  value: ParameterValue | undefined; // Override value (undefined = use default)
  specDefault: unknown; // Default from experiment spec (can be 'eos_dynamic', reference, or static)
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

export function ExperimentParameterField({
  paramName,
  paramSpec,
  value: override,
  specDefault,
  onChange,
  onClear,
}: ExperimentParameterFieldProps) {
  const effective = useMemo(() => getEffectiveValue(override, specDefault), [override, specDefault]);

  const [selectedMode, setSelectedMode] = useState<'static' | 'reference'>(effective.mode);

  // Keep mode in sync with effective value changes
  useEffect(() => {
    setSelectedMode(effective.mode);
  }, [effective.mode]);

  const handleModeChange = useCallback(
    (newMode: 'static' | 'reference') => {
      setSelectedMode(newMode);
      // When switching modes, create an override with reset value
      onChange({
        mode: newMode,
        value: newMode === 'reference' ? '' : undefined,
      });
    },
    [onChange]
  );

  const handleValueChange = useCallback(
    (newValue: unknown) => {
      onChange({
        mode: selectedMode,
        value: newValue,
      });
    },
    [selectedMode, onChange]
  );

  const hasOverride = effective.isOverride;

  return (
    <div
      className={`border rounded-md p-3 space-y-2.5 ${
        hasOverride
          ? 'border-blue-300 dark:border-blue-600 bg-blue-50 dark:bg-blue-900/20'
          : 'border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800'
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
            {paramName}
            <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">
              ({paramSpec.type}
              {paramSpec.unit && `, ${paramSpec.unit}`})
            </span>
            {hasOverride && <span className="ml-2 text-xs text-blue-600 dark:text-blue-400">(override)</span>}
          </label>
          {paramSpec.desc && <p className="text-xs text-gray-500 dark:text-gray-400">{paramSpec.desc}</p>}
        </div>
        {hasOverride && (
          <button
            type="button"
            onClick={onClear}
            className="ml-2 p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            title="Reset to default"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="flex gap-2">
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

      {/* Value Input */}
      {selectedMode === 'static' && <div>{renderStaticField(paramSpec, effective.value, handleValueChange)}</div>}

      {selectedMode === 'reference' && (
        <div>
          <Input
            value={typeof effective.value === 'string' ? effective.value : ''}
            onChange={(e) => handleValueChange(e.target.value)}
            placeholder="task_name.output_param"
            className="font-mono text-sm"
          />
        </div>
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
