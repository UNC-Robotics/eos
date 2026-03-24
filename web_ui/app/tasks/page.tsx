import { getTasks } from '@/features/tasks/api/tasks';
import { TasksTable } from '@/features/tasks/components/TasksTable';
import { getTaskSpecs, getLabSpecs } from '@/lib/api/specs';
import type { TaskSpec, ParameterSpec } from '@/lib/types/experiment';

export default async function TasksPage() {
  const [initialData, rawTaskSpecs, labSpecs] = await Promise.all([
    getTasks(),
    getTaskSpecs(),
    getLabSpecs(true), // Only loaded labs
  ]);

  // Transform task specs to match experiment editor format
  const taskSpecs: Record<string, TaskSpec> = Object.fromEntries(
    Object.entries(rawTaskSpecs).map(([type, spec]) => {
      // Extract unique device types from the devices record
      const deviceTypes = spec.devices ? Array.from(new Set(Object.values(spec.devices).map((d) => d.type))) : [];

      // Transform devices to match DeviceSpec format (add desc field)
      const transformedDevices = spec.devices
        ? Object.fromEntries(
            Object.entries(spec.devices).map(([key, device]) => [key, { type: device.type, desc: '' }])
          )
        : undefined;

      // Transform resources to match ResourceSpec format (add desc field)
      const transformedInputResources = spec.input_resources
        ? Object.fromEntries(
            Object.entries(spec.input_resources).map(([key, resource]) => [key, { type: resource.type, desc: '' }])
          )
        : {};

      const transformedOutputResources = spec.output_resources
        ? Object.fromEntries(
            Object.entries(spec.output_resources).map(([key, resource]) => [key, { type: resource.type, desc: '' }])
          )
        : {};

      return [
        type,
        {
          type,
          desc: spec.desc || '',
          device_types: deviceTypes,
          input_devices: transformedDevices,
          output_devices: {},
          input_resources: transformedInputResources,
          output_resources: transformedOutputResources,
          input_parameters: (spec.input_parameters as Record<string, ParameterSpec>) || {},
          output_parameters: (spec.output_parameters as Record<string, ParameterSpec>) || {},
        } as TaskSpec,
      ];
    })
  );

  return (
    <div className="container mx-auto p-6">
      <TasksTable initialData={initialData} taskSpecs={taskSpecs} labSpecs={labSpecs} />
    </div>
  );
}
