'use client';

import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Download, X } from 'lucide-react';
import { useReactFlow, getNodesBounds } from '@xyflow/react';
import { useEditorStore } from '@/lib/stores/editorStore';

interface ExportImageDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

const PADDING = 50;

export function ExportImageDialog({ isOpen, onClose }: ExportImageDialogProps) {
  const [zoom, setZoom] = useState(2);
  const [isExporting, setIsExporting] = useState(false);
  const { getNodes } = useReactFlow();
  const protocolType = useEditorStore((state) => state.protocolType);

  const handleExport = async () => {
    const nodes = getNodes();
    if (nodes.length === 0) return;

    setIsExporting(true);
    try {
      const bounds = getNodesBounds(nodes);

      // Image dimensions = tight bounds + small padding, scaled by user zoom
      const imageWidth = Math.round((bounds.width + PADDING * 2) * zoom);
      const imageHeight = Math.round((bounds.height + PADDING * 2) * zoom);

      // Compute viewport transform: position nodes to fill the image tightly
      // translate to place top-left of bounds at (PADDING, PADDING), then scale
      const transform = `translate(${-bounds.x * zoom + PADDING * zoom}px, ${-bounds.y * zoom + PADDING * zoom}px) scale(${zoom})`;

      const viewportEl = document.querySelector('.react-flow__viewport') as HTMLElement;
      if (!viewportEl) return;

      const { toCanvas } = await import('html-to-image');
      const canvas = await toCanvas(viewportEl, {
        width: imageWidth,
        height: imageHeight,
        pixelRatio: 1,
        cacheBust: false,
        skipAutoScale: true,
        style: {
          width: `${imageWidth}px`,
          height: `${imageHeight}px`,
          transform,
        },
        filter: (node) => {
          if (node instanceof HTMLElement) {
            if (node.classList.contains('react-flow__background')) return false;
            if (node.classList.contains('react-flow__controls')) return false;
          }
          return true;
        },
      });

      canvas.toBlob((blob) => {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.download = `${protocolType || 'protocol'}.png`;
        a.href = url;
        a.click();
        URL.revokeObjectURL(url);
        onClose();
      }, 'image/png');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <Dialog.Root open={isOpen} onOpenChange={onClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 z-50 animate-in fade-in" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white dark:bg-slate-900 rounded-lg shadow-xl w-[400px] z-50 animate-in fade-in zoom-in-95">
          <div className="flex items-start gap-4 p-6 pb-4">
            <div className="flex-shrink-0 text-blue-500">
              <Download className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <Dialog.Title className="text-lg font-semibold text-gray-900 dark:text-white">
                Export as Image
              </Dialog.Title>
              <Dialog.Description className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                Download the canvas as a PNG with transparent background.
              </Dialog.Description>

              <div className="mt-4">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Zoom Level</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="0.5"
                    max="4"
                    step="0.25"
                    value={zoom}
                    onChange={(e) => setZoom(parseFloat(e.target.value))}
                    className="flex-1"
                  />
                  <input
                    type="number"
                    min="0.5"
                    max="4"
                    step="0.25"
                    value={zoom}
                    onChange={(e) => {
                      const v = parseFloat(e.target.value);
                      if (!isNaN(v) && v >= 0.5 && v <= 4) setZoom(v);
                    }}
                    className="w-16 px-2 py-1 text-sm border border-gray-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-gray-900 dark:text-gray-100"
                  />
                  <span className="text-sm text-gray-500 dark:text-gray-400">x</span>
                </div>
              </div>
            </div>
            <Dialog.Close asChild>
              <button className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </Dialog.Close>
          </div>

          <div className="flex items-center justify-end gap-3 px-6 py-4 bg-gray-50 dark:bg-slate-800 rounded-b-lg">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-md hover:bg-gray-50 dark:hover:bg-slate-600 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleExport}
              disabled={isExporting}
              className="px-4 py-2 text-sm font-medium rounded-md transition-colors bg-blue-600 hover:bg-blue-700 dark:bg-yellow-500 dark:hover:bg-yellow-600 text-white dark:text-slate-900 disabled:opacity-50"
            >
              {isExporting ? 'Exporting...' : 'Download'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
