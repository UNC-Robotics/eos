'use client';

import { ReactFlowProvider } from '@xyflow/react';
import { VisualProtocolEditor } from './VisualProtocolEditor';

interface Props {
  hasJinja: boolean;
  onSave: () => void | Promise<void>;
  onReload?: () => void;
  onSwitchToCode: () => void;
}

export function VisualProtocolEditorWithProvider(props: Props) {
  return (
    <ReactFlowProvider>
      <VisualProtocolEditor {...props} />
    </ReactFlowProvider>
  );
}
