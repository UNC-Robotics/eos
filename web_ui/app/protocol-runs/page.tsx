import { getProtocolRuns } from '@/features/protocol-runs/api/protocolRuns';
import { ProtocolRunsTable } from '@/features/protocol-runs/components/ProtocolRunsTable';
import { getProtocolSpecs, getTaskSpecs, getLabSpecs } from '@/lib/api/specs';
import type { TaskSpec, ParameterSpec } from '@/lib/types/protocol';

export const dynamic = 'force-dynamic';

export default async function ProtocolRunsPage() {
  const [initialData, protocolSpecs, rawTaskSpecs, labSpecs] = await Promise.all([
    getProtocolRuns(),
    getProtocolSpecs(true),
    getTaskSpecs(),
    getLabSpecs(false),
  ]);

  // Transform task specs to match the format used in TasksTable
  const taskSpecs: Record<string, TaskSpec> = Object.fromEntries(
    Object.entries(rawTaskSpecs).map(([type, spec]) => {
      // Extract unique device types from devices object
      const deviceTypes = spec.devices ? Array.from(new Set(Object.values(spec.devices).map((d) => d.type))) : [];

      const transformedSpec: TaskSpec = {
        type,
        desc: spec.desc || '',
        device_types: deviceTypes,
        input_devices: spec.devices
          ? Object.fromEntries(
              Object.entries(spec.devices).map(([name, device]) => [
                name,
                {
                  type: device.type,
                  desc: '',
                },
              ])
            )
          : undefined,
        input_parameters: spec.input_parameters as Record<string, ParameterSpec> | undefined,
        input_resources: spec.input_resources
          ? Object.fromEntries(
              Object.entries(spec.input_resources).map(([name, resource]) => [
                name,
                {
                  type: resource.type,
                  desc: '',
                },
              ])
            )
          : undefined,
      };

      return [type, transformedSpec];
    })
  );

  return (
    <div className="container mx-auto p-6">
      <ProtocolRunsTable
        initialData={initialData}
        protocolSpecs={protocolSpecs}
        taskSpecs={taskSpecs}
        labSpecs={labSpecs}
      />
    </div>
  );
}
