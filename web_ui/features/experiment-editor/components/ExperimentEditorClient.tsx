'use client';

import { useEffect } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { ExperimentEditor } from './ExperimentEditor';
import { useEditorStore } from '@/lib/stores/editorStore';
import type { TaskSpec } from '@/lib/types/experiment';
import type { LabSpec } from '@/lib/api/specs';

interface ExperimentEditorClientProps {
  taskSpecs: TaskSpec[];
  labSpecs: Record<string, LabSpec>;
}

export function ExperimentEditorClient({ taskSpecs, labSpecs }: ExperimentEditorClientProps) {
  const setTaskTemplates = useEditorStore((state) => state.setTaskTemplates);
  const setLabSpecs = useEditorStore((state) => state.setLabSpecs);

  // Load specs into store on mount
  useEffect(() => {
    setTaskTemplates(taskSpecs);
    setLabSpecs(labSpecs);
  }, [taskSpecs, labSpecs, setTaskTemplates, setLabSpecs]);

  return (
    <ReactFlowProvider>
      <ExperimentEditor />
    </ReactFlowProvider>
  );
}
