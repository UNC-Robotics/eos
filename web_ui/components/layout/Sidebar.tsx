'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  ChevronLeft,
  ChevronRight,
  SquarePen,
  ListChecks,
  FlaskConical,
  Target,
  FolderOpen,
  Microscope,
  Settings,
  Sun,
  Moon,
  Wifi,
  WifiOff,
  Terminal,
} from 'lucide-react';
import * as Separator from '@radix-ui/react-separator';
import * as Tooltip from '@radix-ui/react-tooltip';
import { useTheme } from 'next-themes';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';
import { useLogPanel } from '@/contexts/LogPanelContext';

export function Sidebar() {
  const [isExpanded, setIsExpanded] = useState(false);
  const pathname = usePathname();
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const { isConnected } = useOrchestratorConnected();
  const { showLogs, toggleLogs } = useLogPanel();

  // Avoid hydration mismatch
  useEffect(() => {
    setMounted(true);
  }, []);

  const currentTheme = theme === 'system' ? resolvedTheme : theme;

  const toggleTheme = () => {
    setTheme(currentTheme === 'dark' ? 'light' : 'dark');
  };

  const menuItems = [
    {
      href: '/editor',
      icon: SquarePen,
      label: 'Editor',
    },
    {
      href: '/tasks',
      icon: ListChecks,
      label: 'Tasks',
    },
    {
      href: '/experiments',
      icon: FlaskConical,
      label: 'Experiments',
    },
    {
      href: '/campaigns',
      icon: Target,
      label: 'Campaigns',
    },
    {
      href: '/files',
      icon: FolderOpen,
      label: 'Files',
    },
    {
      href: '/devices/inspect',
      icon: Microscope,
      label: 'Device Inspector',
    },
    {
      href: '/management',
      icon: Settings,
      label: 'Management',
    },
  ];

  return (
    <div
      className={`h-screen bg-white dark:bg-slate-900 border-r border-gray-200 dark:border-slate-700 shadow-sm transition-all duration-300 ease-in-out flex flex-col overflow-hidden ${
        isExpanded ? 'w-52' : 'w-16'
      }`}
      style={{ isolation: 'isolate' }}
    >
      {/* Header */}
      <div className="p-4 flex items-center justify-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">EOS</h1>
      </div>

      {/* Toggle Button */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="mx-2 mb-4 p-2 hover:bg-gray-100 dark:hover:bg-slate-800 rounded-md transition-colors duration-200 flex items-center justify-center"
        aria-label={isExpanded ? 'Collapse sidebar' : 'Expand sidebar'}
      >
        {isExpanded ? (
          <ChevronLeft className="w-5 h-5 text-gray-600 dark:text-gray-400" />
        ) : (
          <ChevronRight className="w-5 h-5 text-gray-600 dark:text-gray-400" />
        )}
      </button>

      <Separator.Root className="bg-gray-200 dark:bg-slate-700 h-px mx-2 mb-4" />

      {/* Menu Items and Theme Toggle */}
      <Tooltip.Provider delayDuration={300}>
        <nav className="flex-1 px-2">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;

            const linkContent = (
              <Link
                key={item.href}
                href={item.href}
                className={`w-full p-3 mb-1 rounded-md transition-all duration-200 flex items-center gap-3 ${
                  isActive
                    ? 'bg-blue-50 text-blue-600 dark:bg-slate-800 dark:text-yellow-400'
                    : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-800'
                }`}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                <span
                  className={`transition-opacity duration-300 whitespace-nowrap ${
                    isExpanded ? 'opacity-100' : 'opacity-0 w-0'
                  }`}
                >
                  {item.label}
                </span>
              </Link>
            );

            if (!isExpanded) {
              return (
                <Tooltip.Root key={item.href} disableHoverableContent>
                  <Tooltip.Trigger asChild>{linkContent}</Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content
                      side="right"
                      className="bg-gray-900 dark:bg-slate-700 text-white px-3 py-2 rounded-md text-sm shadow-lg z-50 pointer-events-none"
                      sideOffset={20}
                      collisionPadding={10}
                    >
                      {item.label}
                      <Tooltip.Arrow className="fill-gray-900 dark:fill-slate-700" />
                    </Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              );
            }

            return linkContent;
          })}
        </nav>

        {/* Logs Toggle */}
        <div className="px-2 mt-auto">
          {!isExpanded ? (
            <Tooltip.Root disableHoverableContent>
              <Tooltip.Trigger asChild>
                <button
                  onClick={toggleLogs}
                  className={`w-full p-3 mb-1 rounded-md transition-all duration-200 flex items-center justify-center ${
                    showLogs
                      ? 'bg-blue-50 text-blue-600 dark:bg-slate-800 dark:text-yellow-400'
                      : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-800'
                  }`}
                  aria-label="Toggle logs"
                >
                  <Terminal className="w-5 h-5 flex-shrink-0" />
                </button>
              </Tooltip.Trigger>
              <Tooltip.Portal>
                <Tooltip.Content
                  side="right"
                  className="bg-gray-900 dark:bg-slate-700 text-white px-3 py-2 rounded-md text-sm shadow-lg z-50 pointer-events-none"
                  sideOffset={20}
                  collisionPadding={10}
                >
                  Logs
                  <Tooltip.Arrow className="fill-gray-900 dark:fill-slate-700" />
                </Tooltip.Content>
              </Tooltip.Portal>
            </Tooltip.Root>
          ) : (
            <button
              onClick={toggleLogs}
              className={`w-full p-3 mb-1 rounded-md transition-all duration-200 flex items-center gap-3 ${
                showLogs
                  ? 'bg-blue-50 text-blue-600 dark:bg-slate-800 dark:text-yellow-400'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-800'
              }`}
              aria-label="Toggle logs"
            >
              <Terminal className="w-5 h-5 flex-shrink-0" />
              <span
                className={`transition-opacity duration-300 whitespace-nowrap ${
                  isExpanded ? 'opacity-100' : 'opacity-0 w-0'
                }`}
              >
                Logs
              </span>
            </button>
          )}
        </div>

        <Separator.Root className="bg-gray-200 dark:bg-slate-700 h-px mx-2 mt-4 mb-4" />

        {mounted && (
          <div className="px-2 pb-4 space-y-1">
            {/* Orchestrator Status Indicator */}
            {!isExpanded ? (
              <Tooltip.Root disableHoverableContent>
                <Tooltip.Trigger asChild>
                  <div
                    className="w-full p-3 rounded-md flex items-center justify-center"
                    aria-label={isConnected ? 'Orchestrator online' : 'Orchestrator offline'}
                  >
                    {isConnected ? (
                      <Wifi className="w-5 h-5 text-green-500" />
                    ) : (
                      <WifiOff className="w-5 h-5 text-red-500" />
                    )}
                  </div>
                </Tooltip.Trigger>
                <Tooltip.Portal>
                  <Tooltip.Content
                    side="right"
                    className="bg-gray-900 dark:bg-slate-700 text-white px-3 py-2 rounded-md text-sm shadow-lg z-50 pointer-events-none"
                    sideOffset={20}
                    collisionPadding={10}
                  >
                    {isConnected ? 'Orchestrator online' : 'Orchestrator offline'}
                    <Tooltip.Arrow className="fill-gray-900 dark:fill-slate-700" />
                  </Tooltip.Content>
                </Tooltip.Portal>
              </Tooltip.Root>
            ) : (
              <div
                className="w-full p-3 rounded-md flex items-center gap-3"
                aria-label={isConnected ? 'Orchestrator online' : 'Orchestrator offline'}
              >
                {isConnected ? (
                  <Wifi className="w-5 h-5 flex-shrink-0 text-green-500" />
                ) : (
                  <WifiOff className="w-5 h-5 flex-shrink-0 text-red-500" />
                )}
                <span
                  className={`transition-opacity duration-300 whitespace-nowrap ${
                    isConnected ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                  }`}
                >
                  {isConnected ? 'Online' : 'Offline'}
                </span>
              </div>
            )}

            {/* Theme Toggle */}
            {!isExpanded ? (
              <Tooltip.Root disableHoverableContent>
                <Tooltip.Trigger asChild>
                  <button
                    onClick={toggleTheme}
                    className="w-full p-3 rounded-md transition-all duration-200 flex items-center justify-center hover:bg-gray-100 dark:hover:bg-slate-800"
                    aria-label={currentTheme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
                  >
                    {currentTheme === 'light' ? (
                      <Moon className="w-5 h-5 text-gray-600 dark:text-gray-400" />
                    ) : (
                      <Sun className="w-5 h-5 text-gray-600 dark:text-gray-400" />
                    )}
                  </button>
                </Tooltip.Trigger>
                <Tooltip.Portal>
                  <Tooltip.Content
                    side="right"
                    className="bg-gray-900 dark:bg-slate-700 text-white px-3 py-2 rounded-md text-sm shadow-lg z-50 pointer-events-none"
                    sideOffset={20}
                    collisionPadding={10}
                  >
                    {currentTheme === 'light' ? 'Dark mode' : 'Light mode'}
                    <Tooltip.Arrow className="fill-gray-900 dark:fill-slate-700" />
                  </Tooltip.Content>
                </Tooltip.Portal>
              </Tooltip.Root>
            ) : (
              <button
                onClick={toggleTheme}
                className="w-full p-3 rounded-md transition-all duration-200 flex items-center gap-3 hover:bg-gray-100 dark:hover:bg-slate-800 text-gray-700 dark:text-gray-300"
                aria-label={currentTheme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
              >
                {currentTheme === 'light' ? (
                  <Moon className="w-5 h-5 flex-shrink-0" />
                ) : (
                  <Sun className="w-5 h-5 flex-shrink-0" />
                )}
                <span className="transition-opacity duration-300 whitespace-nowrap">
                  {currentTheme === 'light' ? 'Dark mode' : 'Light mode'}
                </span>
              </button>
            )}
          </div>
        )}
      </Tooltip.Provider>
    </div>
  );
}
