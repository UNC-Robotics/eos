'use client';

import { ThemeProvider } from 'next-themes';
import { usePathname } from 'next/navigation';
import { ShieldAlert } from 'lucide-react';
import { Sidebar } from './Sidebar';
import { TransferPanel } from './TransferPanel';
import { LogPanelProvider, useLogPanel } from '@/contexts/LogPanelContext';
import { OrchestratorStatusProvider } from '@/contexts/OrchestratorStatusContext';
import { useUser } from '@/contexts/UserContext';
import { signOutUser } from '@/features/auth/api/actions';
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

function NoAccessScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-slate-950">
      <div className="w-full max-w-md p-8 bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 shadow-sm text-center">
        <ShieldAlert className="w-10 h-10 mx-auto mb-4 text-amber-500" />
        <h1 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">No access</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
          Your account has no roles yet. Ask an administrator to assign you a role.
        </p>
        <button
          onClick={() => signOutUser()}
          className="px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}

export function ClientLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const user = useUser();

  // The sign-in page renders without the app chrome
  if (pathname === '/signin') {
    return (
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        {children}
      </ThemeProvider>
    );
  }

  const noAccess = user.authEnabled && !user.superuser && user.roles.length === 0;

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      {noAccess ? (
        <NoAccessScreen />
      ) : (
        <OrchestratorStatusProvider>
          <LogPanelProvider>
            <div className="flex h-screen overflow-hidden">
              <Sidebar />
              <MainContent>{children}</MainContent>
            </div>
            <TransferPanel />
          </LogPanelProvider>
        </OrchestratorStatusProvider>
      )}
    </ThemeProvider>
  );
}
