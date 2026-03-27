import * as Tooltip from '@radix-ui/react-tooltip';
import { CircleHelp } from 'lucide-react';

interface DescriptionTooltipProps {
  description?: string;
  constraints?: string;
}

export function DescriptionTooltip({ description, constraints }: DescriptionTooltipProps) {
  if (!description && !constraints) return null;

  const parts: string[] = [];
  if (description) parts.push(description);
  if (constraints) parts.push(constraints);

  return (
    <Tooltip.Provider delayDuration={200}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <button
            type="button"
            className="inline-flex ml-1 align-middle text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
          >
            <CircleHelp className="h-3.5 w-3.5" />
          </button>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            className="bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 px-3 py-2 rounded-md text-xs max-w-xs shadow-lg z-[100]"
            sideOffset={5}
          >
            {description && constraints ? (
              <div className="space-y-1">
                <div className="font-medium text-gray-300 dark:text-gray-600">{constraints}</div>
                <div>{description}</div>
              </div>
            ) : constraints ? (
              <div className="font-medium">{constraints}</div>
            ) : (
              description
            )}
            <Tooltip.Arrow className="fill-gray-900 dark:fill-gray-100" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
