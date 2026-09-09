'use client';

import { useCallback, useRef } from 'react';
import { useEditorStore } from '@/lib/stores/editorStore';
import { serializeCurrentProtocol } from '@/lib/utils/protocolSerializer';
import { validateProtocol } from '@/features/editor/api/validate';

/**
 * Hook that exposes a manual validate function.
 * Calls the orchestrator's /protocols/validate endpoint via a server action.
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
      const result = await validateProtocol(yaml);

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
