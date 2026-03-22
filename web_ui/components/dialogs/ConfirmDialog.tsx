'use client';

import { memo } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, Info, X } from 'lucide-react';

interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'warning' | 'info' | 'danger';
}

const ConfirmDialogComponent = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'warning',
}: ConfirmDialogProps) => {
  const handleConfirm = () => {
    onConfirm();
    onClose();
  };

  const Icon = variant === 'info' ? Info : AlertTriangle;
  const iconColor = variant === 'danger' ? 'text-red-500' : variant === 'warning' ? 'text-yellow-500' : 'text-blue-500';
  const confirmButtonClass =
    variant === 'danger'
      ? 'bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-700 text-white'
      : 'bg-blue-600 hover:bg-blue-700 dark:bg-yellow-500 dark:hover:bg-yellow-600 text-white dark:text-slate-900';

  return (
    <Dialog.Root open={isOpen} onOpenChange={onClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 z-50 animate-in fade-in" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white dark:bg-slate-900 rounded-lg shadow-xl w-[450px] z-50 animate-in fade-in zoom-in-95">
          {/* Header */}
          <div className="flex items-start gap-4 p-6 pb-4">
            <div className={`flex-shrink-0 ${iconColor}`}>
              <Icon className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <Dialog.Title className="text-lg font-semibold text-gray-900 dark:text-white">{title}</Dialog.Title>
              <Dialog.Description className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                {message}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </Dialog.Close>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 px-6 py-4 bg-gray-50 dark:bg-slate-800 rounded-b-lg">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-md hover:bg-gray-50 dark:hover:bg-slate-600 transition-colors"
            >
              {cancelText}
            </button>
            <button
              onClick={handleConfirm}
              className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${confirmButtonClass}`}
            >
              {confirmText}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};

ConfirmDialogComponent.displayName = 'ConfirmDialog';

export const ConfirmDialog = memo(ConfirmDialogComponent);
