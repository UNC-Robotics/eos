'use client';

import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/Sheet';
import { ProtocolRunDetail } from './shared';
import type { ProtocolRun } from '@/lib/types/api';

interface ProtocolRunDetailPanelProps {
  protocolRun: ProtocolRun | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ProtocolRunDetailPanel({ protocolRun, open, onOpenChange }: ProtocolRunDetailPanelProps) {
  if (!protocolRun) return null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{protocolRun.name}</SheetTitle>
          <SheetDescription>Protocol Run Details</SheetDescription>
        </SheetHeader>
        <div className="mt-6">
          <ProtocolRunDetail protocolRun={protocolRun} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
