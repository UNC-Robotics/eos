import { Skeleton } from './Skeleton';

export function ChartSkeleton() {
  return (
    <div className="w-full h-64 flex flex-col gap-2">
      {/* Y-axis labels + chart area */}
      <div className="flex-1 flex gap-2">
        <div className="flex flex-col justify-between py-2">
          <Skeleton className="h-3 w-8" />
          <Skeleton className="h-3 w-6" />
          <Skeleton className="h-3 w-8" />
          <Skeleton className="h-3 w-6" />
        </div>
        <Skeleton className="flex-1 rounded-lg" />
      </div>
      {/* X-axis labels */}
      <div className="flex justify-between pl-10">
        <Skeleton className="h-3 w-6" />
        <Skeleton className="h-3 w-6" />
        <Skeleton className="h-3 w-6" />
        <Skeleton className="h-3 w-6" />
        <Skeleton className="h-3 w-6" />
      </div>
    </div>
  );
}
