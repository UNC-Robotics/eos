'use client';

import * as React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils/cn';

const MAX_WIDTHS = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '3xl': 'max-w-3xl',
} as const;

interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Rendered before the title (e.g. a status badge or icon). */
  icon?: React.ReactNode;
  maxWidth?: keyof typeof MAX_WIDTHS;
  /** Prevents closing via overlay, Escape, or the close button (e.g. while submitting). */
  closeDisabled?: boolean;
  className?: string;
  children: React.ReactNode;
}

/** Themed dialog shell: overlay, animated content, header with title and close button. */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  icon,
  maxWidth = 'md',
  closeDisabled = false,
  className,
  children,
}: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => !closeDisabled && onOpenChange(next)}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content
          className={cn(
            'fixed left-[50%] top-[50%] z-50 w-full translate-x-[-50%] translate-y-[-50%] rounded-lg bg-white p-6 shadow-lg dark:bg-slate-900',
            'data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
            MAX_WIDTHS[maxWidth],
            className
          )}
        >
          <div className="mb-4 flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              {icon}
              <div>
                <Dialog.Title className="text-lg font-semibold text-gray-900 dark:text-white">{title}</Dialog.Title>
                {description && (
                  <Dialog.Description className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                    {description}
                  </Dialog.Description>
                )}
              </div>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                disabled={closeDisabled}
                aria-label="Close"
                className="rounded-sm text-gray-400 opacity-70 ring-offset-white transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-blue-600 dark:focus:ring-yellow-500 focus:ring-offset-2 disabled:pointer-events-none dark:text-gray-400 dark:ring-offset-slate-900"
              >
                <X className="h-5 w-5" />
                <span className="sr-only">Close</span>
              </button>
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
