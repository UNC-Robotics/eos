'use client';

import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/Sheet';
import { ExperimentDetail } from './shared';
import type { Experiment } from '@/lib/types/api';

interface ExperimentDetailPanelProps {
  experiment: Experiment | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ExperimentDetailPanel({ experiment, open, onOpenChange }: ExperimentDetailPanelProps) {
  if (!experiment) return null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{experiment.name}</SheetTitle>
          <SheetDescription>Experiment Details</SheetDescription>
        </SheetHeader>
        <div className="mt-6">
          <ExperimentDetail experiment={experiment} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
