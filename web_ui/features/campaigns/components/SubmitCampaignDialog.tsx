'use client';

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Eraser, ChevronDown, ChevronRight, Upload, Info } from 'lucide-react';
import * as Tooltip from '@radix-ui/react-tooltip';
import { BaseSubmitDialog } from '@/components/dialogs/BaseSubmitDialog';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Textarea } from '@/components/ui/Textarea';
import { Button } from '@/components/ui/Button';
import { Combobox } from '@/components/ui/Combobox';
import { submitCampaign } from '@/features/campaigns/api/campaigns';
import { getOptimizerDefaults } from '@/features/campaigns/api/optimizer';
import { ExperimentParameterField } from '@/features/experiments/components/ExperimentParameterField';
import { BeaconOptimizerPanel } from './BeaconOptimizerPanel';
import { extractBeaconDomain } from '../utils/beaconMeta';
import { parseExperimentParameters } from '../utils/experimentParametersParsing';
import {
  hasNonEmptyObject,
  convertParameters,
  extractParameterValues,
  filterNonDefaultParameters,
} from '@/lib/utils/experimentHelpers';
import type { Campaign, CampaignDefinition, OptimizerDefaults } from '@/lib/types/api';
import type { TaskSpec, ParameterSpec, ParameterValue } from '@/lib/types/experiment';
import type { ExperimentSpec } from '@/lib/api/specs';

const campaignFormSchema = z.object({
  name: z.string().min(1, 'Campaign name is required'),
  experiment_type: z.string().min(1, 'Experiment type is required'),
  owner: z.string().min(1, 'Owner is required'),
  priority: z.number().min(0),
  max_experiments: z.number().min(0),
  max_concurrent_experiments: z.number().min(1),
  optimize: z.boolean(),
  optimizer_ip: z.string(),
  experiment_parameters: z.string().optional(),
  meta: z.string().optional(),
  resume: z.boolean(),
});

type CampaignFormValues = z.infer<typeof campaignFormSchema>;

interface SubmitCampaignDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  experimentSpecs: Record<string, ExperimentSpec>;
  taskSpecs: Record<string, TaskSpec>;
  initialCampaign?: Campaign | null;
  generateCloneName: (name: string) => Promise<string>;
}

function GlobalParametersSection({
  experimentSpec,
  taskSpecs,
  taskParameters,
  expandedTasks,
  toggleTaskExpansion,
  updateTaskParameter,
  clearTaskParameter,
}: {
  experimentSpec: ExperimentSpec | null;
  taskSpecs: Record<string, TaskSpec>;
  taskParameters: Record<string, Record<string, ParameterValue>>;
  expandedTasks: Set<string>;
  toggleTaskExpansion: (name: string) => void;
  updateTaskParameter: (taskName: string, paramName: string, value: ParameterValue) => void;
  clearTaskParameter: (taskName: string, paramName: string) => void;
}) {
  const [expanded, setExpanded] = React.useState(true);

  if (!experimentSpec || experimentSpec.tasks.length === 0) return null;

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
            Parameters shared across all experiments in this campaign
          </p>
        </div>
      </button>

      {expanded &&
        experimentSpec.tasks.map((taskConfig) => {
          const taskSpec = taskSpecs[taskConfig.type];
          if (!taskSpec || !taskSpec.input_parameters || Object.keys(taskSpec.input_parameters).length === 0) {
            return null;
          }

          const isExpanded = expandedTasks.has(taskConfig.name);

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
                      {taskConfig.desc && ` - ${taskConfig.desc}`}
                    </div>
                  </div>
                </div>
              </button>

              {isExpanded && (
                <div className="px-3 pt-3 pb-3 space-y-2.5 border-t border-gray-200 dark:border-slate-700">
                  {Object.entries(taskSpec.input_parameters).map(([paramName, paramSpec]) => (
                    <ExperimentParameterField
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
    </div>
  );
}

export function SubmitCampaignDialog({
  open,
  onOpenChange,
  experimentSpecs,
  taskSpecs,
  initialCampaign,
  generateCloneName,
}: SubmitCampaignDialogProps) {
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedExperimentSpec, setSelectedExperimentSpec] = React.useState<ExperimentSpec | null>(null);
  const [optimizerDefaults, setOptimizerDefaults] = React.useState<OptimizerDefaults | null>(null);
  const [optimizerOverrides, setOptimizerOverrides] = React.useState<Record<string, unknown>>({});

  // Visual editor state - task parameters structure: { task_name: { param_name: ParameterValue } }
  const [taskParameters, setTaskParameters] = React.useState<Record<string, Record<string, ParameterValue>>>({});

  // Track which task sections are expanded (default: all expanded)
  const [expandedTasks, setExpandedTasks] = React.useState<Set<string>>(new Set());

  // Track if we've already populated from initialCampaign to prevent re-population
  const populatedFromCampaignRef = React.useRef<string | null>(null);

  // File upload for experiment parameters
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
      experiment_type: '',
      owner: '',
      priority: 0,
      max_experiments: 0,
      max_concurrent_experiments: 1,
      optimize: true,
      optimizer_ip: '127.0.0.1',
      experiment_parameters: '',
      meta: '',
      resume: false,
    },
  });

  const optimize = watch('optimize');
  const experimentType = watch('experiment_type');
  const isResume = watch('resume');

  // Create experiment type options from specs
  const experimentTypeOptions = React.useMemo(
    () =>
      Object.entries(experimentSpecs).map(([type, spec]) => ({
        value: type,
        label: type,
        description: spec.desc,
      })),
    [experimentSpecs]
  );

  // Initialize from clone - cloned parameters ARE overrides
  React.useEffect(() => {
    if (initialCampaign && populatedFromCampaignRef.current !== initialCampaign.name) {
      populatedFromCampaignRef.current = initialCampaign.name;

      generateCloneName(initialCampaign.name).then((name) => setValue('name', name));
      setValue('experiment_type', initialCampaign.experiment_type);
      setValue('owner', initialCampaign.owner);
      setValue('priority', initialCampaign.priority ?? 0);
      setValue('max_experiments', initialCampaign.max_experiments ?? 0);
      setValue('max_concurrent_experiments', initialCampaign.max_concurrent_experiments ?? 1);
      setValue('optimize', initialCampaign.optimize);
      setValue('optimizer_ip', initialCampaign.optimizer_ip || '127.0.0.1');
      setValue('resume', initialCampaign.resume || false);
      setValue(
        'experiment_parameters',
        hasNonEmptyObject(initialCampaign.experiment_parameters)
          ? JSON.stringify(initialCampaign.experiment_parameters, null, 2)
          : ''
      );
      if (hasNonEmptyObject(initialCampaign.meta)) {
        const { optimizer_overrides: _optimizerOverrides, ...restMeta } = initialCampaign.meta!;
        setValue('meta', hasNonEmptyObject(restMeta) ? JSON.stringify(restMeta, null, 2) : '');
      } else {
        setValue('meta', '');
      }

      if (initialCampaign.global_parameters) {
        // Get the experiment spec for filtering
        const expSpec = experimentSpecs[initialCampaign.experiment_type];

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
  }, [initialCampaign, experimentSpecs, generateCloneName, setValue]);

  // Load experiment spec when type changes
  React.useEffect(() => {
    if (experimentType && experimentSpecs[experimentType]) {
      const spec = experimentSpecs[experimentType];
      setSelectedExperimentSpec(spec);

      // Expand all tasks by default (but don't initialize taskParameters - it only holds overrides)
      setExpandedTasks(new Set(spec.tasks.map((t) => t.name)));
    } else {
      setSelectedExperimentSpec(null);
    }
  }, [experimentType, experimentSpecs]);

  // Fetch optimizer defaults when experiment type changes and optimize is enabled
  React.useEffect(() => {
    if (optimize && experimentType) {
      getOptimizerDefaults(experimentType).then((defaults) => {
        setOptimizerDefaults(defaults);
        if (initialCampaign?.meta?.optimizer_overrides) {
          setOptimizerOverrides(initialCampaign.meta.optimizer_overrides as Record<string, unknown>);
        } else {
          setOptimizerOverrides({});
        }
      });
    } else {
      setOptimizerDefaults(null);
      setOptimizerOverrides({});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally read once during clone
  }, [optimize, experimentType]);

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
      experiment_type: '',
      owner: '',
      priority: 0,
      max_experiments: 0,
      max_concurrent_experiments: 1,
      optimize: true,
      optimizer_ip: '127.0.0.1',
      experiment_parameters: '',
      meta: '',
      resume: false,
    });

    // Clear all overrides (taskParameters only holds overrides)
    setTaskParameters({});

    // Keep tasks expanded
    if (selectedExperimentSpec) {
      setExpandedTasks(new Set(selectedExperimentSpec.tasks.map((t) => t.name)));
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
      let experiment_parameters: Array<Record<string, Record<string, unknown>>> | null;
      try {
        experiment_parameters = data.experiment_parameters?.trim()
          ? parseExperimentParameters(data.experiment_parameters)
          : null;
      } catch (e) {
        throw new Error(e instanceof Error ? e.message : 'Invalid experiment parameters');
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
        experiment_type: data.experiment_type,
        owner: data.owner,
        priority: data.priority,
        max_experiments: data.max_experiments,
        max_concurrent_experiments: data.max_concurrent_experiments,
        optimize: data.optimize,
        optimizer_ip: data.optimizer_ip,
        global_parameters: Object.keys(global_parameters).length > 0 ? global_parameters : undefined,
        experiment_parameters,
        meta,
        resume: data.resume,
      };

      const result = await submitCampaign(campaignDefinition);

      if (result.success) {
        onOpenChange(false);
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
            <Label htmlFor="experiment_type">Experiment Type *</Label>
            <Combobox
              options={experimentTypeOptions}
              value={experimentType}
              onChange={(value) => setValue('experiment_type', value, { shouldValidate: true })}
              placeholder="Select experiment type"
              searchPlaceholder="Search experiment types..."
              emptyText="No experiment types found"
            />
            {errors.experiment_type && <p className="text-sm text-red-600">{errors.experiment_type.message}</p>}
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
            <Label htmlFor="max_experiments">Max Experiments</Label>
            <Input
              id="max_experiments"
              type="number"
              {...register('max_experiments', { valueAsNumber: true })}
              error={errors.max_experiments?.message}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="max_concurrent_experiments">Max Concurrent Experiments</Label>
            <Input
              id="max_concurrent_experiments"
              type="number"
              {...register('max_concurrent_experiments', { valueAsNumber: true })}
              error={errors.max_concurrent_experiments?.message}
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
          experimentSpec={selectedExperimentSpec}
          taskSpecs={taskSpecs}
          taskParameters={taskParameters}
          expandedTasks={expandedTasks}
          toggleTaskExpansion={toggleTaskExpansion}
          updateTaskParameter={updateTaskParameter}
          clearTaskParameter={clearTaskParameter}
        />

        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Label htmlFor="experiment_parameters">Experiment Parameters</Label>
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
                  <p>CSV: dot-notation headers (task.param), one experiment per row. Missing columns are OK.</p>
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
                    setValue('experiment_parameters', reader.result, { shouldValidate: true });
                  }
                };
                reader.readAsText(file);
                e.target.value = '';
              }}
            />
          </div>
          <Textarea
            id="experiment_parameters"
            {...register('experiment_parameters')}
            error={errors.experiment_parameters?.message}
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
