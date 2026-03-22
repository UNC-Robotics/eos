import { Skeleton } from '@/components/ui/Skeleton';

export default function Loading() {
  const columnCount = 5;
  const rowCount = 8;
  const headerWidths = ['w-44', 'w-32', 'w-32', 'w-28', 'w-24'];
  const cellWidths = ['w-40', 'w-28', 'w-20', 'w-24', 'w-16'];

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-slate-950 px-6 py-10">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="space-y-3">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-64" />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex w-full max-w-md items-center gap-3 sm:flex-1">
            <Skeleton className="h-10 w-full" />
          </div>
          <div className="flex items-center gap-3">
            <Skeleton className="h-9 w-28" />
            <Skeleton className="h-9 w-24" />
          </div>
        </div>

        <div className="rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900">
          <div className="grid grid-cols-5 border-b border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800">
            {Array.from({ length: columnCount }).map((_, columnIndex) => (
              <div
                key={`header-${columnIndex}`}
                className="border-r border-gray-200 dark:border-slate-700 p-4 last:border-r-0"
              >
                <Skeleton className={`h-4 ${headerWidths[columnIndex % headerWidths.length]}`} />
              </div>
            ))}
          </div>

          <div className="divide-y divide-gray-200 dark:divide-slate-700">
            {Array.from({ length: rowCount }).map((_, rowIndex) => (
              <div key={`row-${rowIndex}`} className="grid grid-cols-5">
                {Array.from({ length: columnCount }).map((_, cellIndex) => (
                  <div
                    key={`row-${rowIndex}-cell-${cellIndex}`}
                    className="border-r border-gray-100 dark:border-slate-700 p-4 last:border-r-0"
                  >
                    <Skeleton className={`h-4 ${cellWidths[cellIndex % cellWidths.length]}`} />
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
