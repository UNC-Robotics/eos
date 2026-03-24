'use client';

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Eraser, ChevronDown, ChevronRight } from 'lucide-react';
import { BaseSubmitDialog } from '@/components/dialogs/BaseSubmitDialog';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Textarea } from '@/components/ui/Textarea';
import { Button } from '@/components/ui/Button';
import { Combobox } from '@/components/ui/Combobox';
import { submitExperiment } from '@/features/experiments/api/experiments';
import { ExperimentParameterField } from './ExperimentParameterField';
import {
  hasNonEmptyObject,
  convertParameters,
  extractParameterValues,
  filterNonDefaultParameters,
} from '@/lib/utils/experimentHelpers';
import type { ExperimentDefinition, Experiment } from '@/lib/types/api';
import type { TaskSpec, ParameterSpec, ParameterValue } from '@/lib/types/experiment';
import type { ExperimentSpec, LabSpec } from '@/lib/api/specs';

const experimentFormSchema = z.object({
  name: z.string().min(1, 'Experiment name is required'),
  type: z.string().min(1, 'Experiment type is required'),
  owner: z.string().min(1, 'Owner is required'),
  priority: z.number().min(0),
  meta: z.string().optional(),
  resume: z.boolean(),
});

type ExperimentFormValues = z.infer<typeof experimentFormSchema>;

interface SubmitExperimentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  experimentSpecs: Record<string, ExperimentSpec>;
  taskSpecs: Record<string, TaskSpec>;
  labSpecs: Record<string, LabSpec>;
  initialExperiment?: Experiment | null;
  generateCloneName: (name: string) => Promise<string>;
}

export function SubmitExperimentDialog({
  open,
  onOpenChange,
  experimentSpecs,
  taskSpecs,
  labSpecs: _labSpecs,
  initialExperiment,
  generateCloneName,
}: SubmitExperimentDialogProps) {
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedExperimentSpec, setSelectedExperimentSpec] = React.useState<ExperimentSpec | null>(null);

  // Visual editor state - task parameters structure: { task_name: { param_name: ParameterValue } }
  const [taskParameters, setTaskParameters] = React.useState<Record<string, Record<string, ParameterValue>>>({});

  // Track which task sections are expanded (default: all expanded)
  const [expandedTasks, setExpandedTasks] = React.useState<Set<string>>(new Set());

  // Track if we've already populated from initialExperiment to prevent re-population
  const populatedFromExpRef = React.useRef<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
  } = useForm<ExperimentFormValues>({
    resolver: zodResolver(experimentFormSchema),
    defaultValues: {
      name: '',
      type: '',
      owner: '',
      priority: 0,
      meta: '',
      resume: false,
    },
  });

  const experimentType = watch('type');

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
    if (initialExperiment && populatedFromExpRef.current !== initialExperiment.name) {
      populatedFromExpRef.current = initialExperiment.name;

      generateCloneName(initialExperiment.name).then((name) => setValue('name', name));
      setValue('type', initialExperiment.type);
      setValue('owner', initialExperiment.owner);
      setValue('priority', initialExperiment.priority ?? 0);
      setValue('resume', initialExperiment.resume || false);
      setValue(
        'meta',
        hasNonEmptyObject(initialExperiment.meta) ? JSON.stringify(initialExperiment.meta, null, 2) : ''
      );

      if (initialExperiment.parameters) {
        // Get the experiment spec for filtering
        const expSpec = experimentSpecs[initialExperiment.type];

        // Filter out parameters that match spec defaults to avoid false "override" indicators
        const filteredParams = expSpec
          ? filterNonDefaultParameters(initialExperiment.parameters, expSpec)
          : initialExperiment.parameters;

        const convertedParams = convertParameters(filteredParams);
        setTaskParameters(convertedParams);
        setExpandedTasks(new Set(Object.keys(convertedParams)));
      } else {
        setTaskParameters({});
        setExpandedTasks(new Set());
      }
    }
  }, [initialExperiment, experimentSpecs, generateCloneName, setValue]);

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
      type: '',
      owner: '',
      priority: 0,
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

    setError(null);
    populatedFromExpRef.current = null; // Reset so we can clone again if needed
  };

  const onSubmit = async (data: ExperimentFormValues) => {
    setIsSubmitting(true);
    setError(null);

    try {
      // Create task type map from experiment spec
      const taskTypeMap: Record<string, string> = {};
      if (selectedExperimentSpec) {
        selectedExperimentSpec.tasks.forEach((task) => {
          taskTypeMap[task.name] = task.type;
        });
      }

      const parameters = extractParameterValues(taskParameters, taskTypeMap, taskSpecs);
      const meta = data.meta ? JSON.parse(data.meta) : null;

      const experimentDefinition: ExperimentDefinition = {
        name: data.name,
        type: data.type,
        owner: data.owner,
        priority: data.priority,
        parameters: Object.keys(parameters).length > 0 ? parameters : {},
        meta,
        resume: data.resume,
      };

      const result = await submitExperiment(experimentDefinition);

      if (result.success) {
        onOpenChange(false);
      } else {
        setError(result.error || 'Failed to submit experiment');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid input in one of the fields');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <BaseSubmitDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Submit New Experiment"
      submitLabel="Submit Experiment"
      isSubmitting={isSubmitting}
      error={error}
      onSubmit={handleSubmit(onSubmit)}
      headerActions={
        <Button variant="outline" size="sm" onClick={handleClear} className="gap-2">
          <Eraser className="w-4 h-4" />
          Clear
        </Button>
      }
    >
      {/* Basic Fields */}
      <div className="space-y-2">
        <Label htmlFor="name">Experiment Name *</Label>
        <Input id="name" {...register('name')} error={errors.name?.message} placeholder="my_experiment" />
      </div>

      <div className="space-y-2">
        <Label htmlFor="type">Experiment Type *</Label>
        <Combobox
          options={experimentTypeOptions}
          value={experimentType}
          onChange={(value) => setValue('type', value, { shouldValidate: true })}
          placeholder="Select experiment type"
          searchPlaceholder="Search experiment types..."
          emptyText="No experiment types found"
        />
        {errors.type && <p className="text-sm text-red-600">{errors.type.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="owner">Owner *</Label>
        <Input id="owner" {...register('owner')} error={errors.owner?.message} placeholder="user1" />
      </div>

      <div className="space-y-2">
        <Label htmlFor="priority">Priority</Label>
        <Input
          id="priority"
          type="number"
          {...register('priority', { valueAsNumber: true })}
          error={errors.priority?.message}
        />
      </div>

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

      {/* Task Parameters Section */}
      {selectedExperimentSpec && selectedExperimentSpec.tasks.length > 0 && (
        <div className="space-y-4 pt-2 border-t border-gray-200 dark:border-slate-700">
          <div>
            <Label className="text-base">Task Parameters</Label>
          </div>

          {selectedExperimentSpec.tasks.map((taskConfig) => {
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
                {/* Collapsible Header */}
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

                {/* Collapsible Content */}
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
      )}

      {/* Metadata Section */}
      <div className="space-y-2 border-t border-gray-200 dark:border-slate-700 pt-4">
        <Label htmlFor="meta">Metadata (JSON)</Label>
        <Textarea
          id="meta"
          {...register('meta')}
          error={errors.meta?.message}
          placeholder='{"description": "Test experiment"}'
        />
      </div>
    </BaseSubmitDialog>
  );
}
