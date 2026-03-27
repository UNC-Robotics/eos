'use client';

import { memo, useState, useMemo, useEffect } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Search, X } from 'lucide-react';
import type { TaskSpec } from '@/lib/types/protocol';

const PACKAGE_FILTER_KEY = 'eos-task-template-package-filter';

interface NewTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  templates: TaskSpec[];
  onSelectTemplate: (template: TaskSpec) => void;
}

const NewTaskModalComponent = ({ isOpen, onClose, templates, onSelectTemplate }: NewTaskModalProps) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPackage, setSelectedPackage] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    try {
      return localStorage.getItem(PACKAGE_FILTER_KEY);
    } catch {
      return null;
    }
  });

  const packageNames = useMemo(() => {
    const names = new Set<string>();
    templates.forEach((t) => {
      if (t.packageName) names.add(t.packageName);
    });
    return Array.from(names).sort();
  }, [templates]);

  // Persist selected package to localStorage
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      if (selectedPackage) {
        localStorage.setItem(PACKAGE_FILTER_KEY, selectedPackage);
      } else {
        localStorage.removeItem(PACKAGE_FILTER_KEY);
      }
    } catch {}
  }, [selectedPackage]);

  // Reset to "All" if the stored package no longer exists
  useEffect(() => {
    if (selectedPackage && !packageNames.includes(selectedPackage)) {
      setSelectedPackage(null);
    }
  }, [selectedPackage, packageNames]);

  const filteredTemplates = useMemo(() => {
    let result = templates;

    if (selectedPackage) {
      result = result.filter((t) => t.packageName === selectedPackage);
    }

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter((t) => t.type.toLowerCase().includes(query) || t.desc.toLowerCase().includes(query));
    }

    return result;
  }, [templates, searchQuery, selectedPackage]);

  const handleSelect = (template: TaskSpec) => {
    onSelectTemplate(template);
    onClose();
    setSearchQuery('');
  };

  return (
    <Dialog.Root open={isOpen} onOpenChange={onClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 z-50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white dark:bg-slate-900 rounded-lg shadow-xl w-[600px] max-h-[80vh] z-50 flex flex-col">
          {/* Header */}
          <div className="p-6 border-b border-gray-200 dark:border-slate-700">
            <div className="flex items-center justify-between mb-4">
              <Dialog.Title className="text-xl font-semibold text-gray-900 dark:text-white">New Task</Dialog.Title>
              <Dialog.Close asChild>
                <button className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </Dialog.Close>
            </div>

            {/* Search Bar */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
              <input
                type="text"
                placeholder="Search tasks..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-yellow-500 bg-white dark:bg-slate-800 text-gray-900 dark:text-gray-100"
              />
            </div>

            {/* Package Filter */}
            {packageNames.length > 1 && (
              <div className="flex gap-1.5 mt-3 flex-wrap">
                <button
                  onClick={() => setSelectedPackage(null)}
                  className={`px-2.5 py-1 text-xs font-medium rounded-full transition-colors ${
                    selectedPackage === null
                      ? 'bg-blue-100 text-blue-700 dark:bg-yellow-900 dark:text-yellow-300'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-slate-700 dark:text-gray-300 dark:hover:bg-slate-600'
                  }`}
                >
                  All
                </button>
                {packageNames.map((pkg) => (
                  <button
                    key={pkg}
                    onClick={() => setSelectedPackage(pkg)}
                    className={`px-2.5 py-1 text-xs font-medium rounded-full transition-colors ${
                      selectedPackage === pkg
                        ? 'bg-blue-100 text-blue-700 dark:bg-yellow-900 dark:text-yellow-300'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-slate-700 dark:text-gray-300 dark:hover:bg-slate-600'
                    }`}
                  >
                    {pkg}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Task List */}
          <div className="flex-1 overflow-y-auto p-4">
            {filteredTemplates.length === 0 ? (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                No tasks found matching your search.
              </div>
            ) : (
              <div className="space-y-2">
                {filteredTemplates.map((template) => (
                  <button
                    key={template.type}
                    onClick={() => handleSelect(template)}
                    className="w-full text-left p-4 rounded-lg border border-gray-200 dark:border-slate-700 hover:border-blue-500 dark:hover:border-yellow-500 hover:bg-blue-50 dark:hover:bg-slate-800 transition-all"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-gray-900 dark:text-white">{template.type}</span>
                      {template.packageName && (
                        <span className="text-xs text-gray-400 dark:text-gray-500">{template.packageName}</span>
                      )}
                    </div>
                    <div className="text-sm text-gray-600 dark:text-gray-300">{template.desc}</div>
                    <div className="mt-2 flex gap-2 flex-wrap">
                      {template.device_types.map((deviceType) => (
                        <span
                          key={deviceType}
                          className="text-xs bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-300 px-2 py-1 rounded"
                        >
                          {deviceType}
                        </span>
                      ))}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};

NewTaskModalComponent.displayName = 'NewTaskModal';

export const NewTaskModal = memo(NewTaskModalComponent);
