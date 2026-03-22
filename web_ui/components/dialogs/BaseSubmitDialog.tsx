'use client';

import * as React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

function ErrorDisplay({ error }: { error: string }) {
  const lines = error.split('\n').filter((line) => line.trim());
  const hasMultipleLines = lines.length > 1;

  const clean = error.replace(/\u001b\[[0-9;]*m/g, '');

  if (!hasMultipleLines) {
    return (
      <div className="p-3 text-sm text-red-800 dark:text-red-200 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-md max-h-48 overflow-y-auto">
        <pre className="whitespace-pre-wrap break-words font-mono text-xs">{clean}</pre>
      </div>
    );
  }

  // First line is the header, rest are individual errors
  const cleanLines = clean.split('\n').filter((line) => line.trim());
  const [header, ...errorItems] = cleanLines;

  return (
    <div className="p-3 text-sm text-red-800 dark:text-red-200 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-md max-h-48 overflow-y-auto">
      <div className="font-medium mb-2">{header}</div>
      <ul className="list-disc list-inside space-y-1">
        {errorItems.map((item, i) => (
          <li key={i} className="text-xs font-mono">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

interface BaseSubmitDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  submitLabel?: string;
  children: React.ReactNode;
  isSubmitting: boolean;
  error: string | null;
  onSubmit: (e: React.FormEvent) => void;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl';
  headerActions?: React.ReactNode;
}

export function BaseSubmitDialog({
  open,
  onOpenChange,
  title,
  submitLabel = 'Submit',
  children,
  isSubmitting,
  error,
  onSubmit,
  maxWidth = '2xl',
  headerActions,
}: BaseSubmitDialogProps) {
  const { isConnected } = useOrchestratorConnected();

  const maxWidthClasses = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl',
    '2xl': 'max-w-2xl',
    '3xl': 'max-w-3xl',
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content
          className={`fixed left-[50%] top-[50%] z-50 w-full ${maxWidthClasses[maxWidth]} translate-x-[-50%] translate-y-[-50%] bg-white dark:bg-slate-900 rounded-lg shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95`}
        >
          <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-slate-700">
            <Dialog.Title className="text-lg font-semibold text-gray-900 dark:text-white">{title}</Dialog.Title>
            <div className="flex items-center gap-2">
              {headerActions}
              <Dialog.Close asChild>
                <button className="rounded-sm opacity-70 ring-offset-white dark:ring-offset-slate-900 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 text-gray-900 dark:text-gray-400">
                  <X className="h-4 w-4" />
                  <span className="sr-only">Close</span>
                </button>
              </Dialog.Close>
            </div>
          </div>

          <form onSubmit={onSubmit} className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
            {error && <ErrorDisplay error={error} />}

            {children}

            {error && <ErrorDisplay error={error} />}

            <div className="flex justify-end gap-3 pt-4">
              <Dialog.Close asChild>
                <Button type="button" variant="outline">
                  Cancel
                </Button>
              </Dialog.Close>
              <Button type="submit" variant="primary" disabled={isSubmitting || !isConnected}>
                {!isConnected ? 'Orchestrator Offline' : isSubmitting ? 'Submitting...' : submitLabel}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
