'use client';

import * as React from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Button } from '@/components/ui/Button';

/**
 * Input that preserves raw text while focused, preventing value-jumping from
 * parse/format round-trips (e.g., trailing commas being stripped on each keystroke).
 * Shows formatted `displayValue` when blurred; shows raw typed text when focused.
 */
export function RawInput({
  displayValue,
  onRawChange,
  onFocus: onFocusProp,
  onBlur: onBlurProp,
  ...props
}: {
  displayValue: string;
  onRawChange: (text: string) => void;
} & Omit<React.ComponentProps<typeof Input>, 'value' | 'onChange'>) {
  const [rawText, setRawText] = React.useState(displayValue);
  const [isFocused, setIsFocused] = React.useState(false);

  // Sync from parent when not focused
  const prevDisplayRef = React.useRef(displayValue);
  if (displayValue !== prevDisplayRef.current) {
    prevDisplayRef.current = displayValue;
    if (!isFocused) {
      setRawText(displayValue);
    }
  }

  return (
    <Input
      {...props}
      value={isFocused ? rawText : displayValue}
      onChange={(e) => {
        setRawText(e.target.value);
        onRawChange(e.target.value);
      }}
      onFocus={(e) => {
        setIsFocused(true);
        onFocusProp?.(e);
      }}
      onBlur={(e) => {
        setIsFocused(false);
        setRawText(displayValue);
        onBlurProp?.(e);
      }}
    />
  );
}

export const selectClass =
  'flex h-8 w-full items-center rounded-md border border-gray-300 bg-white px-2 text-xs ring-offset-white focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-white dark:ring-offset-slate-900 dark:focus:ring-yellow-500';

// ============================================================================
// Types
// ============================================================================

export interface DomainInput {
  type: 'ContinuousInput' | 'DiscreteInput' | 'CategoricalInput';
  key: string;
  bounds?: [number, number];
  stepsize?: number | null;
  values?: number[];
  categories?: string[];
  allowed?: boolean[];
}

export interface DomainOutput {
  type: 'ContinuousOutput' | 'CategoricalOutput';
  key: string;
  objective: {
    type: 'MinimizeObjective' | 'MaximizeObjective' | 'CloseToTargetObjective';
    w: number;
    target_value?: number;
    exponent?: number;
    bounds?: [number, number];
  };
  categories?: string[];
}

export interface DomainConstraint {
  type: 'LinearEqualityConstraint' | 'LinearInequalityConstraint';
  features: string[];
  coefficients: number[];
  rhs: number;
}

export interface DomainValue {
  inputs: DomainInput[];
  outputs: DomainOutput[];
  constraints: DomainConstraint[];
}

interface DomainEditorProps {
  value: DomainValue;
  onChange: (value: DomainValue) => void;
  readOnly?: boolean;
}

// ============================================================================
// Helpers
// ============================================================================

function makeDefaultInput(): DomainInput {
  return { type: 'ContinuousInput', key: '', bounds: [0, 1] };
}

function makeDefaultOutput(): DomainOutput {
  return {
    type: 'ContinuousOutput',
    key: '',
    objective: { type: 'MinimizeObjective', w: 1.0 },
  };
}

function makeDefaultConstraint(): DomainConstraint {
  return { type: 'LinearEqualityConstraint', features: [], coefficients: [], rhs: 0 };
}

function formatConstraint(c: DomainConstraint): string {
  const parts = c.features.map((f, i) => {
    const coeff = c.coefficients[i] ?? 0;
    return `${coeff} * ${f}`;
  });
  const op = c.type === 'LinearEqualityConstraint' ? '=' : '<=';
  return parts.length > 0 ? `${parts.join(' + ')} ${op} ${c.rhs}` : '(empty)';
}

// ============================================================================
// Sub-editors
// ============================================================================

function InputFeatureCard({
  input,
  index,
  onChange,
  onRemove,
  readOnly,
}: {
  input: DomainInput;
  index: number;
  onChange: (i: number, v: DomainInput) => void;
  onRemove: (i: number) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="relative border border-gray-200 dark:border-slate-700 rounded-md px-3 pt-2 pb-3 space-y-2 bg-white dark:bg-slate-800/50">
      {!readOnly && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onRemove(index)}
          className="absolute top-1 right-1 text-red-500 h-7 w-7 p-0"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      )}
      <div>
        <Label className="text-xs">Key</Label>
        <Input
          value={input.key}
          onChange={(e) => onChange(index, { ...input, key: e.target.value })}
          placeholder="task_name.parameter"
          disabled={readOnly}
          className="text-xs h-8"
        />
      </div>
      <div>
        <Label className="text-xs">Type</Label>
        <select
          value={input.type}
          onChange={(e) => {
            const type = e.target.value as DomainInput['type'];
            const base: DomainInput = { type, key: input.key };
            if (type === 'ContinuousInput') base.bounds = [0, 1];
            else if (type === 'DiscreteInput') base.values = [];
            else if (type === 'CategoricalInput') base.categories = [];
            onChange(index, base);
          }}
          disabled={readOnly}
          className={selectClass}
        >
          <option value="ContinuousInput">Continuous</option>
          <option value="DiscreteInput">Discrete</option>
          <option value="CategoricalInput">Categorical</option>
        </select>
      </div>

      {input.type === 'ContinuousInput' && (
        <div className="grid grid-cols-3 gap-2">
          <div>
            <Label className="text-xs">Lower bound</Label>
            <Input
              type="number"
              value={input.bounds?.[0] ?? 0}
              onChange={(e) =>
                onChange(index, { ...input, bounds: [parseFloat(e.target.value) || 0, input.bounds?.[1] ?? 1] })
              }
              disabled={readOnly}
              className="text-xs h-8"
            />
          </div>
          <div>
            <Label className="text-xs">Upper bound</Label>
            <Input
              type="number"
              value={input.bounds?.[1] ?? 1}
              onChange={(e) =>
                onChange(index, { ...input, bounds: [input.bounds?.[0] ?? 0, parseFloat(e.target.value) || 1] })
              }
              disabled={readOnly}
              className="text-xs h-8"
            />
          </div>
          <div>
            <Label className="text-xs">Step size</Label>
            <Input
              type="number"
              value={input.stepsize ?? ''}
              onChange={(e) =>
                onChange(index, { ...input, stepsize: e.target.value ? parseFloat(e.target.value) : null })
              }
              placeholder="Optional"
              disabled={readOnly}
              className="text-xs h-8"
            />
          </div>
        </div>
      )}

      {input.type === 'DiscreteInput' && (
        <div>
          <Label className="text-xs">Values (comma-separated)</Label>
          <RawInput
            displayValue={(input.values ?? []).join(', ')}
            onRawChange={(text) =>
              onChange(index, {
                ...input,
                values: text
                  .split(',')
                  .map((s) => parseFloat(s.trim()))
                  .filter((n) => !isNaN(n)),
              })
            }
            placeholder="1, 2, 3, 4"
            disabled={readOnly}
            className="text-xs h-8"
          />
        </div>
      )}

      {input.type === 'CategoricalInput' && (
        <div>
          <Label className="text-xs">Categories (comma-separated)</Label>
          <RawInput
            displayValue={(input.categories ?? []).join(', ')}
            onRawChange={(text) =>
              onChange(index, {
                ...input,
                categories: text
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
            placeholder="cat_a, cat_b, cat_c"
            disabled={readOnly}
            className="text-xs h-8"
          />
        </div>
      )}
    </div>
  );
}

function OutputFeatureCard({
  output,
  index,
  onChange,
  onRemove,
  readOnly,
}: {
  output: DomainOutput;
  index: number;
  onChange: (i: number, v: DomainOutput) => void;
  onRemove: (i: number) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="relative border border-gray-200 dark:border-slate-700 rounded-md px-3 pt-2 pb-3 space-y-2 bg-white dark:bg-slate-800/50">
      {!readOnly && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onRemove(index)}
          className="absolute top-1 right-1 text-red-500 h-7 w-7 p-0"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      )}
      <div>
        <Label className="text-xs">Key</Label>
        <Input
          value={output.key}
          onChange={(e) => onChange(index, { ...output, key: e.target.value })}
          placeholder="task_name.parameter"
          disabled={readOnly}
          className="text-xs h-8"
        />
      </div>
      <div>
        <Label className="text-xs">Type</Label>
        <select
          value={output.type}
          onChange={(e) => {
            const type = e.target.value as DomainOutput['type'];
            onChange(index, { ...output, type });
          }}
          disabled={readOnly}
          className={selectClass}
        >
          <option value="ContinuousOutput">Continuous</option>
          <option value="CategoricalOutput">Categorical</option>
        </select>
      </div>

      {output.type === 'CategoricalOutput' && (
        <div>
          <Label className="text-xs">Categories (comma-separated)</Label>
          <RawInput
            displayValue={(output.categories ?? []).join(', ')}
            onRawChange={(text) =>
              onChange(index, {
                ...output,
                categories: text
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
            placeholder="cat_a, cat_b"
            disabled={readOnly}
            className="text-xs h-8"
          />
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-xs">Objective</Label>
          <select
            value={output.objective.type}
            onChange={(e) => {
              const type = e.target.value as DomainOutput['objective']['type'];
              const obj = { ...output.objective, type };
              if (type === 'CloseToTargetObjective') {
                obj.target_value = obj.target_value ?? 0;
                obj.exponent = obj.exponent ?? 2;
              }
              onChange(index, { ...output, objective: obj });
            }}
            disabled={readOnly}
            className={selectClass}
          >
            <option value="MinimizeObjective">Minimize</option>
            <option value="MaximizeObjective">Maximize</option>
            <option value="CloseToTargetObjective">Close to Target</option>
          </select>
        </div>
        <div>
          <Label className="text-xs">Weight (w)</Label>
          <Input
            type="number"
            step="0.1"
            min="0"
            max="1"
            value={output.objective.w}
            onChange={(e) =>
              onChange(index, { ...output, objective: { ...output.objective, w: parseFloat(e.target.value) || 1 } })
            }
            disabled={readOnly}
            className="text-xs h-8"
          />
        </div>
      </div>

      {output.objective.type === 'CloseToTargetObjective' && (
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label className="text-xs">Target value</Label>
            <Input
              type="number"
              value={output.objective.target_value ?? 0}
              onChange={(e) =>
                onChange(index, {
                  ...output,
                  objective: { ...output.objective, target_value: parseFloat(e.target.value) || 0 },
                })
              }
              disabled={readOnly}
              className="text-xs h-8"
            />
          </div>
          <div>
            <Label className="text-xs">Exponent</Label>
            <Input
              type="number"
              value={output.objective.exponent ?? 2}
              onChange={(e) =>
                onChange(index, {
                  ...output,
                  objective: { ...output.objective, exponent: parseFloat(e.target.value) || 2 },
                })
              }
              disabled={readOnly}
              className="text-xs h-8"
            />
          </div>
        </div>
      )}
    </div>
  );
}

function ConstraintCard({
  constraint,
  index,
  inputKeys,
  onChange,
  onRemove,
  readOnly,
}: {
  constraint: DomainConstraint;
  index: number;
  inputKeys: string[];
  onChange: (i: number, v: DomainConstraint) => void;
  onRemove: (i: number) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="relative border border-gray-200 dark:border-slate-700 rounded-md px-3 pt-2 pb-3 space-y-2 bg-white dark:bg-slate-800/50">
      {!readOnly && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onRemove(index)}
          className="absolute top-1 right-1 text-red-500 h-7 w-7 p-0"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      )}
      <div>
        <Label className="text-xs">Type</Label>
        <select
          value={constraint.type}
          onChange={(e) => onChange(index, { ...constraint, type: e.target.value as DomainConstraint['type'] })}
          disabled={readOnly}
          className={selectClass}
        >
          <option value="LinearEqualityConstraint">Linear Equality (=)</option>
          <option value="LinearInequalityConstraint">{'Linear Inequality (<=)'}</option>
        </select>
      </div>

      <div>
        <Label className="text-xs">Features (comma-separated keys)</Label>
        <RawInput
          displayValue={constraint.features.join(', ')}
          onRawChange={(text) => {
            const features = text
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean);
            const coefficients = features.map((_, i) => constraint.coefficients[i] ?? 1);
            onChange(index, { ...constraint, features, coefficients });
          }}
          placeholder={inputKeys.length > 0 ? inputKeys.slice(0, 2).join(', ') : 'feature_1, feature_2'}
          disabled={readOnly}
          className="text-xs h-8"
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-xs">Coefficients (comma-separated)</Label>
          <RawInput
            displayValue={constraint.coefficients.join(', ')}
            onRawChange={(text) =>
              onChange(index, {
                ...constraint,
                coefficients: text
                  .split(',')
                  .map((s) => parseFloat(s.trim()))
                  .filter((n) => !isNaN(n)),
              })
            }
            placeholder="1.0, 2.0"
            disabled={readOnly}
            className="text-xs h-8"
          />
        </div>
        <div>
          <Label className="text-xs">RHS</Label>
          <Input
            type="number"
            value={constraint.rhs}
            onChange={(e) => onChange(index, { ...constraint, rhs: parseFloat(e.target.value) || 0 })}
            disabled={readOnly}
            className="text-xs h-8"
          />
        </div>
      </div>

      <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">{formatConstraint(constraint)}</div>
    </div>
  );
}

// ============================================================================
// Domain parsing helpers (raw API dicts → typed domain values)
// ============================================================================

export function parseDomainInputs(raw: Record<string, unknown>[]): DomainValue['inputs'] {
  return raw.map((r) => ({
    type: ((r.type as string) ?? 'ContinuousInput') as DomainInput['type'],
    key: (r.key as string) ?? '',
    bounds: r.bounds as [number, number] | undefined,
    stepsize: r.stepsize as number | null | undefined,
    values: r.values as number[] | undefined,
    categories: r.categories as string[] | undefined,
    allowed: r.allowed as boolean[] | undefined,
  }));
}

export function parseDomainOutputs(raw: Record<string, unknown>[]): DomainValue['outputs'] {
  return raw.map((r) => ({
    type: ((r.type as string) ?? 'ContinuousOutput') as DomainOutput['type'],
    key: (r.key as string) ?? '',
    objective: (r.objective as DomainValue['outputs'][number]['objective']) ?? {
      type: 'MinimizeObjective' as const,
      w: 1.0,
    },
    categories: r.categories as string[] | undefined,
  }));
}

export function parseDomainConstraints(raw: Record<string, unknown>[]): DomainValue['constraints'] {
  return raw.map((r) => ({
    type: ((r.type as string) ?? 'LinearEqualityConstraint') as DomainConstraint['type'],
    features: (r.features as string[]) ?? [],
    coefficients: (r.coefficients as number[]) ?? [],
    rhs: (r.rhs as number) ?? 0,
  }));
}

// ============================================================================
// Main Component
// ============================================================================

export function DomainEditor({ value, onChange, readOnly }: DomainEditorProps) {
  const inputKeys = value.inputs.map((i) => i.key).filter(Boolean);

  const updateInput = (index: number, input: DomainInput) => {
    const inputs = [...value.inputs];
    inputs[index] = input;
    onChange({ ...value, inputs });
  };

  const updateOutput = (index: number, output: DomainOutput) => {
    const outputs = [...value.outputs];
    outputs[index] = output;
    onChange({ ...value, outputs });
  };

  const updateConstraint = (index: number, constraint: DomainConstraint) => {
    const constraints = [...value.constraints];
    constraints[index] = constraint;
    onChange({ ...value, constraints });
  };

  return (
    <div className="space-y-4">
      {/* Inputs */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-sm font-medium">Inputs</Label>
          {!readOnly && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onChange({ ...value, inputs: [...value.inputs, makeDefaultInput()] })}
              className="h-7 text-xs gap-1"
            >
              <Plus className="h-3 w-3" /> Add Input
            </Button>
          )}
        </div>
        {value.inputs.length === 0 && (
          <p className="text-xs text-gray-400 dark:text-gray-500 italic">No inputs defined</p>
        )}
        {value.inputs.map((input, i) => (
          <InputFeatureCard
            key={`input-${i}`}
            input={input}
            index={i}
            onChange={updateInput}
            onRemove={(idx) => onChange({ ...value, inputs: value.inputs.filter((_, j) => j !== idx) })}
            readOnly={readOnly}
          />
        ))}
      </div>

      {/* Outputs */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-sm font-medium">Outputs</Label>
          {!readOnly && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onChange({ ...value, outputs: [...value.outputs, makeDefaultOutput()] })}
              className="h-7 text-xs gap-1"
            >
              <Plus className="h-3 w-3" /> Add Output
            </Button>
          )}
        </div>
        {value.outputs.length === 0 && (
          <p className="text-xs text-gray-400 dark:text-gray-500 italic">No outputs defined</p>
        )}
        {value.outputs.map((output, i) => (
          <OutputFeatureCard
            key={`output-${i}`}
            output={output}
            index={i}
            onChange={updateOutput}
            onRemove={(idx) => onChange({ ...value, outputs: value.outputs.filter((_, j) => j !== idx) })}
            readOnly={readOnly}
          />
        ))}
      </div>

      {/* Constraints */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-sm font-medium">Constraints</Label>
          {!readOnly && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onChange({ ...value, constraints: [...value.constraints, makeDefaultConstraint()] })}
              className="h-7 text-xs gap-1"
            >
              <Plus className="h-3 w-3" /> Add Constraint
            </Button>
          )}
        </div>
        {value.constraints.length === 0 && (
          <p className="text-xs text-gray-400 dark:text-gray-500 italic">No constraints defined</p>
        )}
        {value.constraints.map((constraint, i) => (
          <ConstraintCard
            key={`constraint-${i}`}
            constraint={constraint}
            index={i}
            inputKeys={inputKeys}
            onChange={updateConstraint}
            onRemove={(idx) => onChange({ ...value, constraints: value.constraints.filter((_, j) => j !== idx) })}
            readOnly={readOnly}
          />
        ))}
      </div>
    </div>
  );
}
