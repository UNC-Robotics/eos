'use client';

import { useEffect, useRef, useState } from 'react';
import * as Popover from '@radix-ui/react-popover';
import { CircleHelp } from 'lucide-react';

interface DescriptionTooltipProps {
  description?: string;
  constraints?: string;
}

const HOVER_OPEN_DELAY_MS = 200;
const HOVER_CLOSE_DELAY_MS = 80; // grace period to move between trigger and content

export function DescriptionTooltip({ description, constraints }: DescriptionTooltipProps) {
  const [open, setOpen] = useState(false);
  const timerRef = useRef<number | null>(null);
  const anchorRef = useRef<HTMLButtonElement>(null);

  // Cancel any pending open/close timer if the tooltip unmounts mid-delay.
  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    },
    []
  );

  if (!description && !constraints) return null;

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const scheduleOpen = () => {
    clearTimer();
    if (open) return;
    timerRef.current = window.setTimeout(() => setOpen(true), HOVER_OPEN_DELAY_MS);
  };

  const scheduleClose = () => {
    clearTimer();
    timerRef.current = window.setTimeout(() => setOpen(false), HOVER_CLOSE_DELAY_MS);
  };

  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        clearTimer();
      }}
    >
      {/* Anchor (not Trigger): we drive open/close manually so a click while hovering doesn't toggle closed. */}
      <Popover.Anchor asChild>
        <button
          ref={anchorRef}
          type="button"
          tabIndex={-1}
          onMouseEnter={scheduleOpen}
          onMouseLeave={scheduleClose}
          onClick={(e) => {
            e.stopPropagation();
            clearTimer();
            setOpen(true);
          }}
          className="inline-flex ml-1 align-middle text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
        >
          <CircleHelp className="h-3.5 w-3.5" />
        </button>
      </Popover.Anchor>
      <Popover.Portal>
        <Popover.Content
          className="bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 px-3 py-2 rounded-md text-xs max-w-xs shadow-lg z-[100]"
          sideOffset={5}
          onOpenAutoFocus={(e) => e.preventDefault()}
          onInteractOutside={(e) => {
            // The anchor isn't recognized as "the trigger" by Radix, so a click/focus
            // on it would otherwise dismiss the popover and flash. Covers both
            // pointer-down-outside and focus-outside paths.
            const target = e.detail.originalEvent.target;
            if (target instanceof Node && anchorRef.current?.contains(target)) {
              e.preventDefault();
            }
          }}
          onMouseEnter={clearTimer}
          onMouseLeave={scheduleClose}
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
          <Popover.Arrow className="fill-gray-900 dark:fill-gray-100" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
