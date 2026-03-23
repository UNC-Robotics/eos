import { Suspense } from 'react';
import { notFound } from 'next/navigation';
import { Skeleton } from '@/components/ui/Skeleton';
import { getExperimentWithTaskStatuses } from '@/features/experiments/api/experimentDetails';
import { getExperimentSpecs } from '@/lib/api/specs';
import { ExperimentExecutionView } from '@/features/experiments/components/ExperimentExecutionView';

export const dynamic = "force-dynamic";

interface ExperimentDetailPageProps {
  params: Promise<{
    experimentName: string;
  }>;
}

export default async function ExperimentDetailPage({ params }: ExperimentDetailPageProps) {
  const { experimentName } = await params;
  const decodedName = decodeURIComponent(experimentName);

  // Fetch experiment with lightweight task statuses and specs in parallel
  const [{ experiment, taskStatuses }, experimentSpecs] = await Promise.all([
    getExperimentWithTaskStatuses(decodedName),
    getExperimentSpecs(false),
  ]);

  // If experiment not found, show 404
  if (!experiment) {
    notFound();
  }

  // Get the experiment spec for this experiment
  const experimentSpec = experimentSpecs[experiment.type];
  if (!experimentSpec) {
    throw new Error(`Experiment spec not found for type: ${experiment.type}`);
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
      <ExperimentExecutionView
        experiment={experiment}
        initialTaskStatuses={taskStatuses}
        experimentSpec={experimentSpec}
      />
    </Suspense>
  );
}
