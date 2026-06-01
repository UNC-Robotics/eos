import * as React from 'react';
import { cn } from '@/lib/utils/cn';

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info' | 'muted';
}

const Badge = React.forwardRef<HTMLDivElement, BadgeProps>(({ className, variant = 'default', ...props }, ref) => {
  const variants = {
    default: 'bg-gray-100 text-gray-800 dark:bg-slate-700 dark:text-slate-200',
    success: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
    warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
    error: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    info: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
    muted: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
  };

  return (
    <div
      ref={ref}
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold',
        variants[variant],
        className
      )}
      {...props}
    />
  );
});

Badge.displayName = 'Badge';

export { Badge };

// Helper function to get badge variant based on status
export function getStatusBadgeVariant(status: string): BadgeProps['variant'] {
  const statusLower = status.toLowerCase();

  if (statusLower === 'completed') return 'success';
  if (statusLower === 'running') return 'info';
  if (statusLower === 'failed') return 'error';
  if (statusLower === 'cancelled') return 'warning';
  if (statusLower === 'suspended') return 'warning';
  if (statusLower === 'skipped') return 'muted';

  return 'default';
}
