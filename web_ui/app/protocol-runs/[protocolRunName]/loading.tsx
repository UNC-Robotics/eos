import { Skeleton } from '@/components/ui/Skeleton';

export default function ProtocolRunDetailLoading() {
  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Skeleton className="h-8 w-16" />
            <div>
              <div className="flex items-center gap-2">
                <Skeleton className="h-6 w-48" />
                <Skeleton className="h-5 w-20 rounded-full" />
              </div>
              <Skeleton className="h-3 w-32 mt-1" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-20" />
            <Skeleton className="h-8 w-28" />
          </div>
        </div>
      </div>

      {/* Flow canvas area */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 p-8">
          {/* Simulated flow nodes */}
          <div className="flex flex-col items-center gap-6 pt-12">
            <Skeleton className="h-16 w-48 rounded-lg" />
            <Skeleton className="h-1 w-px bg-gray-200 dark:bg-slate-700" style={{ height: 32 }} />
            <div className="flex gap-8">
              <Skeleton className="h-16 w-44 rounded-lg" />
              <Skeleton className="h-16 w-44 rounded-lg" />
            </div>
            <Skeleton className="h-1 w-px bg-gray-200 dark:bg-slate-700" style={{ height: 32 }} />
            <Skeleton className="h-16 w-48 rounded-lg" />
          </div>
        </div>
      </div>
    </div>
  );
}
