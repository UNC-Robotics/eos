'use client';

import { memo } from 'react';
import { X, AlertTriangle } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import * as ScrollArea from '@radix-ui/react-scroll-area';
import type { DeviceAssignment, ParameterSpec, ResourceAssignment, TaskNode, TaskSpec } from '@/lib/types/protocol';
import type { LabSpec } from '@/lib/api/specs';
import { useEditorStore } from '@/lib/stores/editorStore';
import { ColorPicker } from './ColorPicker';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';
import { DeviceAssignment as DeviceAssignmentComponent } from './DeviceAssignment';
import { ResourceAssignment as ResourceAssignmentComponent } from './ResourceAssignment';
import { BooleanParameterField } from '@/features/tasks/components/parameter-fields/BooleanParameterField';
import { iterateInputParameters } from '@/lib/utils/paramGroups';
import { IDENTIFIER_ERROR_MESSAGE, isValidIdentifier } from '@/lib/utils/identifier';

interface TaskPropertiesPanelProps {
  isOpen: boolean;
  taskNode: TaskNode | null;
  taskSpec: TaskSpec | null;
  isMissingSpec?: boolean;
  labSpecs: Record<string, LabSpec>;
  selectedLabs: string[];
  onClose: () => void;
  onUpdate: (taskId: string, updates: Partial<TaskNode>) => void;
}

interface InputFieldProps {
  name: string;
  spec: ParameterSpec;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
}

const InputField = memo(({ name, spec, value, placeholder, onChange, onBlur }: InputFieldProps) => {
  const constraints =
    [
      spec.unit && `unit: ${spec.unit}`,
      typeof spec.min === 'number' && `min: ${spec.min}`,
      typeof spec.max === 'number' && `max: ${spec.max}`,
    ]
      .filter(Boolean)
      .join(', ') || undefined;

  return (
    <div>
      <label className="flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
        {name}
        <span className="px-1.5 py-0.5 rounded bg-gray-200 dark:bg-slate-600 text-[10px] font-medium text-gray-700 dark:text-gray-200">
          {spec.type}
        </span>
        {(spec.desc || constraints) && <DescriptionTooltip description={spec.desc} constraints={constraints} />}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={placeholder}
        className="w-full px-2.5 py-1.5 text-sm border border-gray-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-yellow-500 bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500"
      />
    </div>
  );
});

InputField.displayName = 'InputField';

interface OutputFieldProps {
  name: string;
  type: string;
  desc?: string;
}

const OutputField = memo(({ name, type, desc }: OutputFieldProps) => {
  return (
    <div className="bg-gray-50 dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-3 rounded-md">
      <div className="flex items-center gap-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">
        {name}
        <span className="px-1.5 py-0.5 rounded bg-gray-200 dark:bg-slate-600 text-[10px] font-medium text-gray-700 dark:text-gray-200">
          {type}
        </span>
      </div>
      {desc && <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{desc}</div>}
    </div>
  );
});

OutputField.displayName = 'OutputField';

function TaskValidationAlert({ taskName }: { taskName: string }) {
  const errors = useEditorStore((state) => state.taskValidationErrors[taskName]);
  if (!errors || errors.length === 0) return null;

  return (
    <div className="rounded-md bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 p-3">
      <div className="flex items-center gap-1.5 mb-1.5">
        <AlertTriangle className="w-3.5 h-3.5 text-red-600 dark:text-red-400" />
        <p className="text-xs font-medium text-red-800 dark:text-red-300">
          {errors.length} validation {errors.length === 1 ? 'error' : 'errors'}
        </p>
      </div>
      <ul className="space-y-1">
        {errors.map((error, i) => (
          <li key={i} className="text-xs text-red-700 dark:text-red-400 pl-1">
            - {error}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TaskPropertiesPanel({
  isOpen,
  taskNode,
  taskSpec,
  isMissingSpec,
  labSpecs,
  selectedLabs,
  onClose,
  onUpdate,
}: TaskPropertiesPanelProps) {
  const [localName, setLocalName] = useState('');
  const [showColorPicker, setShowColorPicker] = useState(false);
  const debounceTimerRef = useRef<number | null>(null);

  // Sync local name with taskNode name when taskNode changes
  useEffect(() => {
    if (taskNode) {
      setLocalName(taskNode.name);
    }
  }, [taskNode]);

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        window.clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  if (!isOpen || !taskNode || !taskSpec) return null;

  if (isMissingSpec) {
    return (
      <div className="h-full flex flex-col bg-white dark:bg-slate-900 border-l border-gray-200 dark:border-slate-700 min-w-0 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-slate-700">
          <h3 className="font-semibold text-gray-900 dark:text-white truncate">{taskNode.name}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-4">
          <div className="rounded-md bg-amber-50 dark:bg-amber-950/50 border border-amber-200 dark:border-amber-800 p-3">
            <p className="text-sm font-medium text-amber-800 dark:text-amber-300">Task spec not available</p>
            <p className="text-xs text-amber-700 dark:text-amber-400 mt-1">
              The spec for task type{' '}
              <code className="font-mono bg-amber-100 dark:bg-amber-900 px-1 rounded">{taskSpec.type}</code> was not
              found in the database. The package containing this task may not be loaded in the orchestrator.
            </p>
            <p className="text-xs text-amber-700 dark:text-amber-400 mt-2">
              Load the package in the Management page to restore full editing capabilities.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const nameError = localName === '' || isValidIdentifier(localName) ? null : IDENTIFIER_ERROR_MESSAGE;

  const handleNameChange = (newName: string) => {
    setLocalName(newName);

    if (debounceTimerRef.current) {
      window.clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = window.setTimeout(() => {
      if (newName !== taskNode.name && isValidIdentifier(newName)) {
        onUpdate(taskNode.name, { name: newName });
      }
    }, 500);
  };

  const handleNameBlur = () => {
    if (debounceTimerRef.current) {
      window.clearTimeout(debounceTimerRef.current);
    }

    if (localName !== taskNode.name && isValidIdentifier(localName)) {
      onUpdate(taskNode.name, { name: localName });
    }
  };

  const handleParameterChange = (paramName: string, value: string, _paramType: string) => {
    // Raw text stored as-is; coercion happens once at YAML serialization so partial input ("5.0", "5.", "-") survives.
    onUpdate(taskNode.name, {
      parameters: {
        ...taskNode.parameters,
        [paramName]: value,
      },
    });
  };

  const handleParameterClear = (paramName: string) => {
    if (!taskNode.parameters || !(paramName in taskNode.parameters)) return;
    const { [paramName]: _removed, ...rest } = taskNode.parameters;
    onUpdate(taskNode.name, { parameters: rest });
  };

  const handleDeviceChange = (deviceName: string, value: DeviceAssignment) => {
    onUpdate(taskNode.name, {
      devices: {
        ...taskNode.devices,
        [deviceName]: value,
      },
    });
  };

  const handleResourceChange = (resourceName: string, value: ResourceAssignment) => {
    onUpdate(taskNode.name, {
      resources: {
        ...taskNode.resources,
        [resourceName]: value,
      },
    });
  };

  const handleDeviceHoldChange = (deviceName: string, hold: boolean) => {
    const newHolds = { ...taskNode.device_holds };
    if (hold) {
      newHolds[deviceName] = true;
    } else {
      delete newHolds[deviceName];
    }
    onUpdate(taskNode.name, { device_holds: newHolds });
  };

  const handleResourceHoldChange = (resourceName: string, hold: boolean) => {
    const newHolds = { ...taskNode.resource_holds };
    if (hold) {
      newHolds[resourceName] = true;
    } else {
      delete newHolds[resourceName];
    }
    onUpdate(taskNode.name, { resource_holds: newHolds });
  };

  return (
    <div className="h-full flex flex-col bg-white dark:bg-slate-900 border-l border-gray-200 dark:border-slate-700 min-w-0 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-gray-200 dark:border-slate-700 flex items-center justify-between flex-shrink-0">
        <h2 className="text-base font-semibold text-gray-900 dark:text-white">Task Properties</h2>
        <button
          onClick={onClose}
          className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <ScrollArea.Root className="flex-1 min-h-0 min-w-0">
        <ScrollArea.Viewport className="w-full h-full" style={{ overflowX: 'hidden' }}>
          <div className="p-4 space-y-4 min-w-0">
            {/* Validation Errors */}
            <TaskValidationAlert taskName={taskNode.name} />

            {/* Basic Info */}
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">Name</label>
                <input
                  type="text"
                  value={localName}
                  onChange={(e) => handleNameChange(e.target.value)}
                  onBlur={handleNameBlur}
                  aria-invalid={nameError ? true : undefined}
                  className={`w-full px-2.5 py-1.5 text-sm border rounded-md focus:outline-none focus:ring-2 bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100 ${
                    nameError
                      ? 'border-red-400 dark:border-red-600 focus:ring-red-500'
                      : 'border-gray-300 dark:border-slate-600 focus:ring-blue-500 dark:focus:ring-yellow-500'
                  }`}
                />
                {nameError && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{nameError}</p>}
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">Type</label>
                <input
                  type="text"
                  value={taskSpec.type}
                  disabled
                  className="w-full px-2.5 py-1.5 text-sm border border-gray-300 dark:border-slate-600 rounded-md bg-gray-50 dark:bg-slate-800 text-gray-500 dark:text-gray-400"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">Description</label>
                <textarea
                  value={taskNode.desc || ''}
                  onChange={(e) => onUpdate(taskNode.name, { desc: e.target.value })}
                  rows={2}
                  className="w-full px-2.5 py-1.5 text-sm border border-gray-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-yellow-500 bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100"
                />
              </div>

              {/* Group */}
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Group (optional)
                </label>
                <input
                  type="text"
                  value={taskNode.group || ''}
                  onChange={(e) => onUpdate(taskNode.name, { group: e.target.value || undefined })}
                  placeholder="Group ID for back-to-back scheduling"
                  className="w-full px-2.5 py-1.5 text-sm border border-gray-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-yellow-500 bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500"
                />
              </div>

              {/* Duration */}
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Duration (optional)
                </label>
                <input
                  type="number"
                  value={taskNode.duration || ''}
                  onChange={(e) =>
                    onUpdate(taskNode.name, { duration: e.target.value ? Number(e.target.value) : undefined })
                  }
                  placeholder="Task duration in seconds"
                  className="w-full px-2.5 py-1.5 text-sm border border-gray-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-yellow-500 bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500"
                />
              </div>

              {/* Header Color */}
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Header Color
                </label>
                <div className="relative">
                  <button
                    onClick={() => setShowColorPicker(!showColorPicker)}
                    className="w-full px-2.5 py-1.5 border border-gray-300 dark:border-slate-600 rounded-md flex items-center gap-2 hover:border-gray-400 dark:hover:border-slate-500 transition-colors bg-white dark:bg-slate-700"
                  >
                    <div
                      className="w-5 h-5 rounded border border-gray-300 dark:border-slate-600"
                      style={{ backgroundColor: taskNode.color || '#3b82f6' }}
                    />
                    <span className="text-sm text-gray-700 dark:text-gray-300">{taskNode.color || '#3b82f6'}</span>
                  </button>
                  {showColorPicker && (
                    <div className="absolute top-full mt-2 left-0 z-50">
                      <ColorPicker
                        currentColor={taskNode.color || '#3b82f6'}
                        onColorSelect={(color) => {
                          onUpdate(taskNode.name, { color });
                          setShowColorPicker(false);
                        }}
                        onClose={() => setShowColorPicker(false)}
                      />
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Input Devices */}
            {taskSpec.input_devices && Object.keys(taskSpec.input_devices).length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Input Devices</h3>
                <div className="space-y-3">
                  {Object.entries(taskSpec.input_devices).map(([name, spec]) => (
                    <DeviceAssignmentComponent
                      key={name}
                      deviceName={name}
                      deviceSpec={spec}
                      value={taskNode.devices?.[name]}
                      onChange={(value) => handleDeviceChange(name, value)}
                      hold={taskNode.device_holds?.[name]}
                      onHoldChange={(hold) => handleDeviceHoldChange(name, hold)}
                      labSpecs={labSpecs}
                      selectedLabs={selectedLabs}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Input Resources */}
            {taskSpec.input_resources && Object.keys(taskSpec.input_resources).length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Input Resources</h3>
                <div className="space-y-3">
                  {Object.entries(taskSpec.input_resources).map(([name, spec]) => (
                    <ResourceAssignmentComponent
                      key={name}
                      resourceName={name}
                      resourceSpec={spec}
                      value={taskNode.resources?.[name]}
                      onChange={(value) => handleResourceChange(name, value)}
                      hold={taskNode.resource_holds?.[name]}
                      onHoldChange={(hold) => handleResourceHoldChange(name, hold)}
                      labSpecs={labSpecs}
                      selectedLabs={selectedLabs}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Input Parameters */}
            {taskSpec.input_parameters &&
              Object.keys(taskSpec.input_parameters).length > 0 &&
              (() => {
                const structure = iterateInputParameters(taskSpec.input_parameters);
                const renderParam = (name: string, spec: ParameterSpec) => {
                  // User override falls back to task.yml default; serializer strips equal-to-default values
                  const effectiveValue = taskNode.parameters?.[name] ?? spec.value;
                  return spec.type === 'bool' ? (
                    <BooleanParameterField
                      key={name}
                      name={name}
                      spec={spec}
                      value={effectiveValue}
                      onChange={(value) =>
                        onUpdate(taskNode.name, {
                          parameters: {
                            ...taskNode.parameters,
                            [name]: value as boolean,
                          },
                        })
                      }
                    />
                  ) : (
                    <InputField
                      key={name}
                      name={name}
                      spec={spec}
                      value={(() => {
                        if (effectiveValue == null) return '';
                        if (typeof effectiveValue === 'object') return JSON.stringify(effectiveValue);
                        return String(effectiveValue);
                      })()}
                      placeholder={spec.desc ?? ''}
                      onChange={(value) => handleParameterChange(name, value, spec.type)}
                      onBlur={() => {
                        const v = taskNode.parameters?.[name];
                        const isEmpty = v === undefined || v === null || v === '';
                        if (isEmpty) handleParameterClear(name);
                      }}
                    />
                  );
                };

                // Required/optional split applies only to top-level leaves. Group children keep author order.
                const topLevel = structure.filter((item) => item.kind === 'param') as Array<{
                  kind: 'param';
                  name: string;
                  spec: ParameterSpec;
                }>;
                const groups = structure.filter((item) => item.kind === 'group') as Array<{
                  kind: 'group';
                  name: string;
                  params: Record<string, ParameterSpec>;
                }>;
                const topRequired = topLevel.filter(({ spec }) => spec.value === undefined);
                const topOptional = topLevel.filter(({ spec }) => spec.value !== undefined);

                return (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Input Parameters</h3>
                    <div className="space-y-4">
                      {topRequired.map(({ name, spec }) => renderParam(name, spec))}
                      {topOptional.length > 0 && topRequired.length > 0 && (
                        <div className="text-xs text-gray-400 dark:text-gray-500 pt-1">Optional</div>
                      )}
                      {topOptional.map(({ name, spec }) => renderParam(name, spec))}
                      {groups.map((group) => (
                        <div key={`group-${group.name}`} className="space-y-2 pt-1">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold uppercase tracking-wide text-black dark:text-white whitespace-nowrap">
                              {group.name}
                            </span>
                            <div className="flex-1 h-px bg-gray-200 dark:bg-slate-700" />
                          </div>
                          <div className="space-y-4">
                            {Object.entries(group.params).map(([name, spec]) => renderParam(name, spec))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}

            {/* Output Devices */}
            {taskSpec.output_devices && Object.keys(taskSpec.output_devices).length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Output Devices</h3>
                <div className="space-y-2">
                  {Object.entries(taskSpec.output_devices).map(([name, spec]) => (
                    <OutputField key={name} name={name} type={spec.type} desc={spec.desc} />
                  ))}
                </div>
              </div>
            )}

            {/* Output Resources */}
            {taskSpec.output_resources && Object.keys(taskSpec.output_resources).length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Output Resources</h3>
                <div className="space-y-2">
                  {Object.entries(taskSpec.output_resources).map(([name, spec]) => (
                    <OutputField key={name} name={name} type={spec.type} desc={spec.desc} />
                  ))}
                </div>
              </div>
            )}

            {/* Output Parameters */}
            {taskSpec.output_parameters && Object.keys(taskSpec.output_parameters).length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Output Parameters</h3>
                <div className="space-y-2">
                  {Object.entries(taskSpec.output_parameters).map(([name, spec]) => (
                    <OutputField key={name} name={name} type={spec.type} desc={spec.desc} />
                  ))}
                </div>
              </div>
            )}
          </div>
        </ScrollArea.Viewport>
        <ScrollArea.Scrollbar
          className="flex select-none touch-none p-0.5 bg-gray-100 dark:bg-slate-800 transition-colors duration-150 ease-out hover:bg-gray-200 dark:hover:bg-slate-700"
          orientation="vertical"
        >
          <ScrollArea.Thumb className="flex-1 bg-gray-400 dark:bg-slate-600 rounded-full relative before:content-[''] before:absolute before:top-1/2 before:left-1/2 before:-translate-x-1/2 before:-translate-y-1/2 before:w-full before:h-full before:min-w-[44px] before:min-h-[44px]" />
        </ScrollArea.Scrollbar>
      </ScrollArea.Root>
    </div>
  );
}
