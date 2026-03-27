'use client';

import { useCallback, useRef } from 'react';
import { useEditorStore } from '@/lib/stores/editorStore';
import { serializeCurrentProtocol } from '@/lib/utils/protocolSerializer';
import { orchestratorPost } from '@/lib/api/orchestrator';

interface ValidationResponse {
  valid: boolean;
  errors: Array<{ task: string | null; message: string }>;
}

/**
 * Hook that exposes a manual validate function.
 * Calls the orchestrator's /protocols/validate endpoint.
 * Degrades gracefully when the orchestrator is unavailable.
 */
export function useProtocolValidation() {
  const setValidationResult = useEditorStore((state) => state.setValidationResult);
  const setIsValidating = useEditorStore((state) => state.setIsValidating);
  const abortRef = useRef<AbortController | null>(null);

  const validate = useCallback(async () => {
    const { tasks, protocolType, labs } = useEditorStore.getState();

    if (tasks.length === 0 || !protocolType || labs.length === 0) {
      setValidationResult({ valid: true, errors: [] });
      return;
    }

    const { yaml } = serializeCurrentProtocol();

    // Abort any in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsValidating(true);

    try {
      const result = (await orchestratorPost('/protocols/validate', {
        protocol_yaml: yaml,
      })) as ValidationResponse;

      if (!controller.signal.aborted) {
        setValidationResult({
          valid: result.valid,
          errors: result.errors || [],
        });
      }
    } catch {
      // Orchestrator unavailable — degrade gracefully
      if (!controller.signal.aborted) {
        setValidationResult({ valid: true, errors: [] });
        useEditorStore.setState({ isValid: null });
      }
    }
  }, [setValidationResult, setIsValidating]);

  return { validate };
}
