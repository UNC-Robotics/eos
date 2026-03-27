'use client';

import { X } from 'lucide-react';
import { Skeleton } from '@/components/ui/Skeleton';
import { SECTION_DIVIDER } from '../styles';

interface TaskDetailPanelSkeletonProps {
  taskName: string;
  onClose: () => void;
}

export function TaskDetailPanelSkeleton({ taskName, onClose }: TaskDetailPanelSkeletonProps) {
  return (
    <div className="w-96 border-l border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-y-auto">
      <div className="sticky top-0 bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-700 p-4 z-10">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{taskName}</h2>
            <Skeleton className="h-4 w-24 mt-1" />
          </div>
          <button
            onClick={onClose}
            className="rounded-sm opacity-70 ring-offset-white dark:ring-offset-slate-900 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 text-gray-900 dark:text-gray-400"
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Close</span>
          </button>
        </div>
      </div>

      <div className="p-4 space-y-6">
        {/* Basic info skeleton */}
        <div className="space-y-3">
          <div>
            <Skeleton className="h-3 w-12 mb-1" />
            <Skeleton className="h-6 w-20" />
          </div>
          <div>
            <Skeleton className="h-3 w-14 mb-1" />
            <Skeleton className="h-5 w-8" />
          </div>
          <div>
            <Skeleton className="h-3 w-16 mb-1" />
            <Skeleton className="h-5 w-32" />
          </div>
        </div>

        {/* Timeline skeleton */}
        <div className={SECTION_DIVIDER}>
          <Skeleton className="h-4 w-16 mb-2" />
          <div className="space-y-1">
            <Skeleton className="h-3 w-48" />
            <Skeleton className="h-3 w-44" />
            <Skeleton className="h-3 w-40" />
          </div>
        </div>

        {/* Parameters skeleton */}
        <div className={SECTION_DIVIDER}>
          <Skeleton className="h-4 w-28 mb-2" />
          <Skeleton className="h-24 w-full rounded-md" />
        </div>

        {/* Resources skeleton */}
        <div className={SECTION_DIVIDER}>
          <Skeleton className="h-4 w-24 mb-2" />
          <Skeleton className="h-16 w-full rounded-md" />
        </div>
      </div>
    </div>
  );
}
