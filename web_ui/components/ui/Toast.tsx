'use client';

import { memo, useEffect } from 'react';
import { X, CheckCircle, AlertCircle, Info } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'info';

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
}

interface ToastProps {
  toast: Toast;
  onClose: (id: string) => void;
}

const ToastComponent = memo(({ toast, onClose }: ToastProps) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose(toast.id);
    }, 8000); // Auto-dismiss after 8 seconds

    return () => clearTimeout(timer);
  }, [toast.id, onClose]);

  const Icon = toast.type === 'success' ? CheckCircle : toast.type === 'error' ? AlertCircle : Info;
  const bgColor =
    toast.type === 'success'
      ? 'bg-green-50 dark:bg-green-900/60 border-green-200 dark:border-green-800'
      : toast.type === 'error'
        ? 'bg-red-50 dark:bg-red-900/60 border-red-200 dark:border-red-800'
        : 'bg-blue-50 dark:bg-blue-900/60 border-blue-200 dark:border-blue-800';
  const iconColor =
    toast.type === 'success'
      ? 'text-green-600 dark:text-green-400'
      : toast.type === 'error'
        ? 'text-red-600 dark:text-red-400'
        : 'text-blue-600 dark:text-blue-400';

  return (
    <div
      className={`${bgColor} border rounded-lg shadow-lg p-4 flex items-start gap-3 min-w-[300px] max-w-[500px] animate-in slide-in-from-bottom fade-in duration-300`}
    >
      <div className={`flex-shrink-0 ${iconColor}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-900 dark:text-white">{toast.title}</p>
        {toast.message && <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">{toast.message}</p>}
      </div>
      <button
        onClick={() => onClose(toast.id)}
        className="flex-shrink-0 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
});

ToastComponent.displayName = 'ToastComponent';

interface ToastContainerProps {
  toasts: Toast[];
  onClose: (id: string) => void;
}

export const ToastContainer = memo(({ toasts, onClose }: ToastContainerProps) => {
  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <ToastComponent toast={toast} onClose={onClose} />
        </div>
      ))}
    </div>
  );
});

ToastContainer.displayName = 'ToastContainer';
