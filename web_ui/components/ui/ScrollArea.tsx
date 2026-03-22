import * as React from 'react';
import * as ScrollAreaPrimitive from '@radix-ui/react-scroll-area';

export const ScrollArea = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.Root>
>(({ className, children, ...props }, ref) => (
  <ScrollAreaPrimitive.Root ref={ref} className={`relative overflow-hidden ${className || ''}`} {...props}>
    <ScrollAreaPrimitive.Viewport className="h-full w-full rounded-[inherit]">{children}</ScrollAreaPrimitive.Viewport>
    <ScrollAreaPrimitive.Scrollbar
      orientation="vertical"
      className="flex touch-none select-none transition-colors h-full w-2.5 border-l border-l-transparent p-[1px]"
    >
      <ScrollAreaPrimitive.Thumb className="relative flex-1 rounded-full bg-gray-300 dark:bg-gray-600" />
    </ScrollAreaPrimitive.Scrollbar>
    <ScrollAreaPrimitive.Scrollbar
      orientation="horizontal"
      className="flex touch-none select-none transition-colors h-2.5 flex-col border-t border-t-transparent p-[1px]"
    >
      <ScrollAreaPrimitive.Thumb className="relative flex-1 rounded-full bg-gray-300 dark:bg-gray-600" />
    </ScrollAreaPrimitive.Scrollbar>
    <ScrollAreaPrimitive.Corner />
  </ScrollAreaPrimitive.Root>
));

ScrollArea.displayName = 'ScrollArea';
