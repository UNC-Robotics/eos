import type {
  DeviceAssignment,
  ResourceAssignment,
  StaticDeviceAssignment,
  DynamicDeviceAssignment,
  DynamicResourceAssignment,
  DeviceSpec,
  ResourceSpec,
  DeviceIdentifier,
} from '@/lib/types/experiment';
import type { LabSpec } from '@/lib/api/specs';

// Type Guards
export const isStaticDeviceAssignment = (v: DeviceAssignment): v is StaticDeviceAssignment =>
  typeof v === 'object' && v !== null && 'lab_name' in v && 'name' in v && !('allocation_type' in v);

export const isDynamicDeviceAssignment = (v: DeviceAssignment): v is DynamicDeviceAssignment =>
  typeof v === 'object' &&
  v !== null &&
  'allocation_type' in v &&
  v.allocation_type === 'dynamic' &&
  'device_type' in v;

export const isTaskReferenceAssignment = (v: DeviceAssignment | ResourceAssignment): v is string =>
  typeof v === 'string' && v.includes('.');

export const isDynamicResourceAssignment = (v: ResourceAssignment): v is DynamicResourceAssignment =>
  typeof v === 'object' &&
  v !== null &&
  'allocation_type' in v &&
  v.allocation_type === 'dynamic' &&
  'resource_type' in v;

export const isStaticResourceAssignment = (v: ResourceAssignment): v is string =>
  typeof v === 'string' && !v.includes('.');

// Mode Detection
export type AssignmentMode = 'static' | 'dynamic' | 'reference';

export const getDeviceAssignmentMode = (v: DeviceAssignment | undefined): AssignmentMode =>
  !v ? 'static' : isDynamicDeviceAssignment(v) ? 'dynamic' : isTaskReferenceAssignment(v) ? 'reference' : 'static';

export const getResourceAssignmentMode = (v: ResourceAssignment | undefined): AssignmentMode =>
  !v ? 'static' : isDynamicResourceAssignment(v) ? 'dynamic' : isTaskReferenceAssignment(v) ? 'reference' : 'static';

// Filtering
export const getDevicesByLab = (labSpecs: Record<string, LabSpec>, labName: string, deviceType?: string) => {
  const lab = labSpecs[labName];
  if (!lab?.devices) return [];

  return Object.entries(lab.devices)
    .filter(([_, config]) => !deviceType || config.type === deviceType)
    .map(([name, config]) => ({ name, type: config.type, desc: config.desc }))
    .sort((a, b) => a.name.localeCompare(b.name));
};

export const getAvailableResources = (
  labSpecs: Record<string, LabSpec>,
  selectedLabs: string[],
  resourceType?: string
) => {
  const resources: Array<{ resourceName: string; resourceType: string; labName?: string }> = [];

  selectedLabs.forEach((labName) => {
    const lab = labSpecs[labName];
    if (!lab?.resources) return;

    Object.entries(lab.resources).forEach(([resourceName, config]) => {
      if (!resourceType || config.type === resourceType) {
        resources.push({ resourceName, resourceType: config.type, labName });
      }
    });
  });

  return resources.sort((a, b) => a.resourceName.localeCompare(b.resourceName));
};

// Validation
export interface ValidationResult {
  valid: boolean;
  error?: string;
}

const validateTaskReference = (ref: string): ValidationResult => {
  const parts = ref.split('.');
  return parts.length === 2 && parts[0] && parts[1]
    ? { valid: true }
    : { valid: false, error: 'Invalid format. Use: task_name.output_name' };
};

const checkLabExists = (
  labName: string,
  selectedLabs: string[],
  labSpecs: Record<string, LabSpec>
): ValidationResult => {
  if (!selectedLabs.includes(labName)) return { valid: false, error: `Lab "${labName}" not selected in experiment` };
  if (!labSpecs[labName]) return { valid: false, error: `Lab "${labName}" not found` };
  return { valid: true };
};

export const validateDeviceAssignment = (
  assignment: DeviceAssignment | undefined,
  deviceSpec: DeviceSpec,
  labSpecs: Record<string, LabSpec>,
  selectedLabs: string[]
): ValidationResult => {
  if (!assignment) return { valid: false, error: 'Device assignment required' };

  if (isTaskReferenceAssignment(assignment)) return validateTaskReference(assignment);

  if (isStaticDeviceAssignment(assignment)) {
    const { lab_name, name } = assignment;
    if (!lab_name || !name) return { valid: false, error: 'Lab and device name required' };

    const labCheck = checkLabExists(lab_name, selectedLabs, labSpecs);
    if (!labCheck.valid) return labCheck;

    const device = labSpecs[lab_name].devices?.[name];
    if (!device) return { valid: false, error: `Device "${name}" not found in lab "${lab_name}"` };
    if (device.type !== deviceSpec.type)
      return { valid: false, error: `Type mismatch: expected "${deviceSpec.type}", got "${device.type}"` };

    return { valid: true };
  }

  if (isDynamicDeviceAssignment(assignment)) {
    const { device_type, allowed_labs, allowed_devices } = assignment;

    if (device_type !== deviceSpec.type)
      return { valid: false, error: `Type mismatch: expected "${deviceSpec.type}", got "${device_type}"` };

    if (allowed_labs) {
      for (const lab of allowed_labs) {
        const check = checkLabExists(lab, selectedLabs, labSpecs);
        if (!check.valid) return check;
      }
    }

    if (allowed_devices) {
      for (const { lab_name, name } of allowed_devices) {
        if (!labSpecs[lab_name]) return { valid: false, error: `Lab "${lab_name}" not found` };
        const device = labSpecs[lab_name].devices?.[name];
        if (!device) return { valid: false, error: `Device "${name}" not found in lab "${lab_name}"` };
        if (device.type !== device_type)
          return {
            valid: false,
            error: `Device "${name}" has wrong type: expected "${device_type}", got "${device.type}"`,
          };
      }
    }

    return { valid: true };
  }

  return { valid: false, error: 'Invalid device assignment format' };
};

export const validateResourceAssignment = (
  assignment: ResourceAssignment | undefined,
  resourceSpec: ResourceSpec,
  labSpecs: Record<string, LabSpec>,
  selectedLabs: string[]
): ValidationResult => {
  if (!assignment) return { valid: false, error: 'Resource assignment required' };

  if (isTaskReferenceAssignment(assignment)) return validateTaskReference(assignment);

  if (isDynamicResourceAssignment(assignment)) {
    const { resource_type } = assignment;
    return resource_type === resourceSpec.type
      ? { valid: true }
      : { valid: false, error: `Type mismatch: expected "${resourceSpec.type}", got "${resource_type}"` };
  }

  if (isStaticResourceAssignment(assignment)) {
    const resourceName = assignment as string;
    if (!resourceName.trim()) return { valid: false, error: 'Resource name cannot be empty' };

    for (const labName of selectedLabs) {
      const resource = labSpecs[labName]?.resources?.[resourceName];
      if (resource) {
        return resource.type === resourceSpec.type
          ? { valid: true }
          : { valid: false, error: `Type mismatch: expected "${resourceSpec.type}", got "${resource.type}"` };
      }
    }

    return { valid: false, error: `Resource "${resourceName}" not found in selected labs` };
  }

  return { valid: false, error: 'Invalid resource assignment format' };
};

// Serialization
type SerializedDeviceAssignment =
  | string
  | { ref: string; hold: boolean }
  | { lab_name: string; name: string; hold?: boolean }
  | {
      allocation_type: 'dynamic';
      device_type: string;
      allowed_labs?: string[];
      allowed_devices?: DeviceIdentifier[];
      hold?: boolean;
    };

export const serializeDeviceAssignment = (assignment: DeviceAssignment, hold?: boolean): SerializedDeviceAssignment => {
  if (isTaskReferenceAssignment(assignment)) {
    return hold ? { ref: assignment, hold: true } : assignment;
  }
  if (isStaticDeviceAssignment(assignment)) {
    const base = { lab_name: assignment.lab_name, name: assignment.name };
    return hold ? { ...base, hold: true } : base;
  }
  if (isDynamicDeviceAssignment(assignment)) {
    const base = {
      allocation_type: 'dynamic' as const,
      device_type: assignment.device_type,
      ...(assignment.allowed_labs?.length && { allowed_labs: assignment.allowed_labs }),
      ...(assignment.allowed_devices?.length && { allowed_devices: assignment.allowed_devices }),
    };
    return hold ? { ...base, hold: true } : base;
  }
  return assignment;
};

type SerializedResourceAssignment =
  | string
  | { ref: string; hold: boolean }
  | { allocation_type: 'dynamic'; resource_type: string; hold?: boolean };

export const serializeResourceAssignment = (
  assignment: ResourceAssignment,
  hold?: boolean
): SerializedResourceAssignment => {
  if (isTaskReferenceAssignment(assignment)) {
    return hold ? { ref: assignment, hold: true } : assignment;
  }
  if (isDynamicResourceAssignment(assignment)) {
    const base = { allocation_type: 'dynamic' as const, resource_type: assignment.resource_type };
    return hold ? { ...base, hold: true } : base;
  }
  // Static resource (plain string) — backend has no hold support for static resources
  return assignment;
};
