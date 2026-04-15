'use client';

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Eraser, ChevronDown, ChevronRight, Upload, Info, Loader2 } from 'lucide-react';
import * as Tooltip from '@radix-ui/react-tooltip';
import { BaseSubmitDialog } from '@/components/dialogs/BaseSubmitDialog';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Textarea } from '@/components/ui/Textarea';
import { Button } from '@/components/ui/Button';
import { Combobox } from '@/components/ui/Combobox';
import { ParameterSearchInput } from '@/components/ui/ParameterSearchInput';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';
import { submitCampaign } from '@/features/campaigns/api/campaigns';
import { getOptimizerDefaults } from '@/features/campaigns/api/optimizer';
import { ProtocolRunParameterField } from '@/features/protocol-runs/components/ProtocolRunParameterField';
import { BeaconOptimizerPanel } from './BeaconOptimizerPanel';
import { extractBeaconDomain } from '../utils/beaconMeta';
import { parseProtocolRunParameters } from '../utils/protocolRunParametersParsing';
import {
  hasNonEmptyObject,
  convertParameters,
  extractParameterValues,
  filterNonDefaultParameters,
} from '@/lib/utils/protocolHelpers';
import type { Campaign, CampaignDefinition, OptimizerDefaults } from '@/lib/types/api';
import type { TaskSpec, ParameterSpec, ParameterValue } from '@/lib/types/protocol';
import type { ProtocolSpec } from '@/lib/api/specs';

const campaignFormSchema = z.object({
  name: z.string().min(1, 'Campaign name is required'),
  protocol: z.string().min(1, 'Protocol type is required'),
  owner: z.string().min(1, 'Owner is required'),
  priority: z.number().min(0),
  max_protocol_runs: z.number().min(0),
  max_concurrent_protocol_runs: z.number().min(1),
  optimize: z.boolean(),
  optimizer_ip: z.string(),
  protocol_run_parameters: z.string().optional(),
  meta: z.string().optional(),
  resume: z.boolean(),
});

type CampaignFormValues = z.infer<typeof campaignFormSchema>;

interface SubmitCampaignDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
  protocolSpecs: Record<string, ProtocolSpec>;
  taskSpecs: Record<string, TaskSpec>;
  initialCampaign?: Campaign | null;
  generateCloneName: (name: string) => Promise<string>;
}

function GlobalParametersSection({
  protocolSpec,
  taskSpecs,
  taskParameters,
  expandedTasks,
  toggleTaskExpansion,
  updateTaskParameter,
  clearTaskParameter,
}: {
  protocolSpec: ProtocolSpec | null;
  taskSpecs: Record<string, TaskSpec>;
  taskParameters: Record<string, Record<string, ParameterValue>>;
  expandedTasks: Set<string>;
  toggleTaskExpansion: (name: string) => void;
  updateTaskParameter: (taskName: string, paramName: string, value: ParameterValue) => void;
  clearTaskParameter: (taskName: string, paramName: string) => void;
}) {
  const [expanded, setExpanded] = React.useState(true);
  const [inputSearch, setInputSearch] = React.useState('');

  if (!protocolSpec || protocolSpec.tasks.length === 0) return null;

  return (
    <div className="space-y-4 pt-2 border-t border-gray-200 dark:border-slate-700">
      <button type="button" onClick={() => setExpanded(!expanded)} className="flex items-center gap-2 w-full text-left">
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-gray-500 dark:text-gray-400" />
        ) : (
          <ChevronRight className="h-4 w-4 text-gray-500 dark:text-gray-400" />
        )}
        <div>
          <Label className="text-base cursor-pointer">Global Parameters</Label>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Parameters shared across all protocol runs in this campaign
          </p>
        </div>
      </button>

      {expanded && (
        <>
          <ParameterSearchInput value={inputSearch} onChange={setInputSearch} />
          {protocolSpec.tasks.map((taskConfig) => {
            const taskSpec = taskSpecs[taskConfig.type];
            if (!taskSpec || !taskSpec.input_parameters || Object.keys(taskSpec.input_parameters).length === 0) {
              return null;
            }

            const searchLower = inputSearch.toLowerCase();
            const taskNameMatches =
              !searchLower ||
              taskConfig.name.toLowerCase().includes(searchLower) ||
              taskConfig.type.toLowerCase().includes(searchLower);
            const filteredParams = Object.entries(taskSpec.input_parameters).filter(([paramName, paramSpec]) => {
              if (!searchLower || taskNameMatches) return true;
              const spec = paramSpec as ParameterSpec;
              return (
                paramName.toLowerCase().includes(searchLower) ||
                (spec.desc && spec.desc.toLowerCase().includes(searchLower)) ||
                spec.type.toLowerCase().includes(searchLower)
              );
            });

            if (searchLower && !taskNameMatches && filteredParams.length === 0) return null;

            const isExpanded = searchLower ? true : expandedTasks.has(taskConfig.name);

            return (
              <div
                key={taskConfig.name}
                className="border border-gray-200 dark:border-slate-700 rounded-md bg-gray-50 dark:bg-slate-800/50"
              >
                <button
                  type="button"
                  onClick={() => toggleTaskExpansion(taskConfig.name)}
                  className="w-full px-3 py-2.5 flex items-center justify-between hover:bg-gray-100 dark:hover:bg-slate-700/50 transition-colors rounded-t-md"
                >
                  <div className="flex items-center gap-2">
                    {isExpanded ? (
                      <ChevronDown className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                    )}
                    <div className="text-left">
                      <div className="text-sm font-medium text-gray-900 dark:text-white">{taskConfig.name}</div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        Type: {taskConfig.type}
                        {taskConfig.desc && <DescriptionTooltip description={taskConfig.desc} />}
                      </div>
                    </div>
                  </div>
                </button>

                {isExpanded && (
                  <div className="px-3 pt-3 pb-3 space-y-2.5 border-t border-gray-200 dark:border-slate-700">
                    {filteredParams.map(([paramName, paramSpec]) => (
                      <ProtocolRunParameterField
                        key={paramName}
                        paramName={paramName}
                        paramSpec={paramSpec as ParameterSpec}
                        value={taskParameters[taskConfig.name]?.[paramName]}
                        specDefault={taskConfig.parameters?.[paramName]}
                        onChange={(value) => updateTaskParameter(taskConfig.name, paramName, value)}
                        onClear={() => clearTaskParameter(taskConfig.name, paramName)}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}

export function SubmitCampaignDialog({
  open,
  onOpenChange,
  onSuccess,
  protocolSpecs,
  taskSpecs,
  initialCampaign,
  generateCloneName,
}: SubmitCampaignDialogProps) {
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedProtocolSpec, setSelectedProtocolSpec] = React.useState<ProtocolSpec | null>(null);
  const [optimizerDefaults, setOptimizerDefaults] = React.useState<OptimizerDefaults | null>(null);
  const [optimizerOverrides, setOptimizerOverrides] = React.useState<Record<string, unknown>>({});
  const [isLoadingOptimizer, setIsLoadingOptimizer] = React.useState(false);

  // Visual editor state - task parameters structure: { task_name: { param_name: ParameterValue } }
  const [taskParameters, setTaskParameters] = React.useState<Record<string, Record<string, ParameterValue>>>({});

  // Track which task sections are expanded (default: all expanded)
  const [expandedTasks, setExpandedTasks] = React.useState<Set<string>>(new Set());

  // Track if we've already populated from initialCampaign to prevent re-population
  const populatedFromCampaignRef = React.useRef<string | null>(null);

  // File upload for protocol run parameters
  const paramFileInputRef = React.useRef<HTMLInputElement>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
  } = useForm<CampaignFormValues>({
    resolver: zodResolver(campaignFormSchema),
    defaultValues: {
      name: '',
      protocol: '',
      owner: '',
      priority: 0,
      max_protocol_runs: 0,
      max_concurrent_protocol_runs: 1,
      optimize: true,
      optimizer_ip: '127.0.0.1',
      protocol_run_parameters: '',
      meta: '',
      resume: false,
    },
  });

  const optimize = watch('optimize');
  const protocolType = watch('protocol');
  const isResume = watch('resume');

  // Create protocol type options from specs
  const protocolTypeOptions = React.useMemo(
    () =>
      Object.entries(protocolSpecs).map(([type, spec]) => ({
        value: type,
        label: type,
        description: spec.desc,
      })),
    [protocolSpecs]
  );

  // Initialize from clone - cloned parameters ARE overrides
  React.useEffect(() => {
    if (initialCampaign && populatedFromCampaignRef.current !== initialCampaign.name) {
      populatedFromCampaignRef.current = initialCampaign.name;

      generateCloneName(initialCampaign.name).then((name) => setValue('name', name));
      setValue('protocol', initialCampaign.protocol);
      setValue('owner', initialCampaign.owner);
      setValue('priority', initialCampaign.priority ?? 0);
      setValue('max_protocol_runs', initialCampaign.max_protocol_runs ?? 0);
      setValue('max_concurrent_protocol_runs', initialCampaign.max_concurrent_protocol_runs ?? 1);
      setValue('optimize', initialCampaign.optimize);
      setValue('optimizer_ip', initialCampaign.optimizer_ip || '127.0.0.1');
      setValue('resume', initialCampaign.resume || false);
      setValue(
        'protocol_run_parameters',
        hasNonEmptyObject(initialCampaign.protocol_run_parameters)
          ? JSON.stringify(initialCampaign.protocol_run_parameters, null, 2)
          : ''
      );
      if (hasNonEmptyObject(initialCampaign.meta)) {
        const { optimizer_overrides: _optimizerOverrides, ...restMeta } = initialCampaign.meta!;
        setValue('meta', hasNonEmptyObject(restMeta) ? JSON.stringify(restMeta, null, 2) : '');
      } else {
        setValue('meta', '');
      }

      if (initialCampaign.global_parameters) {
        // Get the protocol spec for filtering
        const expSpec = protocolSpecs[initialCampaign.protocol];

        // Filter out parameters that match spec defaults to avoid false "override" indicators
        const filteredParams = expSpec
          ? filterNonDefaultParameters(initialCampaign.global_parameters, expSpec)
          : initialCampaign.global_parameters;

        const convertedParams = convertParameters(filteredParams);
        setTaskParameters(convertedParams);
        setExpandedTasks(new Set(Object.keys(convertedParams)));
      } else {
        setTaskParameters({});
        setExpandedTasks(new Set());
      }
    }
  }, [initialCampaign, protocolSpecs, generateCloneName, setValue]);

  // Load protocol spec when type changes
  React.useEffect(() => {
    if (protocolType && protocolSpecs[protocolType]) {
      const spec = protocolSpecs[protocolType];
      setSelectedProtocolSpec(spec);

      // Expand all tasks by default (but don't initialize taskParameters - it only holds overrides)
      setExpandedTasks(new Set(spec.tasks.map((t) => t.name)));
    } else {
      setSelectedProtocolSpec(null);
    }
  }, [protocolType, protocolSpecs]);

  // Fetch optimizer defaults when protocol type changes and optimize is enabled
  React.useEffect(() => {
    if (optimize && protocolType) {
      setIsLoadingOptimizer(true);
      getOptimizerDefaults(protocolType)
        .then((defaults) => {
          setOptimizerDefaults(defaults);
          if (initialCampaign?.meta?.optimizer_overrides) {
            setOptimizerOverrides(initialCampaign.meta.optimizer_overrides as Record<string, unknown>);
          } else {
            setOptimizerOverrides({});
          }
        })
        .finally(() => setIsLoadingOptimizer(false));
    } else {
      setOptimizerDefaults(null);
      setOptimizerOverrides({});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally read once during clone
  }, [optimize, protocolType]);

  const toggleTaskExpansion = (taskName: string) => {
    setExpandedTasks((prev) => {
      const next = new Set(prev);
      if (next.has(taskName)) {
        next.delete(taskName);
      } else {
        next.add(taskName);
      }
      return next;
    });
  };

  const updateTaskParameter = (taskName: string, paramName: string, value: ParameterValue) => {
    setTaskParameters((prev) => ({
      ...prev,
      [taskName]: {
        ...(prev[taskName] || {}),
        [paramName]: value,
      },
    }));
  };

  // Remove an override, reverting to spec default
  const clearTaskParameter = (taskName: string, paramName: string) => {
    setTaskParameters((prev) => {
      const taskParams = prev[taskName];
      if (!taskParams) return prev;

      const { [paramName]: _removed, ...rest } = taskParams;
      void _removed; // Destructuring to remove the key
      if (Object.keys(rest).length === 0) {
        const { [taskName]: _removedTask, ...taskRest } = prev;
        void _removedTask; // Destructuring to remove the key
        return taskRest;
      }
      return { ...prev, [taskName]: rest };
    });
  };

  const handleClear = () => {
    reset({
      name: '',
      protocol: '',
      owner: '',
      priority: 0,
      max_protocol_runs: 0,
      max_concurrent_protocol_runs: 1,
      optimize: true,
      optimizer_ip: '127.0.0.1',
      protocol_run_parameters: '',
      meta: '',
      resume: false,
    });

    // Clear all overrides (taskParameters only holds overrides)
    setTaskParameters({});

    // Keep tasks expanded
    if (selectedProtocolSpec) {
      setExpandedTasks(new Set(selectedProtocolSpec.tasks.map((t) => t.name)));
    } else {
      setExpandedTasks(new Set());
    }

    setOptimizerOverrides({});
    setError(null);
    populatedFromCampaignRef.current = null; // Reset so we can clone again if needed
  };

  const onSubmit = async (data: CampaignFormValues) => {
    setIsSubmitting(true);
    setError(null);

    try {
      const global_parameters = extractParameterValues(taskParameters);
      let protocol_run_parameters: Array<Record<string, Record<string, unknown>>> | null;
      try {
        protocol_run_parameters = data.protocol_run_parameters?.trim()
          ? parseProtocolRunParameters(data.protocol_run_parameters)
          : null;
      } catch (e) {
        throw new Error(e instanceof Error ? e.message : 'Invalid protocol run parameters');
      }
      let meta: Record<string, unknown>;
      try {
        meta = data.meta?.trim() ? JSON.parse(data.meta) : {};
      } catch {
        throw new Error('Invalid JSON in "Metadata" field');
      }

      // Include optimizer overrides in meta — only values that differ from defaults
      if (data.optimize && optimizerDefaults) {
        const defaults = optimizerDefaults.params as Record<string, unknown>;
        const actualOverrides: Record<string, unknown> = {};
        for (const [key, value] of Object.entries(optimizerOverrides)) {
          if (JSON.stringify(value) !== JSON.stringify(defaults[key])) {
            actualOverrides[key] = value;
          }
        }
        if (Object.keys(actualOverrides).length > 0) {
          meta.optimizer_overrides = actualOverrides;
        }
      }

      const campaignDefinition: CampaignDefinition = {
        name: data.name,
        protocol: data.protocol,
        owner: data.owner,
        priority: data.priority,
        max_protocol_runs: data.max_protocol_runs,
        max_concurrent_protocol_runs: data.max_concurrent_protocol_runs,
        optimize: data.optimize,
        optimizer_ip: data.optimizer_ip,
        global_parameters: Object.keys(global_parameters).length > 0 ? global_parameters : undefined,
        protocol_run_parameters,
        meta,
        resume: data.resume,
      };

      const result = await submitCampaign(campaignDefinition);

      if (result.success) {
        onOpenChange(false);
        onSuccess?.();
      } else {
        setError(result.error || 'Failed to submit campaign');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid input in one of the fields');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Tooltip.Provider delayDuration={300}>
      <BaseSubmitDialog
        open={open}
        onOpenChange={onOpenChange}
        title="Submit Campaign"
        submitLabel="Submit Campaign"
        isSubmitting={isSubmitting}
        error={error}
        onSubmit={handleSubmit(onSubmit)}
        maxWidth="3xl"
        headerActions={
          <Button variant="outline" size="sm" onClick={handleClear} className="gap-2">
            <Eraser className="w-4 h-4" />
            Clear
          </Button>
        }
      >
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="name">Campaign Name *</Label>
            <Input id="name" {...register('name')} error={errors.name?.message} placeholder="my_campaign" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="protocol">Protocol *</Label>
            <Combobox
              options={protocolTypeOptions}
              value={protocolType}
              onChange={(value) => setValue('protocol', value, { shouldValidate: true })}
              placeholder="Select protocol"
              searchPlaceholder="Search protocols..."
              emptyText="No protocols found"
            />
            {errors.protocol && <p className="text-sm text-red-600">{errors.protocol.message}</p>}
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="owner">Owner *</Label>
          <Input id="owner" {...register('owner')} error={errors.owner?.message} placeholder="user1" />
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div className="space-y-2">
            <Label htmlFor="priority">Priority</Label>
            <Input
              id="priority"
              type="number"
              {...register('priority', { valueAsNumber: true })}
              error={errors.priority?.message}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="max_protocol_runs">Max Protocol Runs</Label>
            <Input
              id="max_protocol_runs"
              type="number"
              {...register('max_protocol_runs', { valueAsNumber: true })}
              error={errors.max_protocol_runs?.message}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="max_concurrent_protocol_runs">Max Concurrent Protocol Runs</Label>
            <Input
              id="max_concurrent_protocol_runs"
              type="number"
              {...register('max_concurrent_protocol_runs', { valueAsNumber: true })}
              error={errors.max_concurrent_protocol_runs?.message}
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <input
            id="optimize"
            type="checkbox"
            {...register('optimize')}
            className="h-4 w-4 rounded border-gray-300 dark:border-slate-600 dark:bg-slate-800 text-blue-600 focus:ring-blue-600"
          />
          <Label htmlFor="optimize" className="cursor-pointer">
            Enable Optimization
          </Label>
        </div>

        {optimize && (
          <div className="space-y-2">
            <Label htmlFor="optimizer_ip">Optimizer IP</Label>
            <Input id="optimizer_ip" {...register('optimizer_ip')} error={errors.optimizer_ip?.message} />
          </div>
        )}

        {/* Beacon Optimizer Settings */}
        {optimize && isLoadingOptimizer && (
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 py-4">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading optimizer settings...
          </div>
        )}
        {optimize && optimizerDefaults && optimizerDefaults.optimizer_type === 'BeaconOptimizer' && (
          <BeaconOptimizerPanel
            mode="submission"
            defaults={optimizerDefaults}
            isResume={isResume}
            overrides={optimizerOverrides}
            onChange={setOptimizerOverrides}
            persistedDomain={isResume && initialCampaign?.meta ? extractBeaconDomain(initialCampaign.meta) : null}
          />
        )}

        <div className="flex items-center gap-2">
          <input
            id="resume"
            type="checkbox"
            {...register('resume')}
            className="h-4 w-4 rounded border-gray-300 dark:border-slate-600 dark:bg-slate-800 text-blue-600 focus:ring-blue-600"
          />
          <Label htmlFor="resume" className="cursor-pointer">
            Resume if exists
          </Label>
        </div>

        {/* Global Parameters - Visual Editor (collapsible) */}
        <GlobalParametersSection
          protocolSpec={selectedProtocolSpec}
          taskSpecs={taskSpecs}
          taskParameters={taskParameters}
          expandedTasks={expandedTasks}
          toggleTaskExpansion={toggleTaskExpansion}
          updateTaskParameter={updateTaskParameter}
          clearTaskParameter={clearTaskParameter}
        />

        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Label htmlFor="protocol_run_parameters">Protocol Run Parameters</Label>
            <Tooltip.Root>
              <Tooltip.Trigger asChild>
                <button
                  type="button"
                  className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
                >
                  <Info className="w-4 h-4" />
                </button>
              </Tooltip.Trigger>
              <Tooltip.Portal>
                <Tooltip.Content
                  className="bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 px-3 py-2 rounded-md text-xs max-w-xs shadow-lg z-[100]"
                  sideOffset={5}
                >
                  <p className="font-medium mb-1">Accepts JSON or CSV</p>
                  <p className="mb-1">JSON: [&#123;&quot;task.param&quot;: value&#125;, ...]</p>
                  <p>CSV: dot-notation headers (task.param), one protocol run per row. Missing columns are OK.</p>
                  <Tooltip.Arrow className="fill-gray-900 dark:fill-gray-100" />
                </Tooltip.Content>
              </Tooltip.Portal>
            </Tooltip.Root>
            <div className="flex-1" />
            <button
              type="button"
              onClick={() => paramFileInputRef.current?.click()}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
            >
              <Upload className="w-3.5 h-3.5" />
              Upload
            </button>
            <input
              ref={paramFileInputRef}
              type="file"
              accept=".json,.csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = () => {
                  if (typeof reader.result === 'string') {
                    setValue('protocol_run_parameters', reader.result, { shouldValidate: true });
                  }
                };
                reader.readAsText(file);
                e.target.value = '';
              }}
            />
          </div>
          <Textarea
            id="protocol_run_parameters"
            {...register('protocol_run_parameters')}
            error={errors.protocol_run_parameters?.message}
            placeholder="Paste JSON array or CSV"
          />
          {!optimize && <p className="text-xs text-gray-500 dark:text-gray-400">Required if not optimizing</p>}
        </div>

        <div className="space-y-2">
          <Label htmlFor="meta">Metadata (JSON)</Label>
          <Textarea
            id="meta"
            {...register('meta')}
            error={errors.meta?.message}
            placeholder='{"description": "Test campaign"}'
          />
        </div>
      </BaseSubmitDialog>
    </Tooltip.Provider>
  );
}
