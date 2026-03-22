'use client';

import * as React from 'react';
import { LogViewer } from './LogViewer';

const MIN_HEIGHT = 100;
const MAX_HEIGHT = 600;
const DEFAULT_HEIGHT = 224; // h-56

interface ResizableLogPanelProps {
  enabled: boolean;
}

export function ResizableLogPanel({ enabled }: ResizableLogPanelProps) {
  const [height, setHeight] = React.useState(DEFAULT_HEIGHT);
  const [isResizing, setIsResizing] = React.useState(false);
  const draggingRef = React.useRef(false);
  const startYRef = React.useRef(0);
  const startHeightRef = React.useRef(0);

  const handleMouseDown = React.useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      draggingRef.current = true;
      setIsResizing(true);
      startYRef.current = e.clientY;
      startHeightRef.current = height;

      const handleMouseMove = (ev: MouseEvent) => {
        if (!draggingRef.current) return;
        const delta = startYRef.current - ev.clientY;
        const newHeight = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, startHeightRef.current + delta));
        setHeight(newHeight);
      };

      const handleMouseUp = () => {
        draggingRef.current = false;
        setIsResizing(false);
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';
    },
    [height]
  );

  return (
    <div className="shrink-0 flex flex-col border-t border-gray-200 dark:border-slate-700" style={{ height }}>
      <div
        onMouseDown={handleMouseDown}
        className="h-1 cursor-row-resize bg-gray-200 dark:bg-gray-700 hover:bg-blue-500 dark:hover:bg-yellow-500 transition-colors shrink-0"
      />
      <div className="flex-1 min-h-0">
        <LogViewer enabled={enabled} isResizing={isResizing} />
      </div>
    </div>
  );
}
