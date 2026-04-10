'use client';

import { createContext, useContext, type ReactNode } from 'react';
import { useOrchestratorStatus } from '@/hooks/useOrchestratorStatus';

interface OrchestratorStatusContextValue {
  isConnected: boolean;
  isChecking: boolean;
  checkNow: () => void;
}

const OrchestratorStatusContext = createContext<OrchestratorStatusContextValue | null>(null);

export function OrchestratorStatusProvider({ children }: { children: ReactNode }) {
  const { isConnected, isChecking, checkNow } = useOrchestratorStatus();

  return (
    <OrchestratorStatusContext.Provider value={{ isConnected, isChecking, checkNow }}>
      {children}
    </OrchestratorStatusContext.Provider>
  );
}

export function useOrchestratorConnected() {
  const ctx = useContext(OrchestratorStatusContext);
  if (!ctx) throw new Error('useOrchestratorConnected must be used within OrchestratorStatusProvider');
  return ctx;
}
