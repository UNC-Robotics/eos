import * as React from 'react';
import { Primitive } from '@radix-ui/react-primitive';
import { cn } from '@/lib/utils/cn';

type SkeletonElement = React.ElementRef<typeof Primitive.div>;
type SkeletonProps = React.ComponentPropsWithoutRef<typeof Primitive.div>;

const Skeleton = React.forwardRef<SkeletonElement, SkeletonProps>(({ className, ...props }, ref) => {
  return (
    <Primitive.div
      ref={ref}
      className={cn('rounded-md bg-gray-200 dark:bg-slate-700', className)}
      style={{
        opacity: 0,
        animation:
          'skeleton-fade-in 150ms ease-out 200ms forwards, skeleton-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite 200ms',
      }}
      {...props}
    />
  );
});

Skeleton.displayName = 'Skeleton';

export { Skeleton };
