'use client';

import { ThemeProvider } from 'next-themes';
import { Sidebar } from './Sidebar';
import { TransferPanel } from './TransferPanel';
import { LogPanelProvider, useLogPanel } from '@/contexts/LogPanelContext';
import { OrchestratorStatusProvider } from '@/contexts/OrchestratorStatusContext';
import { ResizableLogPanel } from '@/features/logs/components/ResizableLogPanel';
import type { ReactNode } from 'react';

function MainContent({ children }: { children: ReactNode }) {
  const { showLogs } = useLogPanel();

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-auto bg-gray-50 dark:bg-slate-950">{children}</div>
      {showLogs && <ResizableLogPanel enabled={showLogs} />}
    </div>
  );
}

export function ClientLayout({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <OrchestratorStatusProvider>
        <LogPanelProvider>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <MainContent>{children}</MainContent>
          </div>
          <TransferPanel />
        </LogPanelProvider>
      </OrchestratorStatusProvider>
    </ThemeProvider>
  );
}
