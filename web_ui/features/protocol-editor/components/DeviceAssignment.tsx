'use client';

import { useState, useMemo, useCallback, useEffect } from 'react';
import type { DeviceAssignment as DeviceAssignmentType, DeviceSpec, DeviceIdentifier } from '@/lib/types/protocol';
import type { LabSpec } from '@/lib/api/specs';
import {
  getDeviceAssignmentMode,
  getDevicesByLab,
  isDynamicDeviceAssignment,
  isStaticDeviceAssignment,
} from '@/lib/utils/assignment-utils';
import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';
import { AssignmentModeSelector } from './AssignmentModeSelector';
import { ConstraintSection } from '@/components/ui/ConstraintSection';
import { toggleInArray } from '@/lib/utils/array';

interface DeviceAssignmentProps {
  deviceName: string;
  deviceSpec: DeviceSpec;
  value: DeviceAssignmentType | undefined;
  onChange: (value: DeviceAssignmentType) => void;
  labSpecs: Record<string, LabSpec>;
  selectedLabs: string[];
  enableReferenceMode?: boolean;
  hold?: boolean;
  onHoldChange?: (hold: boolean) => void;
}

export function DeviceAssignment({
  deviceName,
  deviceSpec,
  value,
  onChange,
  labSpecs,
  selectedLabs,
  enableReferenceMode = true,
  hold,
  onHoldChange,
}: DeviceAssignmentProps) {
  const [selectedMode, setSelectedMode] = useState(() => {
    const mode = getDeviceAssignmentMode(value);
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
    } else if (typeof value === 'object' && value && 'lab_name' in value && (value.lab_name || value.name)) {
      // It's static with actual values
      setSelectedMode('static');
    }
    // Don't update for empty string or empty static object - let user's selection persist
  }, [value, enableReferenceMode]);

  const handleModeChange = useCallback(
    (newMode: 'static' | 'dynamic' | 'reference') => {
      setSelectedMode(newMode);
      onChange(
        newMode === 'static'
          ? { lab_name: '', name: '' }
          : newMode === 'dynamic'
            ? { allocation_type: 'dynamic', device_type: deviceSpec.type }
            : ''
      );
    },
    [deviceSpec.type, onChange]
  );

  return (
    <div className="border border-gray-200 dark:border-slate-600 rounded-md px-3 py-2 space-y-1.5 bg-white dark:bg-slate-800">
      <div className="flex items-center justify-between gap-2 min-w-0">
        <label className="shrink min-w-0 text-sm font-medium text-gray-700 dark:text-white truncate">
          {deviceName} <span className="text-xs text-gray-400 dark:text-gray-500">({deviceSpec.type})</span>
          {deviceSpec.desc && <DescriptionTooltip description={deviceSpec.desc} />}
        </label>

        {enableReferenceMode ? (
          <AssignmentModeSelector mode={selectedMode} onChange={handleModeChange} color="blue" />
        ) : (
          <div className="flex gap-1 min-w-0 shrink-0">
            {(['static', 'dynamic'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => handleModeChange(mode)}
                className={`px-1.5 py-1.5 text-xs font-medium rounded-md transition-colors capitalize ${
                  selectedMode === mode
                    ? 'bg-blue-600 dark:bg-yellow-500 text-white dark:text-slate-900'
                    : 'bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-slate-600'
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedMode === 'static' && (
        <StaticMode
          value={value}
          onChange={onChange}
          deviceSpec={deviceSpec}
          labSpecs={labSpecs}
          selectedLabs={selectedLabs}
        />
      )}
      {selectedMode === 'dynamic' && (
        <DynamicMode
          value={value}
          onChange={onChange}
          deviceSpec={deviceSpec}
          labSpecs={labSpecs}
          selectedLabs={selectedLabs}
        />
      )}
      {selectedMode === 'reference' && enableReferenceMode && <ReferenceMode value={value} onChange={onChange} />}

      {onHoldChange && (
        <label className="flex items-center gap-2 pt-2 border-t border-gray-100 dark:border-slate-700 cursor-pointer">
          <input
            type="checkbox"
            checked={hold ?? false}
            onChange={(e) => onHoldChange(e.target.checked)}
            className="h-4 w-4 rounded border-gray-300 dark:border-slate-500"
          />
          <span
            className="text-sm text-gray-700 dark:text-gray-300"
            title="Prevent this device from being released until successor tasks complete"
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
  deviceSpec,
  labSpecs,
  selectedLabs,
}: Omit<DeviceAssignmentProps, 'deviceName'>) {
  const staticValue = value && isStaticDeviceAssignment(value) ? value : { lab_name: '', name: '' };

  const labOptions = useMemo(
    () => selectedLabs.map((lab) => ({ value: lab, label: lab, description: labSpecs[lab]?.desc })),
    [selectedLabs, labSpecs]
  );

  const deviceOptions = useMemo(
    () =>
      staticValue.lab_name
        ? getDevicesByLab(labSpecs, staticValue.lab_name, deviceSpec.type).map((d) => ({
            value: d.name,
            label: d.name,
            description: d.desc,
          }))
        : [],
    [staticValue.lab_name, labSpecs, deviceSpec.type]
  );

  return (
    <div className="grid grid-cols-2 gap-2">
      <div>
        <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Lab</label>
        <Combobox
          options={labOptions}
          value={staticValue.lab_name}
          onChange={(lab) => onChange({ lab_name: lab, name: '' })}
          placeholder="Select lab..."
          emptyText="No labs available"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Device</label>
        <Combobox
          options={deviceOptions}
          value={staticValue.name}
          onChange={(name) => onChange({ ...staticValue, name })}
          placeholder={staticValue.lab_name ? 'Select device...' : 'Select lab first'}
          emptyText={`No ${deviceSpec.type} devices in this lab`}
          disabled={!staticValue.lab_name}
        />
      </div>
    </div>
  );
}

function DynamicMode({
  value,
  onChange,
  deviceSpec,
  labSpecs,
  selectedLabs,
}: Omit<DeviceAssignmentProps, 'deviceName'>) {
  const dynamicValue = useMemo(
    () =>
      value && isDynamicDeviceAssignment(value)
        ? value
        : { allocation_type: 'dynamic' as const, device_type: deviceSpec.type },
    [value, deviceSpec.type]
  );
  const [constrainLabs, setConstrainLabs] = useState(!!dynamicValue.allowed_labs);
  const [constrainDevices, setConstrainDevices] = useState(!!dynamicValue.allowed_devices);

  const updateConstraint = useCallback(
    (field: 'allowed_labs' | 'allowed_devices', enabled: boolean) => {
      const updated = { ...dynamicValue };
      if (enabled) updated[field] = field === 'allowed_labs' ? [] : [];
      else delete updated[field];
      onChange(updated);
    },
    [dynamicValue, onChange]
  );

  const labOptions = useMemo(
    () =>
      selectedLabs
        .filter((lab) => !dynamicValue.allowed_labs?.includes(lab))
        .map((lab) => ({ value: lab, label: lab, description: labSpecs[lab]?.desc })),
    [selectedLabs, dynamicValue.allowed_labs, labSpecs]
  );

  const deviceOptions = useMemo(() => {
    const devices: ComboboxOption[] = [];
    selectedLabs.forEach((labName) => {
      const labDevices = getDevicesByLab(labSpecs, labName, deviceSpec.type);
      labDevices.forEach((d) => {
        if (!dynamicValue.allowed_devices?.some((ad) => ad.lab_name === labName && ad.name === d.name)) {
          devices.push({ value: `${labName}.${d.name}`, label: `${d.name} (${labName})`, description: d.desc });
        }
      });
    });
    return devices;
  }, [selectedLabs, labSpecs, deviceSpec.type, dynamicValue.allowed_devices]);

  const compareDevices = useCallback(
    (a: DeviceIdentifier, b: DeviceIdentifier) => a.lab_name === b.lab_name && a.name === b.name,
    []
  );

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 bg-gray-50 dark:bg-slate-700 px-2.5 py-1.5 rounded-md">
        <span className="text-xs font-medium text-gray-700 dark:text-gray-300">Device Type:</span>
        <span className="text-sm text-gray-900 dark:text-white">{deviceSpec.type}</span>
      </div>

      <ConstraintSection
        label="Constrain to specific labs"
        enabled={constrainLabs}
        onToggle={(enabled) => {
          setConstrainLabs(enabled);
          updateConstraint('allowed_labs', enabled);
        }}
        items={dynamicValue.allowed_labs || []}
        onAdd={(lab) => onChange({ ...dynamicValue, allowed_labs: toggleInArray(dynamicValue.allowed_labs, lab) })}
        onRemove={(lab) => onChange({ ...dynamicValue, allowed_labs: toggleInArray(dynamicValue.allowed_labs, lab) })}
        options={labOptions}
        placeholder="Add lab..."
        emptyText="All labs added"
        renderItem={(item) => item}
        getKey={(item) => item}
        color="blue"
      />

      <ConstraintSection
        label="Constrain to specific devices"
        enabled={constrainDevices}
        onToggle={(enabled) => {
          setConstrainDevices(enabled);
          updateConstraint('allowed_devices', enabled);
        }}
        items={dynamicValue.allowed_devices || []}
        onAdd={(value) => {
          const [lab, name] = value.split('.');
          onChange({
            ...dynamicValue,
            allowed_devices: toggleInArray(dynamicValue.allowed_devices, { lab_name: lab, name }, compareDevices),
          });
        }}
        onRemove={(device) =>
          onChange({
            ...dynamicValue,
            allowed_devices: toggleInArray(dynamicValue.allowed_devices, device, compareDevices),
          })
        }
        options={deviceOptions}
        placeholder="Add device..."
        emptyText="All devices added"
        renderItem={(d: DeviceIdentifier) => `${d.name} (${d.lab_name})`}
        getKey={(d: DeviceIdentifier) => `${d.lab_name}.${d.name}`}
        color="green"
      />
    </div>
  );
}

function ReferenceMode({ value, onChange }: Pick<DeviceAssignmentProps, 'value' | 'onChange'>) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Task Reference</label>
      <input
        type="text"
        value={typeof value === 'string' ? value : ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder="task_name.device_output_name"
        className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-yellow-500 bg-white dark:bg-slate-700 text-gray-900 dark:text-gray-100"
      />
    </div>
  );
}
