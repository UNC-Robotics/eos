import { Skeleton } from '@/components/ui/Skeleton';

export default function EditorLoading() {
  return (
    <div className="h-screen bg-white dark:bg-gray-900 flex">
      {/* Left Panel - Package Tree Skeleton */}
      <div className="w-64 border-r border-gray-200 dark:border-gray-700 flex flex-col">
        {/* Header */}
        <div className="p-3 border-b border-gray-200 dark:border-gray-700">
          <Skeleton className="h-5 w-24" />
        </div>

        {/* Search Bar */}
        <div className="p-2">
          <Skeleton className="h-9 w-full" />
        </div>

        {/* Package Items */}
        <div className="flex-1 p-2 space-y-2">
          {Array.from({ length: 3 }).map((_, pkgIndex) => (
            <div key={`pkg-${pkgIndex}`} className="space-y-1">
              <Skeleton className="h-7 w-full" />
              <div className="ml-4 space-y-1">
                <Skeleton className="h-6 w-32" />
                <div className="ml-4 space-y-1">
                  <Skeleton className="h-5 w-full" />
                  <Skeleton className="h-5 w-full" />
                  <Skeleton className="h-5 w-3/4" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Center Panel - Editor Skeleton */}
      <div className="flex-1 flex flex-col">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-48" />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-20" />
            <Skeleton className="h-8 w-20" />
          </div>
        </div>

        {/* Tab Bar */}
        <div className="flex items-center gap-1 px-4 py-1 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <Skeleton className="h-7 w-24" />
          <Skeleton className="h-7 w-24" />
        </div>

        {/* Editor Content Area */}
        <div className="flex-1 p-4 space-y-2">
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-11/12" />
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-10/12" />
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-9/12" />
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-11/12" />
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-10/12" />
        </div>
      </div>
    </div>
  );
}
