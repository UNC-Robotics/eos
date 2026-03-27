'use client';

import * as React from 'react';
import { ChevronDown, ChevronRight, SlidersHorizontal } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Textarea } from '@/components/ui/Textarea';
import { Button } from '@/components/ui/Button';
import {
  DomainEditor,
  RawInput,
  selectClass,
  parseDomainInputs,
  parseDomainOutputs,
  parseDomainConstraints,
  type DomainValue,
} from './DomainEditor';
import { updateOptimizerParams } from '../api/optimizer';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';
import type { OptimizerDefaults, OptimizerInfo } from '@/lib/types/api';
import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';

// ============================================================================
// AI Model Options
// ============================================================================

const AI_MODEL_OPTIONS: ComboboxOption[] = [
  // Claude Agent SDK (recommended — uses local CLI credentials)
  { value: 'claude-agent-sdk:opus', label: 'Claude Opus', group: 'Claude Agent SDK' },
  { value: 'claude-agent-sdk:sonnet', label: 'Claude Sonnet', group: 'Claude Agent SDK' },
  { value: 'claude-agent-sdk:haiku', label: 'Claude Haiku', group: 'Claude Agent SDK' },
  // Anthropic (direct API)
  { value: 'anthropic:claude-opus-4-6', label: 'Claude Opus 4.6', group: 'Anthropic' },
  { value: 'anthropic:claude-sonnet-4-6', label: 'Claude Sonnet 4.6', group: 'Anthropic' },
  // OpenAI
  { value: 'openai:gpt-5.4', label: 'GPT-5.4', group: 'OpenAI' },
  { value: 'openai:gpt-5.4-mini', label: 'GPT-5.4 Mini', group: 'OpenAI' },
  { value: 'openai:gpt-5.4-nano', label: 'GPT-5.4 Nano', group: 'OpenAI' },
  // Google
  { value: 'google-gla:gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro', group: 'Google' },
  { value: 'google-gla:gemini-3-flash-preview', label: 'Gemini 3 Flash', group: 'Google' },
  { value: 'google-gla:gemini-3.1-flash-lite-preview', label: 'Gemini 3.1 Flash Lite', group: 'Google' },
];

// ============================================================================
// Types
// ============================================================================

interface RuntimeModeProps {
  mode: 'runtime';
  campaignName: string;
  optimizerInfo: OptimizerInfo;
  isRunning: boolean;
  onRefresh?: () => void;
}

interface SubmissionModeProps {
  mode: 'submission';
  defaults: OptimizerDefaults;
  isResume: boolean;
  overrides: Record<string, unknown>;
  onChange: (overrides: Record<string, unknown>) => void;
  /** For resume mode, the persisted domain from campaign.meta.beacon.optimizer_config */
  persistedDomain?: DomainValue | null;
}

interface EditorModeProps {
  mode: 'editor';
  defaults: OptimizerDefaults;
  onSave: (values: Record<string, unknown>, domain: DomainValue) => void | Promise<void>;
}

type BeaconOptimizerPanelProps = RuntimeModeProps | SubmissionModeProps | EditorModeProps;

/** Display a JSON value as a pretty-printed string, or empty string for null/undefined. */
function jsonDisplay(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

/** Parse a JSON string, returning null for empty/invalid input. Keeps raw string if not valid JSON. */
function jsonParse(text: string): unknown {
  const trimmed = text.trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return trimmed; // Keep raw string — user may still be typing
  }
}

/**
 * Textarea for editing JSON values. Uses local state during editing to avoid
 * cursor jumps from round-tripping through jsonDisplay/jsonParse on every keystroke.
 * Syncs to the parent on blur.
 */
function JsonTextarea({
  value,
  onChange,
  ...props
}: { value: unknown; onChange: (parsed: unknown) => void } & Omit<
  React.ComponentProps<typeof Textarea>,
  'value' | 'onChange'
>) {
  const [localText, setLocalText] = React.useState(() => jsonDisplay(value));
  const focusedRef = React.useRef(false);

  // Sync from parent when not focused (e.g. external reset)
  React.useEffect(() => {
    if (!focusedRef.current) setLocalText(jsonDisplay(value));
  }, [value]);

  return (
    <Textarea
      {...props}
      value={localText}
      onChange={(e) => setLocalText(e.target.value)}
      onFocus={() => {
        focusedRef.current = true;
      }}
      onBlur={() => {
        onChange(jsonParse(localText));
        focusedRef.current = false;
      }}
    />
  );
}

// ============================================================================
// Strategy Mix Slider (shared)
// ============================================================================

export function StrategyMixSlider({
  pAi,
  onChange,
  disabled,
}: {
  /** AI probability 0–1 (left = Bayesian, right = AI) */
  pAi: number;
  onChange: (pAi: number) => void;
  disabled?: boolean;
}) {
  const pAiPct = Math.round(pAi * 100);
  const pBayesianPct = 100 - pAiPct;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <span className="text-sm font-semibold w-24 text-right text-red-600">Bayesian {pBayesianPct}%</span>
        <div className="flex-1 relative">
          {/* Gradient track */}
          <div
            className="absolute inset-0 rounded-full pointer-events-none"
            style={{
              height: '14px',
              top: '50%',
              transform: 'translateY(-50%)',
              background: 'linear-gradient(to right, #dc2626, #9333ea)',
              opacity: disabled ? 0.4 : 0.85,
            }}
          />
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={pAi}
            onChange={(e) => onChange(parseFloat(e.target.value))}
            disabled={disabled}
            className="strategy-slider relative w-full cursor-pointer disabled:cursor-not-allowed"
            style={{ height: '14px' }}
          />
        </div>
        <span className="text-sm font-semibold w-24 text-purple-600">AI {pAiPct}%</span>
      </div>
    </div>
  );
}

// ============================================================================
// Runtime Mode Component
// ============================================================================

function RuntimePanel({ campaignName, optimizerInfo, isRunning, onRefresh }: Omit<RuntimeModeProps, 'mode'>) {
  const { isConnected } = useOrchestratorConnected();
  const { runtime_params } = optimizerInfo;

  const [pBayesian, setPBayesian] = React.useState(runtime_params.p_bayesian);
  const [historySize, setHistorySize] = React.useState(runtime_params.ai_history_size);
  const [additionalContext, setAdditionalContext] = React.useState(runtime_params.ai_additional_context ?? '');
  const [isUpdating, setIsUpdating] = React.useState(false);

  // Sync with props when they update
  React.useEffect(() => {
    setPBayesian(runtime_params.p_bayesian);
    setHistorySize(runtime_params.ai_history_size);
    setAdditionalContext(runtime_params.ai_additional_context ?? '');
  }, [runtime_params]);

  const hasDirtyParams =
    pBayesian !== runtime_params.p_bayesian ||
    historySize !== runtime_params.ai_history_size ||
    additionalContext !== (runtime_params.ai_additional_context ?? '');

  const handleSaveParams = async () => {
    const params: Record<string, unknown> = {};
    if (pBayesian !== runtime_params.p_bayesian) params.p_bayesian = pBayesian;
    if (historySize !== runtime_params.ai_history_size) params.ai_history_size = historySize;
    if (additionalContext !== (runtime_params.ai_additional_context ?? ''))
      params.ai_additional_context = additionalContext || undefined;
    if (Object.keys(params).length === 0) return;
    setIsUpdating(true);
    await updateOptimizerParams(campaignName, params);
    setIsUpdating(false);
    onRefresh?.();
  };

  const disabled = !isRunning || isUpdating || !isConnected;

  return (
    <div className="space-y-4">
      {/* Strategy Mix Slider */}
      <StrategyMixSlider pAi={1 - pBayesian} onChange={(pAi) => setPBayesian(1 - pAi)} disabled={disabled} />

      {/* AI Settings */}
      <div className="space-y-3">
        <Label className="text-sm font-semibold text-purple-600">AI</Label>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label className="text-xs">History Size</Label>
            <Input
              type="number"
              min={1}
              value={historySize}
              onChange={(e) => setHistorySize(parseInt(e.target.value) || 1)}
              disabled={disabled}
              className="text-xs h-8"
            />
          </div>
        </div>

        <div className="space-y-1">
          <Label className="text-xs">Additional Context</Label>
          <Textarea
            value={additionalContext}
            onChange={(e) => setAdditionalContext(e.target.value)}
            placeholder="Additional context for the AI agent..."
            disabled={disabled}
            className="text-xs min-h-[60px]"
          />
        </div>
      </div>

      {/* Save Button */}
      {isRunning && (
        <Button
          variant="default"
          size="sm"
          onClick={handleSaveParams}
          disabled={!hasDirtyParams || isUpdating || !isConnected}
          className="w-full"
        >
          {isUpdating ? 'Saving...' : 'Save Changes'}
        </Button>
      )}
    </div>
  );
}

// ============================================================================
// Submission Mode Component
// ============================================================================

function SubmissionPanel({
  defaults,
  isResume,
  overrides,
  onChange,
  persistedDomain,
  onSave,
  defaultShowDomain = true,
}: Omit<SubmissionModeProps, 'mode'> & {
  onSave?: (values: Record<string, unknown>, domain: DomainValue) => void | Promise<void>;
  defaultShowDomain?: boolean;
}) {
  const params = defaults.params;

  const get = <T,>(key: string, fallback: T): T => {
    return key in overrides ? (overrides[key] as T) : fallback;
  };

  const set = (key: string, value: unknown) => {
    onChange({ ...overrides, [key]: value });
  };

  // Domain state (Tier 3)
  const [domain, setDomain] = React.useState<DomainValue>(() => {
    if (isResume && persistedDomain) {
      return persistedDomain;
    }
    // Parse defaults into DomainValue
    return {
      inputs: (overrides.inputs as DomainValue['inputs']) ?? parseDomainInputs(defaults.inputs),
      outputs: (overrides.outputs as DomainValue['outputs']) ?? parseDomainOutputs(defaults.outputs),
      constraints:
        (overrides.constraints as DomainValue['constraints']) ?? parseDomainConstraints(defaults.constraints),
    };
  });

  const handleDomainChange = (newDomain: DomainValue) => {
    setDomain(newDomain);
    onChange({
      ...overrides,
      inputs: newDomain.inputs,
      outputs: newDomain.outputs,
      constraints: newDomain.constraints,
    });
  };

  const [showDomain, setShowDomain] = React.useState(defaultShowDomain);
  const [justSaved, setJustSaved] = React.useState(false);
  const [isSaving, setIsSaving] = React.useState(false);

  return (
    <div className="space-y-4">
      {/* Strategy Mix Slider */}
      <StrategyMixSlider
        pAi={1 - get<number>('p_bayesian', params.p_bayesian)}
        onChange={(pAi) => set('p_bayesian', 1 - pAi)}
      />

      {/* Bayesian Settings */}
      <div className="space-y-3">
        <Label className="text-sm font-semibold text-red-600">Bayesian</Label>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Num Initial Samples</Label>
            <Input
              type="number"
              min={0}
              value={get<number>('num_initial_samples', params.num_initial_samples)}
              onChange={(e) => set('num_initial_samples', parseInt(e.target.value) || 0)}
              disabled={isResume}
              className="text-xs h-8"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Initial Sampling Method</Label>
            <select
              value={get<string>('initial_sampling_method', params.initial_sampling_method)}
              onChange={(e) => set('initial_sampling_method', e.target.value)}
              className={selectClass}
            >
              <option value="SOBOL">Sobol</option>
              <option value="UNIFORM">Uniform</option>
              <option value="LHS">Latin Hypercube</option>
            </select>
          </div>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Acquisition Function</Label>
          <JsonTextarea
            value={get<Record<string, unknown> | null>('acquisition_function', params.acquisition_function)}
            onChange={(v) => set('acquisition_function', v)}
            placeholder='{"type": "qLogNEI"}'
            className="text-xs min-h-[48px] font-mono"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Surrogate Specs</Label>
          <JsonTextarea
            value={get<Record<string, unknown> | null>('surrogate_specs', params.surrogate_specs)}
            onChange={(v) => set('surrogate_specs', v)}
            placeholder="Leave empty for auto-detected surrogates"
            className="text-xs min-h-[48px] font-mono"
          />
        </div>
      </div>

      {/* AI Settings */}
      <div className="space-y-3">
        <Label className="text-sm font-semibold text-purple-600">AI</Label>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">History Size</Label>
            <Input
              type="number"
              min={1}
              value={get<number>('ai_history_size', params.ai_history_size)}
              onChange={(e) => set('ai_history_size', parseInt(e.target.value) || 1)}
              className="text-xs h-8"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Retries</Label>
            <Input
              type="number"
              min={0}
              value={get<number>('ai_retries', params.ai_retries)}
              onChange={(e) => set('ai_retries', parseInt(e.target.value) || 0)}
              className="text-xs h-8"
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Model</Label>
          <Combobox
            options={AI_MODEL_OPTIONS}
            value={get<string>('ai_model', params.ai_model)}
            onChange={(v) => set('ai_model', v)}
            placeholder="Select a model..."
            searchPlaceholder="Search or type custom model (e.g. ollama:qwen3.5)..."
            allowCustomValue
            className="text-xs h-8"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Model Settings</Label>
          <JsonTextarea
            value={get<Record<string, unknown> | null>('ai_model_settings', params.ai_model_settings)}
            onChange={(v) => set('ai_model_settings', v)}
            placeholder='{"max_thinking_tokens": 1024}'
            className="text-xs min-h-[48px] font-mono"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Additional Parameters</Label>
          <RawInput
            displayValue={(
              get<string[] | null>('ai_additional_parameters', params.ai_additional_parameters) ?? []
            ).join(', ')}
            onRawChange={(text) => {
              const val = text.trim();
              set(
                'ai_additional_parameters',
                val
                  ? val
                      .split(',')
                      .map((s) => s.trim())
                      .filter(Boolean)
                  : null
              );
            }}
            placeholder="e.g. TaskName.param1, TaskName.param2"
            className="text-xs h-8"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Additional Context</Label>
          <Textarea
            value={get<string>('ai_additional_context', params.ai_additional_context ?? '')}
            onChange={(e) => set('ai_additional_context', e.target.value || null)}
            placeholder="Additional context for the AI agent..."
            className="text-xs min-h-[60px]"
          />
        </div>
      </div>

      {/* Tier 3: Domain Definition */}
      <div className="border-t border-gray-200 dark:border-slate-700 pt-3">
        <button
          type="button"
          onClick={() => setShowDomain(!showDomain)}
          className="flex items-center gap-1 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
        >
          {showDomain ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Domain Definition
          {isResume && (
            <span className="ml-2 text-xs text-amber-600 dark:text-amber-400 font-normal">(read-only on resume)</span>
          )}
        </button>
        {showDomain && (
          <div className="mt-3">
            {isResume && (
              <p className="text-xs text-amber-600 dark:text-amber-400 mb-3">
                Domain cannot be changed on resume — existing protocol run history depends on it.
              </p>
            )}
            <DomainEditor value={domain} onChange={handleDomainChange} readOnly={isResume} />
          </div>
        )}
      </div>

      {/* Save Button (editor mode only) */}
      {onSave && (
        <div className="border-t border-gray-200 dark:border-slate-700 pt-3">
          <Button
            variant={justSaved ? 'default' : 'primary'}
            size="sm"
            disabled={isSaving}
            onClick={async () => {
              setIsSaving(true);
              try {
                await onSave(overrides, domain);
                setJustSaved(true);
                setTimeout(() => setJustSaved(false), 2000);
              } finally {
                setIsSaving(false);
              }
            }}
            className="w-full"
          >
            {isSaving ? 'Saving...' : justSaved ? 'Saved!' : 'Save'}
          </Button>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function BeaconOptimizerPanel(props: BeaconOptimizerPanelProps) {
  const [expanded, setExpanded] = React.useState(props.mode === 'editor');

  // Editor mode: manage internal overrides state
  const [editorOverrides, setEditorOverrides] = React.useState<Record<string, unknown>>(() => {
    return props.mode === 'editor' ? { ...props.defaults.params } : {};
  });

  // If in editor mode, render without collapsible header
  if (props.mode === 'editor') {
    return (
      <SubmissionPanel
        defaults={props.defaults}
        isResume={false}
        overrides={editorOverrides}
        onChange={setEditorOverrides}
        onSave={(values, domain) => props.onSave(values, domain)}
      />
    );
  }

  return (
    <div className="bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 p-4">
      <button type="button" onClick={() => setExpanded(!expanded)} className="w-full flex items-center gap-2 text-left">
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-gray-500" />
        ) : (
          <ChevronRight className="h-4 w-4 text-gray-500" />
        )}
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <SlidersHorizontal className="h-5 w-5" />
            Beacon Optimizer
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {props.mode === 'runtime'
              ? 'Tune optimizer parameters in real-time'
              : 'Configure optimizer parameters for this campaign'}
          </p>
        </div>
      </button>
      {expanded && (
        <div className="mt-4">
          {props.mode === 'runtime' ? (
            <RuntimePanel
              campaignName={props.campaignName}
              optimizerInfo={props.optimizerInfo}
              isRunning={props.isRunning}
              onRefresh={props.onRefresh}
            />
          ) : (
            <SubmissionPanel
              defaults={props.defaults}
              isResume={props.isResume}
              overrides={props.overrides}
              onChange={props.onChange}
              persistedDomain={props.persistedDomain}
              defaultShowDomain={false}
            />
          )}
        </div>
      )}
    </div>
  );
}
