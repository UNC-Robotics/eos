'use client';

import { useState, useMemo, useCallback, useEffect } from 'react';
import type { ResourceAssignment as ResourceAssignmentType, ResourceSpec } from '@/lib/types/experiment';
import type { LabSpec } from '@/lib/api/specs';
import {
  getResourceAssignmentMode,
  getAvailableResources,
  isStaticResourceAssignment,
} from '@/lib/utils/assignment-utils';
import { Combobox } from '@/components/ui/Combobox';
import { AssignmentModeSelector } from './AssignmentModeSelector';

interface ResourceAssignmentProps {
  resourceName: string;
  resourceSpec: ResourceSpec;
  value: ResourceAssignmentType | undefined;
  onChange: (value: ResourceAssignmentType) => void;
  labSpecs: Record<string, LabSpec>;
  selectedLabs: string[];
  enableReferenceMode?: boolean;
  hold?: boolean;
  onHoldChange?: (hold: boolean) => void;
}

export function ResourceAssignment({
  resourceName,
  resourceSpec,
  value,
  onChange,
  labSpecs,
  selectedLabs,
  enableReferenceMode = true,
  hold,
  onHoldChange,
}: ResourceAssignmentProps) {
  const [selectedMode, setSelectedMode] = useState(() => {
    const mode = getResourceAssignmentMode(value);
    // If reference mode is disabled and value is reference, default to static
    if (!enableReferenceMode && mode === 'reference') {
      return 'static';
    }
    return mode;
  });

  // Sync selectedMode when value changes externally (e.g., from connections)
  useEffect(() => {
    // Only update if the mode actually changed from what we expect
    // This prevents fighting with user interactions
    if (typeof value === 'string' && value.includes('.') && enableReferenceMode) {
      // It's a valid reference (only if reference mode is enabled)
      setSelectedMode('reference');
    } else if (typeof value === 'object' && value && 'allocation_type' in value) {
      // It's dynamic
      setSelectedMode('dynamic');
    } else if (typeof value === 'string' && value && !value.includes('.')) {
      // It's static with actual value
      setSelectedMode('static');
    }
    // Don't update for empty string - let user's selection persist
  }, [value, enableReferenceMode]);

  const handleModeChange = useCallback(
    (newMode: 'static' | 'dynamic' | 'reference') => {
      setSelectedMode(newMode);
      onChange(
        newMode === 'static'
          ? ''
          : newMode === 'dynamic'
            ? { allocation_type: 'dynamic', resource_type: resourceSpec.type }
            : ''
      );
    },
    [resourceSpec.type, onChange]
  );

  return (
    <div className="border border-gray-200 dark:border-slate-600 rounded-md p-3 space-y-2.5 bg-white dark:bg-slate-800">
      <div>
        <label className="block text-xs font-medium text-gray-700 dark:text-white mb-1">
          {resourceName} <span className="text-xs text-gray-400 dark:text-gray-500">({resourceSpec.type})</span>
        </label>
        {resourceSpec.desc && <p className="text-xs text-gray-500 dark:text-gray-400">{resourceSpec.desc}</p>}
      </div>

      {enableReferenceMode ? (
        <AssignmentModeSelector mode={selectedMode} onChange={handleModeChange} color="green" />
      ) : (
        <div className="flex gap-2">
          {(['static', 'dynamic'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => handleModeChange(mode)}
              className={`flex-1 px-3 py-2 text-xs font-medium rounded-md transition-colors capitalize ${
                selectedMode === mode
                  ? 'bg-green-600 dark:bg-yellow-500 text-white dark:text-slate-900'
                  : 'bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-slate-600'
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
      )}

      {selectedMode === 'static' && (
        <StaticMode
          value={value}
          onChange={onChange}
          resourceSpec={resourceSpec}
          labSpecs={labSpecs}
          selectedLabs={selectedLabs}
        />
      )}
      {selectedMode === 'dynamic' && <DynamicMode resourceSpec={resourceSpec} />}
      {selectedMode === 'reference' && enableReferenceMode && <ReferenceMode value={value} onChange={onChange} />}

      {onHoldChange && selectedMode !== 'static' && (
        <label className="flex items-center gap-2 pt-1.5 border-t border-gray-100 dark:border-slate-700 cursor-pointer">
          <input
            type="checkbox"
            checked={hold ?? false}
            onChange={(e) => onHoldChange(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-gray-300 dark:border-slate-500"
          />
          <span
            className="text-xs text-gray-600 dark:text-gray-400"
            title="Prevent this resource from being released until successor tasks complete"
          >
            Hold for successors
          </span>
        </label>
      )}
    </div>
  );
}

function StaticMode({
  value,
  onChange,
  resourceSpec,
  labSpecs,
  selectedLabs,
}: Omit<ResourceAssignmentProps, 'resourceName'>) {
  const resourceOptions = useMemo(
    () =>
      getAvailableResources(labSpecs, selectedLabs, resourceSpec.type).map((r) => ({
        value: r.resourceName,
        label: r.resourceName,
        description: r.labName ? `Lab: ${r.labName}` : undefined,
      })),
    [labSpecs, selectedLabs, resourceSpec.type]
  );

  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Resource</label>
      <Combobox
        options={resourceOptions}
        value={value && isStaticResourceAssignment(value) ? value : ''}
        onChange={onChange}
        placeholder="Select or type resource name..."
        emptyText={`No ${resourceSpec.type} resources in selected labs`}
      />
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
        Select from available resources or type a custom resource name
      </p>
    </div>
  );
}

function DynamicMode({ resourceSpec }: Pick<ResourceAssignmentProps, 'resourceSpec'>) {
  return (
    <div className="bg-gray-50 dark:bg-slate-700 p-2.5 rounded-md">
      <div className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-0.5">Dynamic Allocation</div>
      <div className="text-sm text-gray-900 dark:text-white">Resource Type: {resourceSpec.type}</div>
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">
        Resource will be dynamically allocated at runtime based on availability
      </p>
    </div>
  );
}

function ReferenceMode({ value, onChange }: Pick<ResourceAssignmentProps, 'value' | 'onChange'>) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Task Reference</label>
      <input
        type="text"
        value={typeof value === 'string' ? value : ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder="task_name.resource_output_name"
        className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 dark:focus:ring-green-500 bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100"
      />
    </div>
  );
}
