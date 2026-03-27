'use client';

import { useEffect } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { ProtocolEditor } from './ProtocolEditor';
import { useEditorStore } from '@/lib/stores/editorStore';
import type { TaskSpec } from '@/lib/types/protocol';
import type { LabSpec } from '@/lib/api/specs';

interface ProtocolEditorClientProps {
  taskSpecs: TaskSpec[];
  labSpecs: Record<string, LabSpec>;
}

export function ProtocolEditorClient({ taskSpecs, labSpecs }: ProtocolEditorClientProps) {
  const setTaskTemplates = useEditorStore((state) => state.setTaskTemplates);
  const setLabSpecs = useEditorStore((state) => state.setLabSpecs);

  // Load specs into store on mount
  useEffect(() => {
    setTaskTemplates(taskSpecs);
    setLabSpecs(labSpecs);
  }, [taskSpecs, labSpecs, setTaskTemplates, setLabSpecs]);

  return (
    <ReactFlowProvider>
      <ProtocolEditor />
    </ReactFlowProvider>
  );
}
