'use client';

import { ReactFlowProvider } from '@xyflow/react';
import { VisualExperimentEditor } from './VisualExperimentEditor';

interface Props {
  hasJinja: boolean;
  onSave: () => void | Promise<void>;
  onReload?: () => void;
  onSwitchToCode: () => void;
}

export function VisualExperimentEditorWithProvider(props: Props) {
  return (
    <ReactFlowProvider>
      <VisualExperimentEditor {...props} />
    </ReactFlowProvider>
  );
}
