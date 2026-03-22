'use client';

import * as React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, X } from 'lucide-react';
import { Button } from '@/components/ui/Button';

interface ConfirmationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'destructive';
  items?: string[];
  onConfirm: () => Promise<void>;
}

export function ConfirmationDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  items,
  onConfirm,
}: ConfirmationDialogProps) {
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const handleConfirm = async () => {
    setIsSubmitting(true);
    setError(null);

    try {
      await onConfirm();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    if (!isSubmitting) {
      setError(null);
      onOpenChange(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={handleCancel}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 z-50" />
        <Dialog.Content className="fixed left-[50%] top-[50%] z-50 w-full max-w-lg translate-x-[-50%] translate-y-[-50%] bg-white dark:bg-slate-900 rounded-lg shadow-lg">
          <div className="p-6">
            {/* Header */}
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                {variant === 'destructive' && (
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
                    <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400" />
                  </div>
                )}
                <div>
                  <Dialog.Title className="text-lg font-semibold text-gray-900 dark:text-white">{title}</Dialog.Title>
                </div>
              </div>
              <Dialog.Close asChild>
                <button
                  className="rounded-sm opacity-70 ring-offset-white dark:ring-offset-slate-900 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-gray-400 focus:ring-offset-2 disabled:pointer-events-none text-gray-900 dark:text-gray-400"
                  disabled={isSubmitting}
                >
                  <X className="h-4 w-4" />
                  <span className="sr-only">Close</span>
                </button>
              </Dialog.Close>
            </div>

            {/* Content */}
            <div className="space-y-4">
              <Dialog.Description className="text-sm text-gray-600 dark:text-gray-300">
                {description}
              </Dialog.Description>

              {items && items.length > 0 && (
                <div className="rounded-md bg-gray-50 dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-3">
                  <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Affected items ({items.length}):
                  </p>
                  <ul className="text-sm text-gray-600 dark:text-gray-300 space-y-1 max-h-40 overflow-y-auto">
                    {items.map((item, index) => (
                      <li key={index} className="flex items-center gap-2">
                        <span className="h-1 w-1 rounded-full bg-gray-400 dark:bg-gray-500" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {error && (
                <div className="p-3 text-sm text-red-800 dark:text-red-200 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-md max-h-48 overflow-y-auto">
                  <pre className="whitespace-pre-wrap break-words font-mono text-xs">
                    {error.replace(/\u001b\[[0-9;]*m/g, '')}
                  </pre>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 mt-6">
              <Dialog.Close asChild>
                <Button type="button" variant="outline" disabled={isSubmitting}>
                  {cancelLabel}
                </Button>
              </Dialog.Close>
              <Button
                type="button"
                variant={variant === 'destructive' ? 'destructive' : 'primary'}
                disabled={isSubmitting}
                onClick={handleConfirm}
              >
                {isSubmitting ? 'Processing...' : confirmLabel}
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
