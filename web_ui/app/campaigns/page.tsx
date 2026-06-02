import { getCampaigns } from '@/features/campaigns/api/campaigns';
import { CampaignsTable } from '@/features/campaigns/components/CampaignsTable';
import { getProtocolSpecs, getTaskSpecs } from '@/lib/api/specs';
import { transformTaskSpec } from '@/lib/api/taskSpecTransform';
import type { TaskSpec } from '@/lib/types/protocol';

export const dynamic = 'force-dynamic';

export default async function CampaignsPage() {
  const [initialData, protocolSpecs, rawTaskSpecs] = await Promise.all([
    getCampaigns(),
    getProtocolSpecs(true),
    getTaskSpecs(),
  ]);

  const taskSpecs: Record<string, TaskSpec> = Object.fromEntries(
    Object.entries(rawTaskSpecs).map(([type, spec]) => [type, transformTaskSpec(type, spec)])
  );

  return (
    <div className="container mx-auto p-6">
      <CampaignsTable initialData={initialData} protocolSpecs={protocolSpecs} taskSpecs={taskSpecs} />
    </div>
  );
}
