'use client';

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Eraser } from 'lucide-react';
import { BaseSubmitDialog } from '@/components/dialogs/BaseSubmitDialog';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Textarea } from '@/components/ui/Textarea';
import { Button } from '@/components/ui/Button';
import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';
import { ParameterSearchInput } from '@/components/ui/ParameterSearchInput';
import { submitTask } from '@/features/tasks/api/tasks';
import { getTaskPlugins } from '@/features/management/api/taskPlugins';
import { TaskDeviceAssignment } from './TaskDeviceAssignment';
import { TaskResourceAssignment } from './TaskResourceAssignment';
import { TaskParameterFields } from './TaskParameterFields';
import { serializeDeviceAssignment, serializeResourceAssignment } from '@/lib/utils/assignment-utils';
import { buildDefaultParameters, coerceForSpec } from '@/lib/utils/protocolHelpers';
import { flattenInputParameters, iterateInputParameters } from '@/lib/utils/paramGroups';
import { validateParameter } from '@/lib/validation/parameter-validation';
import { IDENTIFIER_PATTERN, IDENTIFIER_ERROR_MESSAGE } from '@/lib/utils/identifier';
import type { TaskDefinition, Task } from '@/lib/types/api';
import type { TaskSpec, DeviceAssignment, ResourceAssignment, ParameterSpec } from '@/lib/types/protocol';
import type { LabSpec } from '@/lib/api/specs';

const taskFormSchema = z.object({
  name: z.string().min(1, 'Task name is required').regex(IDENTIFIER_PATTERN, IDENTIFIER_ERROR_MESSAGE),
  type: z.string().min(1, 'Task type is required'),
  priority: z.number().min(0),
  allocation_timeout: z.number().min(0),
  meta: z.string().optional(),
});

type TaskFormValues = z.infer<typeof taskFormSchema>;

interface SubmitTaskDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
  taskSpecs: Record<string, TaskSpec>;
  labSpecs: Record<string, LabSpec>;
  initialTask?: Task | null;
  generateCloneName: (name: string) => Promise<string>;
}

export function SubmitTaskDialog({
  open,
  onOpenChange,
  onSuccess,
  taskSpecs,
  labSpecs,
  initialTask,
  generateCloneName,
}: SubmitTaskDialogProps) {
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [taskTypes, setTaskTypes] = React.useState<ComboboxOption[]>([]);
  const [selectedTaskSpec, setSelectedTaskSpec] = React.useState<TaskSpec | null>(null);

  // Visual editor state
  const [devices, setDevices] = React.useState<Record<string, DeviceAssignment>>({});
  const [inputParameters, setInputParameters] = React.useState<Record<string, unknown>>({});
  const [inputResources, setInputResources] = React.useState<Record<string, ResourceAssignment>>({});
  const [inputSearch, setInputSearch] = React.useState('');

  // Track if we've already populated from initialTask to prevent re-population
  const populatedFromTaskRef = React.useRef<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
  } = useForm<TaskFormValues>({
    resolver: zodResolver(taskFormSchema),
    defaultValues: {
      name: '',
      type: '',
      priority: 0,
      allocation_timeout: 600,
      meta: '',
    },
  });

  const taskType = watch('type');
  const allLabNames = React.useMemo(() => Object.keys(labSpecs), [labSpecs]);

  // Fetch task types on mount
  React.useEffect(() => {
    getTaskPlugins()
      .then((plugins) => {
        const options: ComboboxOption[] = plugins.map((plugin) => ({
          value: plugin.type,
          label: plugin.type,
          description: plugin.description,
        }));
        setTaskTypes(options);
      })
      .catch((err) => {
        console.error('Failed to load task types:', err);
        setTaskTypes([]);
      });
  }, []);

  // Populate form when initialTask changes (for cloning)
  React.useEffect(() => {
    if (initialTask && populatedFromTaskRef.current !== initialTask.name) {
      // Mark that we've populated from this task
      populatedFromTaskRef.current = initialTask.name;

      // Populate form fields
      generateCloneName(initialTask.name).then((name) => setValue('name', name));
      setValue('type', initialTask.type);
      setValue('priority', initialTask.priority ?? 0);
      setValue('allocation_timeout', initialTask.allocation_timeout ?? 0);
      setValue(
        'meta',
        initialTask.meta && Object.keys(initialTask.meta).length > 0 ? JSON.stringify(initialTask.meta, null, 2) : ''
      );

      // Populate devices
      if (initialTask.devices && Object.keys(initialTask.devices).length > 0) {
        setDevices(initialTask.devices as unknown as Record<string, DeviceAssignment>);
      } else {
        setDevices({});
      }

      // Clone values win over spec defaults
      const cloneSpec = taskSpecs[initialTask.type];
      const specDefaults = cloneSpec ? buildDefaultParameters(cloneSpec) : {};
      setInputParameters({ ...specDefaults, ...(initialTask.input_parameters ?? {}) });

      // Populate resources
      if (initialTask.input_resources && Object.keys(initialTask.input_resources).length > 0) {
        setInputResources(initialTask.input_resources as Record<string, ResourceAssignment>);
      } else {
        setInputResources({});
      }
    }
  }, [initialTask, taskSpecs, generateCloneName, setValue]);

  // Load task spec when type changes
  React.useEffect(() => {
    if (taskType && taskSpecs[taskType]) {
      const spec = taskSpecs[taskType];
      setSelectedTaskSpec(spec);

      // Only initialize empty values if we don't have any existing values
      // (i.e., user just selected a new task type)
      const hasExistingDevices = Object.keys(devices).length > 0;
      const hasExistingParams = Object.keys(inputParameters).length > 0;
      const hasExistingResources = Object.keys(inputResources).length > 0;

      if (!hasExistingDevices && !hasExistingParams && !hasExistingResources) {
        // Initialize with empty static assignments
        if (spec.input_devices) {
          const initialDevices: Record<string, DeviceAssignment> = {};
          Object.keys(spec.input_devices).forEach((deviceName) => {
            initialDevices[deviceName] = { lab_name: '', name: '' };
          });
          setDevices(initialDevices);
        }

        if (spec.input_parameters) {
          const initialParams = buildDefaultParameters(spec);
          if (Object.keys(initialParams).length > 0) {
            setInputParameters(initialParams);
          }
        }

        if (spec.input_resources) {
          const initialResources: Record<string, ResourceAssignment> = {};
          Object.keys(spec.input_resources).forEach((resourceName) => {
            initialResources[resourceName] = '';
          });
          setInputResources(initialResources);
        }
      }
    } else {
      setSelectedTaskSpec(null);
    }
  }, [taskType, taskSpecs, devices, inputParameters, inputResources]);

  const handleClear = () => {
    reset({
      name: '',
      type: '',
      priority: 0,
      allocation_timeout: 600,
      meta: '',
    });
    setDevices({});
    setInputParameters({});
    setInputResources({});
    setSelectedTaskSpec(null);
    setError(null);
    populatedFromTaskRef.current = null; // Reset so we can clone again if needed
  };

  const onSubmit = async (data: TaskFormValues) => {
    setIsSubmitting(true);
    setError(null);

    try {
      const submittedDevices: Record<string, unknown> = {};
      let input_parameters: Record<string, unknown> | null = null;
      let input_resources: Record<string, unknown> | null = null;

      // Handle devices - serialize only devices defined in current task spec
      if (selectedTaskSpec?.input_devices) {
        Object.keys(selectedTaskSpec.input_devices).forEach((name) => {
          const assignment = devices[name];
          if (assignment !== undefined) {
            submittedDevices[name] = serializeDeviceAssignment(assignment);
          }
        });
      }

      // Validate and handle parameters (flatten groups; payload stays flat)
      if (selectedTaskSpec?.input_parameters) {
        const validationErrors: string[] = [];
        const filteredParams: Record<string, unknown> = {};

        Object.entries(flattenInputParameters(selectedTaskSpec.input_parameters)).forEach(([name, spec]) => {
          const coerced = coerceForSpec(inputParameters[name], spec);
          const result = validateParameter(coerced, spec);
          if (!result.valid) {
            validationErrors.push(`${name}: ${result.error}`);
          } else if (coerced !== undefined && coerced !== null && coerced !== '') {
            filteredParams[name] = coerced;
          }
        });

        if (validationErrors.length > 0) {
          setError(`Parameter validation failed:\n${validationErrors.join('\n')}`);
          setIsSubmitting(false);
          return;
        }

        input_parameters = Object.keys(filteredParams).length > 0 ? filteredParams : {};
      }

      // Handle resources - serialize only resources defined in current task spec
      // The API expects Resource objects ({name, type}), not plain strings
      if (selectedTaskSpec?.input_resources) {
        const serializedResources: Record<string, unknown> = {};
        Object.keys(selectedTaskSpec.input_resources).forEach((name) => {
          const assignment = inputResources[name];
          if (assignment !== undefined) {
            const serialized = serializeResourceAssignment(assignment);
            // Wrap plain string (static resource name) into a Resource object for the API
            serializedResources[name] = typeof serialized === 'string' ? { name: serialized, type: '' } : serialized;
          }
        });
        input_resources = Object.keys(serializedResources).length > 0 ? serializedResources : null;
      }

      // Parse metadata (always JSON)
      const meta = data.meta ? JSON.parse(data.meta) : {};

      const taskDefinition: TaskDefinition = {
        name: data.name,
        type: data.type,
        protocol_run_name: null,
        priority: data.priority,
        allocation_timeout: data.allocation_timeout,
        devices: submittedDevices as unknown as TaskDefinition['devices'],
        input_parameters,
        input_resources,
        meta,
      };

      const result = await submitTask(taskDefinition);

      if (result.success) {
        onOpenChange(false);
        onSuccess?.();
      } else {
        setError(result.error || 'Failed to submit task');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid input in one of the fields');
    } finally {
      setIsSubmitting(false);
    }
  };

  const searchLower = inputSearch.toLowerCase();
  const hasSpecInputs =
    selectedTaskSpec &&
    ((selectedTaskSpec.input_devices && Object.keys(selectedTaskSpec.input_devices).length > 0) ||
      (selectedTaskSpec.input_parameters && Object.keys(selectedTaskSpec.input_parameters).length > 0) ||
      (selectedTaskSpec.input_resources && Object.keys(selectedTaskSpec.input_resources).length > 0));

  const matchesSearch = (name: string, spec: { type?: string; desc?: string }) =>
    !searchLower ||
    name.toLowerCase().includes(searchLower) ||
    (spec.type && spec.type.toLowerCase().includes(searchLower)) ||
    (spec.desc && spec.desc.toLowerCase().includes(searchLower));

  return (
    <BaseSubmitDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Submit New Task"
      submitLabel="Submit Task"
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
      <div className="space-y-2">
        <Label htmlFor="name">Task Name *</Label>
        <Input id="name" {...register('name')} error={errors.name?.message} placeholder="my_task" />
      </div>

      <div className="space-y-2">
        <Label htmlFor="type">Task Type *</Label>
        <Combobox
          options={taskTypes}
          value={taskType}
          onChange={(value) => setValue('type', value, { shouldValidate: true })}
          placeholder="Select task type"
          searchPlaceholder="Search task types..."
          emptyText="No task types found"
        />
        {errors.type && <p className="text-sm text-red-600">{errors.type.message}</p>}
      </div>

      <div className="grid grid-cols-2 gap-4">
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
          <Label htmlFor="allocation_timeout">Allocation Timeout (seconds)</Label>
          <Input
            id="allocation_timeout"
            type="number"
            {...register('allocation_timeout', { valueAsNumber: true })}
            error={errors.allocation_timeout?.message}
          />
        </div>
      </div>

      {/* Search filter for spec-driven inputs */}
      {hasSpecInputs && (
        <>
          <div className="border-t border-gray-200 dark:border-slate-700" />
          <ParameterSearchInput value={inputSearch} onChange={setInputSearch} />
        </>
      )}

      {/* Devices Section */}
      {selectedTaskSpec?.input_devices &&
        Object.keys(selectedTaskSpec.input_devices).length > 0 &&
        (() => {
          const filtered = Object.entries(selectedTaskSpec.input_devices).filter(([name, spec]) =>
            matchesSearch(name, spec)
          );
          if (filtered.length === 0) return null;
          return (
            <div className="space-y-2">
              <Label>Input Devices *</Label>
              <div className="space-y-2.5">
                {filtered.map(([name, spec]) => (
                  <TaskDeviceAssignment
                    key={name}
                    deviceName={name}
                    deviceSpec={spec}
                    value={devices[name]}
                    onChange={(value) => setDevices({ ...devices, [name]: value })}
                    labSpecs={labSpecs}
                    selectedLabs={allLabNames}
                  />
                ))}
              </div>
            </div>
          );
        })()}

      {/* Parameters Section */}
      {selectedTaskSpec?.input_parameters &&
        Object.keys(selectedTaskSpec.input_parameters).length > 0 &&
        (() => {
          const filtered: Record<string, (typeof selectedTaskSpec.input_parameters)[string]> = {};
          for (const item of iterateInputParameters(selectedTaskSpec.input_parameters)) {
            if (item.kind === 'param') {
              if (matchesSearch(item.name, item.spec)) filtered[item.name] = item.spec;
            } else {
              const groupMatches = !searchLower || item.name.toLowerCase().includes(searchLower);
              const keptLeaves: Record<string, ParameterSpec> = {};
              for (const [leafName, leafSpec] of Object.entries(item.params)) {
                if (groupMatches || matchesSearch(leafName, leafSpec)) {
                  keptLeaves[leafName] = leafSpec;
                }
              }
              if (Object.keys(keptLeaves).length > 0) filtered[item.name] = keptLeaves;
            }
          }
          if (Object.keys(filtered).length === 0) return null;
          return (
            <div className="space-y-2">
              <Label>Input Parameters</Label>
              <TaskParameterFields
                parameters={filtered}
                values={inputParameters}
                onChange={(name, value) => setInputParameters({ ...inputParameters, [name]: value })}
              />
            </div>
          );
        })()}

      {/* Resources Section */}
      {selectedTaskSpec?.input_resources &&
        Object.keys(selectedTaskSpec.input_resources).length > 0 &&
        (() => {
          const filtered = Object.entries(selectedTaskSpec.input_resources).filter(([name, spec]) =>
            matchesSearch(name, spec)
          );
          if (filtered.length === 0) return null;
          return (
            <div className="space-y-2">
              <Label>Input Resources</Label>
              <div className="space-y-2.5">
                {filtered.map(([name, spec]) => (
                  <TaskResourceAssignment
                    key={name}
                    resourceName={name}
                    resourceSpec={spec}
                    value={inputResources[name]}
                    onChange={(value) => setInputResources({ ...inputResources, [name]: value })}
                    labSpecs={labSpecs}
                    selectedLabs={allLabNames}
                  />
                ))}
              </div>
            </div>
          );
        })()}

      {/* Metadata Section (always JSON) */}
      <div className="space-y-2">
        <Label htmlFor="meta">Metadata (JSON)</Label>
        <Textarea
          id="meta"
          {...register('meta')}
          error={errors.meta?.message}
          placeholder='{"description": "Test task"}'
        />
      </div>
    </BaseSubmitDialog>
  );
}
