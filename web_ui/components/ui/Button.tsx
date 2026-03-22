import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cn } from '@/lib/utils/cn';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean;
  variant?: 'default' | 'primary' | 'secondary' | 'destructive' | 'outline' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'md', asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';

    const baseStyles =
      'inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50';

    const variants = {
      default: 'bg-gray-100 text-gray-900 hover:bg-gray-200 dark:bg-slate-800 dark:text-white dark:hover:bg-slate-700',
      primary:
        'bg-blue-600 text-white hover:bg-blue-700 focus-visible:ring-blue-600 dark:bg-yellow-500 dark:text-slate-900 dark:hover:bg-yellow-600 dark:focus-visible:ring-yellow-500',
      secondary: 'bg-gray-600 text-white hover:bg-gray-700 dark:bg-slate-700 dark:hover:bg-slate-600',
      destructive:
        'bg-red-600 text-white hover:bg-red-700 focus-visible:ring-red-600 dark:bg-red-700 dark:hover:bg-red-800',
      outline:
        'border border-gray-300 bg-transparent hover:bg-gray-100 dark:border-slate-600 dark:hover:bg-slate-800 dark:text-gray-300',
      ghost: 'hover:bg-gray-100 dark:hover:bg-slate-800 dark:text-gray-300',
    };

    const sizes = {
      sm: 'h-8 px-3 text-sm',
      md: 'h-10 px-4',
      lg: 'h-12 px-6 text-lg',
    };

    return <Comp ref={ref} className={cn(baseStyles, variants[variant], sizes[size], className)} {...props} />;
  }
);

Button.displayName = 'Button';

export { Button };
