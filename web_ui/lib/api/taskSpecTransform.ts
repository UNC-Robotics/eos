import type { TaskSpec as DbTaskSpec } from '@/lib/api/specs';
import type { TaskSpec, ParameterSpec, FileSpec } from '@/lib/types/protocol';

/**
 * Transform a DB-layer TaskSpec into the editor-layer TaskSpec.
 * Single source of truth: every task-spec consumer must use it so they never drift.
 */
export function transformTaskSpec(type: string, spec: DbTaskSpec & { packageName: string }): TaskSpec {
  const deviceTypes = spec.devices ? Array.from(new Set(Object.values(spec.devices).map((d) => d.type))) : [];

  const inputDevices = spec.devices
    ? Object.fromEntries(Object.entries(spec.devices).map(([key, device]) => [key, { type: device.type, desc: '' }]))
    : undefined;

  const inputResources = spec.input_resources
    ? Object.fromEntries(
        Object.entries(spec.input_resources).map(([key, resource]) => [key, { type: resource.type, desc: '' }])
      )
    : {};

  const outputResources = spec.output_resources
    ? Object.fromEntries(
        Object.entries(spec.output_resources).map(([key, resource]) => [key, { type: resource.type, desc: '' }])
      )
    : {};

  const toFileSpecs = (files?: Record<string, { desc?: string }>): Record<string, FileSpec> =>
    files ? Object.fromEntries(Object.entries(files).map(([key, file]) => [key, { desc: file.desc || '' }])) : {};

  return {
    type,
    desc: spec.desc || '',
    device_types: deviceTypes,
    packageName: spec.packageName,
    input_devices: inputDevices,
    output_devices: {},
    input_resources: inputResources,
    output_resources: outputResources,
    input_parameters: (spec.input_parameters as Record<string, ParameterSpec>) || {},
    output_parameters: (spec.output_parameters as Record<string, ParameterSpec>) || {},
    input_files: toFileSpecs(spec.input_files),
    output_files: toFileSpecs(spec.output_files),
  };
}
