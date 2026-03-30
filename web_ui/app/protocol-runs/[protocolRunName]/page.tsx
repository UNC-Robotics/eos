import { Suspense } from 'react';
import { notFound } from 'next/navigation';
import { Skeleton } from '@/components/ui/Skeleton';
import { getProtocolRunWithTaskStatuses } from '@/features/protocol-runs/api/protocolRunDetails';
import { getProtocolSpecs } from '@/lib/api/specs';
import { ProtocolRunExecutionView } from '@/features/protocol-runs/components/ProtocolRunExecutionView';

export const dynamic = 'force-dynamic';

interface ProtocolRunDetailPageProps {
  params: Promise<{
    protocolRunName: string;
  }>;
}

export default async function ProtocolRunDetailPage({ params }: ProtocolRunDetailPageProps) {
  const { protocolRunName } = await params;
  const decodedName = decodeURIComponent(protocolRunName);

  // Fetch protocol run with lightweight task statuses and specs in parallel
  const [{ protocolRun, taskStatuses }, protocolSpecs] = await Promise.all([
    getProtocolRunWithTaskStatuses(decodedName),
    getProtocolSpecs(false),
  ]);

  // If protocol run not found, show 404
  if (!protocolRun) {
    notFound();
  }

  // Get the protocol spec for this protocol run
  const protocolSpec = protocolSpecs[protocolRun.type];
  if (!protocolSpec) {
    throw new Error(`Protocol spec not found for type: ${protocolRun.type}`);
  }

  return (
    <Suspense
      fallback={
        <div className="flex flex-col h-screen">
          <div className="border-b border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2">
            <div className="flex items-center gap-3">
              <Skeleton className="h-8 w-16" />
              <div>
                <Skeleton className="h-6 w-48" />
                <Skeleton className="h-3 w-32 mt-1" />
              </div>
            </div>
          </div>
          <div className="flex-1 flex items-center justify-center">
            <div className="flex flex-col items-center gap-6">
              <Skeleton className="h-16 w-48 rounded-lg" />
              <div className="flex gap-8">
                <Skeleton className="h-16 w-44 rounded-lg" />
                <Skeleton className="h-16 w-44 rounded-lg" />
              </div>
              <Skeleton className="h-16 w-48 rounded-lg" />
            </div>
          </div>
        </div>
      }
    >
      <ProtocolRunExecutionView
        protocolRun={protocolRun}
        initialTaskStatuses={taskStatuses}
        protocolSpec={protocolSpec}
      />
    </Suspense>
  );
}
