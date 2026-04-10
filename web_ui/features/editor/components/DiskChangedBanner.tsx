'use client';

import { AlertTriangle } from 'lucide-react';
import { useEditorStore } from '@/lib/stores/editorStore';

interface DiskChangedBannerProps {
  onReload?: () => void;
}

export function DiskChangedBanner({ onReload }: DiskChangedBannerProps) {
  const diskChanged = useEditorStore((s) => s.diskChanged);
  const setDiskChanged = useEditorStore((s) => s.setDiskChanged);

  if (!diskChanged) return null;

  return (
    <div className="flex items-center gap-2 px-4 py-2 border-b border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-900/20 text-orange-800 dark:text-orange-200 text-sm">
      <AlertTriangle className="w-4 h-4 flex-shrink-0" />
      <span className="flex-1">File has been modified externally.</span>
      <button
        onClick={() => {
          onReload?.();
          setDiskChanged(false);
        }}
        className="text-xs font-medium underline hover:no-underline"
      >
        Reload from disk
      </button>
      <button onClick={() => setDiskChanged(false)} className="text-xs font-medium underline hover:no-underline ml-2">
        Dismiss
      </button>
    </div>
  );
}
