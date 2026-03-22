'use client';

import { useEffect, useState, useCallback } from 'react';
import { Save, Code, AlertTriangle, RefreshCw, Download, Upload } from 'lucide-react';
import { ExperimentEditor } from '@/features/experiment-editor/components/ExperimentEditor';
import { useEditorStore } from '@/lib/stores/editorStore';
import { serializeCurrentExperiment } from '@/lib/utils/experimentSerializer';
import { loadEntity, unloadEntity, reloadEntity } from '@/features/editor/api/reload';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';
import { getLoadedStatus } from '@/features/editor/api/loaded-status';

interface VisualExperimentEditorProps {
  hasJinja: boolean;
  onSave: () => void | Promise<void>;
  onReload?: () => void;
  onSwitchToCode: () => void;
}

export function VisualExperimentEditor({ hasJinja, onSave, onReload, onSwitchToCode }: VisualExperimentEditorProps) {
  const selectedPackage = useEditorStore((s) => s.selectedPackage);
  const selectedEntityName = useEditorStore((s) => s.selectedEntityName);
  const isDirty = useEditorStore((s) => s.isDirty);
  const updateYaml = useEditorStore((s) => s.updateYaml);
  const updateLayout = useEditorStore((s) => s.updateLayout);

  const tasks = useEditorStore((s) => s.tasks);
  const taskTemplates = useEditorStore((s) => s.taskTemplates);
  const experimentType = useEditorStore((s) => s.experimentType);
  const experimentDesc = useEditorStore((s) => s.experimentDesc);
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
        setIsLoaded(status.experiments.includes(selectedEntityName!));
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
      const result = await loadEntity('experiments', selectedEntityName);
      if (result.success) {
        setIsLoaded(true);
        onReload?.();
      } else {
        alert(result.error || 'Failed to load experiment');
      }
    } catch {
      alert('Failed to load experiment');
    } finally {
      setIsLoading(false);
    }
  }, [selectedPackage, selectedEntityName, onReload]);

  // Handle unload
  const handleUnload = useCallback(async () => {
    if (!selectedPackage || !selectedEntityName) return;
    setIsUnloading(true);
    try {
      const result = await unloadEntity('experiments', selectedEntityName);
      if (result.success) {
        setIsLoaded(false);
        onReload?.();
      } else {
        alert(result.error || 'Failed to unload experiment');
      }
    } catch {
      alert('Failed to unload experiment');
    } finally {
      setIsUnloading(false);
    }
  }, [selectedPackage, selectedEntityName, onReload]);

  // Handle reload
  const handleReload = useCallback(async () => {
    if (!selectedPackage || !selectedEntityName) return;
    setIsReloading(true);
    try {
      const result = await reloadEntity('experiments', selectedEntityName);
      if (result.success) onReload?.();
      else alert(result.error || 'Failed to reload experiment');
    } catch {
      alert('Failed to reload experiment');
    } finally {
      setIsReloading(false);
    }
  }, [selectedPackage, selectedEntityName, onReload]);

  // -----------------------------------------------------------------------
  // Serialize effect: experiment state → yaml/layout (ONE direction only)
  // No effect watches yaml→experiment, so no loop is possible.
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (tasks.length === 0 && !experimentType) return;

    const { yaml, layoutJson } = serializeCurrentExperiment();

    const state = useEditorStore.getState();
    if (yaml !== state.yaml) updateYaml(yaml);
    if (layoutJson !== state.layout) updateLayout(layoutJson);
  }, [tasks, taskTemplates, experimentType, experimentDesc, labs, updateYaml, updateLayout]);

  // Show warning if Jinja detected
  if (hasJinja) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-white dark:bg-gray-900 p-8">
        <AlertTriangle className="w-16 h-16 text-yellow-500 mb-4" />
        <h3 className="text-xl font-semibold mb-2">Jinja Template Detected</h3>
        <p className="text-gray-600 dark:text-gray-400 text-center mb-4">
          This experiment contains Jinja2 template syntax. Visual editing is disabled to prevent corruption.
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
          <span className="text-sm font-semibold text-gray-900 dark:text-white">Experiment: {selectedEntityName}</span>
          <div className="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-500">
            <span>{selectedPackage}</span>
            <span>/</span>
            <span>experiments</span>
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
              title="Load experiment"
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
              title="Unload experiment"
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
              title="Reload experiment from disk"
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

      {/* Visual Editor */}
      <div className="flex-1 overflow-hidden">
        <ExperimentEditor />
      </div>
    </div>
  );
}
