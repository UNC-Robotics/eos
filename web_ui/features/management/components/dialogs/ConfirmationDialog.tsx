'use client';

import * as React from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { ErrorBox } from '@/components/ui/ErrorBox';
import { Modal } from '@/components/ui/Modal';

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
    setError(null);
    onOpenChange(false);
  };

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && handleCancel()}
      title={title}
      description={description}
      maxWidth="xl"
      closeDisabled={isSubmitting}
      icon={
        variant === 'destructive' ? (
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
            <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400" />
          </div>
        ) : undefined
      }
    >
      <div className="space-y-4">
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

        {error && <ErrorBox error={error} />}
      </div>

      <div className="flex justify-end gap-3 mt-6">
        <Button type="button" variant="outline" disabled={isSubmitting} onClick={handleCancel}>
          {cancelLabel}
        </Button>
        <Button
          type="button"
          variant={variant === 'destructive' ? 'destructive' : 'primary'}
          disabled={isSubmitting}
          onClick={handleConfirm}
        >
          {isSubmitting ? 'Processing...' : confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
