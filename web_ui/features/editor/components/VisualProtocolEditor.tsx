'use client';

import { useEffect, useState, useCallback } from 'react';
import { Save, Code, AlertTriangle, RefreshCw, Download, Upload } from 'lucide-react';
import { ProtocolEditor } from '@/features/protocol-editor/components/ProtocolEditor';
import { useEditorStore } from '@/lib/stores/editorStore';
import { serializeCurrentProtocol } from '@/lib/utils/protocolSerializer';
import { loadEntity, unloadEntity, reloadEntity } from '@/features/editor/api/reload';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';
import { getLoadedStatus } from '@/features/editor/api/loaded-status';
import { DiskChangedBanner } from './DiskChangedBanner';

interface VisualProtocolEditorProps {
  hasJinja: boolean;
  onSave: () => void | Promise<void>;
  onReload?: () => void;
  onSwitchToCode: () => void;
}

export function VisualProtocolEditor({ hasJinja, onSave, onReload, onSwitchToCode }: VisualProtocolEditorProps) {
  const selectedPackage = useEditorStore((s) => s.selectedPackage);
  const selectedEntityName = useEditorStore((s) => s.selectedEntityName);
  const isDirty = useEditorStore((s) => s.isDirty);
  const updateYaml = useEditorStore((s) => s.updateYaml);
  const updateLayout = useEditorStore((s) => s.updateLayout);

  const tasks = useEditorStore((s) => s.tasks);
  const taskTemplates = useEditorStore((s) => s.taskTemplates);
  const protocolType = useEditorStore((s) => s.protocolType);
  const protocolDesc = useEditorStore((s) => s.protocolDesc);
  const labs = useEditorStore((s) => s.labs);

  const { isConnected } = useOrchestratorConnected();
  const [isReloading, setIsReloading] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isUnloading, setIsUnloading] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);

  // Fetch loaded status when entity changes
  useEffect(() => {
    if (!selectedEntityName) {
      setIsLoaded(false);
      return;
    }

    async function checkLoadedStatus() {
      try {
        const status = await getLoadedStatus();
        setIsLoaded(status.protocols.includes(selectedEntityName!));
      } catch {
        // ignore
      }
    }

    checkLoadedStatus();
  }, [selectedEntityName]);

  // Handle load
  const handleLoad = useCallback(async () => {
    if (!selectedPackage || !selectedEntityName) return;
    setIsLoading(true);
    try {
      const result = await loadEntity('protocols', selectedEntityName);
      if (result.success) {
        setIsLoaded(true);
        onReload?.();
      } else {
        alert(result.error || 'Failed to load protocol');
      }
    } catch {
      alert('Failed to load protocol');
    } finally {
      setIsLoading(false);
    }
  }, [selectedPackage, selectedEntityName, onReload]);

  // Handle unload
  const handleUnload = useCallback(async () => {
    if (!selectedPackage || !selectedEntityName) return;
    setIsUnloading(true);
    try {
      const result = await unloadEntity('protocols', selectedEntityName);
      if (result.success) {
        setIsLoaded(false);
        onReload?.();
      } else {
        alert(result.error || 'Failed to unload protocol');
      }
    } catch {
      alert('Failed to unload protocol');
    } finally {
      setIsUnloading(false);
    }
  }, [selectedPackage, selectedEntityName, onReload]);

  // Handle reload
  const handleReload = useCallback(async () => {
    if (!selectedPackage || !selectedEntityName) return;
    setIsReloading(true);
    try {
      const result = await reloadEntity('protocols', selectedEntityName);
      if (result.success) onReload?.();
      else alert(result.error || 'Failed to reload protocol');
    } catch {
      alert('Failed to reload protocol');
    } finally {
      setIsReloading(false);
    }
  }, [selectedPackage, selectedEntityName, onReload]);

  // -----------------------------------------------------------------------
  // Serialize effect: protocol state → yaml/layout (ONE direction only)
  // No effect watches yaml→protocol, so no loop is possible.
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (tasks.length === 0 && !protocolType) return;

    const { yaml, layoutJson } = serializeCurrentProtocol();

    const state = useEditorStore.getState();
    if (yaml !== state.yaml) updateYaml(yaml);
    if (layoutJson !== state.layout) updateLayout(layoutJson);
  }, [tasks, taskTemplates, protocolType, protocolDesc, labs, updateYaml, updateLayout]);

  // Show warning if Jinja detected
  if (hasJinja) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-white dark:bg-gray-900 p-8">
        <AlertTriangle className="w-16 h-16 text-yellow-500 mb-4" />
        <h3 className="text-xl font-semibold mb-2">Jinja Template Detected</h3>
        <p className="text-gray-600 dark:text-gray-400 text-center mb-4">
          This protocol contains Jinja2 template syntax. Visual editing is disabled to prevent corruption.
        </p>
        <button
          onClick={onSwitchToCode}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 dark:bg-yellow-500 text-white dark:text-slate-900 rounded hover:bg-blue-700 dark:hover:bg-yellow-600"
        >
          <Code className="w-4 h-4" />
          Switch to Code Editor
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-gray-900 dark:text-white">Protocol: {selectedEntityName}</span>
          <div className="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-500">
            <span>{selectedPackage}</span>
            <span>/</span>
            <span>protocols</span>
            <span>/</span>
            <span>{selectedEntityName}</span>
          </div>
          {isDirty && <span className="text-xs text-orange-600 dark:text-orange-400">● Unsaved</span>}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onSwitchToCode}
            className="flex items-center gap-2 px-3 py-1.5 text-sm rounded hover:bg-gray-100 dark:hover:bg-gray-800"
            title="Switch to code editor"
          >
            <Code className="w-4 h-4" />
            Code
          </button>

          {!isLoaded && (
            <button
              onClick={handleLoad}
              disabled={isLoading || !isConnected}
              className="flex items-center gap-2 px-3 py-1.5 text-sm rounded hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
              title="Load protocol"
            >
              <Download className={`w-4 h-4 ${isLoading ? 'animate-pulse' : ''}`} />
              Load
            </button>
          )}

          {isLoaded && (
            <button
              onClick={handleUnload}
              disabled={isUnloading || !isConnected}
              className="flex items-center gap-2 px-3 py-1.5 text-sm rounded hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
              title="Unload protocol"
            >
              <Upload className={`w-4 h-4 ${isUnloading ? 'animate-pulse' : ''}`} />
              Unload
            </button>
          )}

          {isLoaded && (
            <button
              onClick={handleReload}
              disabled={isReloading || !isConnected}
              className="flex items-center gap-2 px-3 py-1.5 text-sm rounded hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
              title="Reload protocol from disk"
            >
              <RefreshCw className={`w-4 h-4 ${isReloading ? 'animate-spin' : ''}`} />
              Reload
            </button>
          )}

          <button
            onClick={() => onSave()}
            disabled={!isDirty}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-blue-600 dark:bg-yellow-500 text-white dark:text-slate-900 rounded hover:bg-blue-700 dark:hover:bg-yellow-600 disabled:opacity-50 disabled:cursor-not-allowed"
            title="Save (Cmd/Ctrl+S)"
          >
            <Save className="w-4 h-4" />
            Save
          </button>
        </div>
      </div>

      <DiskChangedBanner onReload={onReload} />

      {/* Visual Editor */}
      <div className="flex-1 overflow-hidden">
        <ProtocolEditor />
      </div>
    </div>
  );
}
