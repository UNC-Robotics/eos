'use client';

import { createContext, useContext, useState, type ReactNode } from 'react';

interface LogPanelContextValue {
  showLogs: boolean;
  setShowLogs: (show: boolean | ((prev: boolean) => boolean)) => void;
  toggleLogs: () => void;
}

const LogPanelContext = createContext<LogPanelContextValue | null>(null);

export function LogPanelProvider({ children }: { children: ReactNode }) {
  const [showLogs, setShowLogs] = useState(false);
  const toggleLogs = () => setShowLogs((prev) => !prev);

  return <LogPanelContext.Provider value={{ showLogs, setShowLogs, toggleLogs }}>{children}</LogPanelContext.Provider>;
}

export function useLogPanel() {
  const ctx = useContext(LogPanelContext);
  if (!ctx) throw new Error('useLogPanel must be used within LogPanelProvider');
  return ctx;
}
