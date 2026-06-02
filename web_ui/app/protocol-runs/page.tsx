import { getProtocolRuns } from '@/features/protocol-runs/api/protocolRuns';
import { ProtocolRunsTable } from '@/features/protocol-runs/components/ProtocolRunsTable';
import { getProtocolSpecs, getTaskSpecs, getLabSpecs } from '@/lib/api/specs';
import { transformTaskSpec } from '@/lib/api/taskSpecTransform';
import type { TaskSpec } from '@/lib/types/protocol';

export const dynamic = 'force-dynamic';

export default async function ProtocolRunsPage() {
  const [initialData, protocolSpecs, rawTaskSpecs, labSpecs] = await Promise.all([
    getProtocolRuns(),
    getProtocolSpecs(true),
    getTaskSpecs(),
    getLabSpecs(false),
  ]);

  const taskSpecs: Record<string, TaskSpec> = Object.fromEntries(
    Object.entries(rawTaskSpecs).map(([type, spec]) => [type, transformTaskSpec(type, spec)])
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
