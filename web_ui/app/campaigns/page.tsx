import { getCampaigns } from '@/features/campaigns/api/campaigns';
import { CampaignsTable } from '@/features/campaigns/components/CampaignsTable';
import { getProtocolSpecs, getTaskSpecs } from '@/lib/api/specs';
import type { TaskSpec, ParameterSpec } from '@/lib/types/protocol';

export const dynamic = 'force-dynamic';

export default async function CampaignsPage() {
  const [initialData, protocolSpecs, rawTaskSpecs] = await Promise.all([
    getCampaigns(),
    getProtocolSpecs(true),
    getTaskSpecs(),
  ]);

  // Transform task specs to match the format used in submission dialogs
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
      <CampaignsTable initialData={initialData} protocolSpecs={protocolSpecs} taskSpecs={taskSpecs} />
    </div>
  );
}
