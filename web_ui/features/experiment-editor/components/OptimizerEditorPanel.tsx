'use client';

import { useEffect, useState } from 'react';
import { X, AlertTriangle, Loader2 } from 'lucide-react';
import { useEditorStore } from '@/lib/stores/editorStore';
import { BeaconOptimizerPanel } from '@/features/campaigns/components/BeaconOptimizerPanel';
import type { DomainValue } from '@/features/campaigns/components/DomainEditor';
import { getOptimizerDefaults } from '@/features/campaigns/api/optimizer';
import {
  isStandardOptimizerPy,
  generateOptimizerPython,
  buildOptimizerConfig,
  parseOptimizerPython,
} from '../utils/optimizerCodegen';
import { serializeCurrentExperiment } from '@/lib/utils/experimentSerializer';
import type { OptimizerDefaults } from '@/lib/types/api';

/**
 * Save the Python (optimizer.py) file to disk along with the current YAML and layout.
 * Uses current content (not originals) to avoid overwriting unsaved YAML changes.
 */
async function savePythonOnly(code: string) {
  const store = useEditorStore.getState();
  const { selectedPackage, selectedEntityType, selectedEntityName, isSaving } = store;

  if (!selectedPackage || !selectedEntityType || !selectedEntityName) return;
  if (isSaving) return;

  useEditorStore.getState().setIsSaving(true);
  try {
    let yamlToWrite = store.yaml;
    let layoutToWrite = store.layout;

    if (store.editorMode === 'visual') {
      const serialized = serializeCurrentExperiment();
      yamlToWrite = serialized.yaml;
      layoutToWrite = serialized.layoutJson;
      useEditorStore.getState().updateYaml(yamlToWrite);
      useEditorStore.getState().updateLayout(layoutToWrite);
    }

    const body: Record<string, string> = { yaml: yamlToWrite, python: code };

    if (selectedEntityType === 'experiments' && layoutToWrite) {
      body.json = layoutToWrite;
    }

    const response = await fetch(
      `/api/filesystem/packages/${encodeURIComponent(selectedPackage)}/${selectedEntityType}/${selectedEntityName}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }
    );

    if (!response.ok) throw new Error('Failed to save optimizer file');

    useEditorStore.getState().markSaved();
  } finally {
    useEditorStore.getState().setIsSaving(false);
  }
}

export function OptimizerEditorPanel() {
  const experimentType = useEditorStore((state) => state.experimentType);
  const setIsOptimizerPanelOpen = useEditorStore((state) => state.setIsOptimizerPanelOpen);
  const pythonContent = useEditorStore((state) => state.python);
  const updatePythonContent = useEditorStore((state) => state.updatePython);

  const [defaults, setDefaults] = useState<OptimizerDefaults | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load optimizer config: try local pythonContent first, fall back to orchestrator API
  useEffect(() => {
    // Tier 1: Parse from local pythonContent (works for unsaved experiments)
    if (pythonContent && isStandardOptimizerPy(pythonContent)) {
      const parsed = parseOptimizerPython(pythonContent);
      if (parsed) {
        setDefaults(parsed);
        setError(null);
        setIsLoading(false);
        return;
      }
    }

    // Tier 2: Fall back to orchestrator API
    if (!experimentType) {
      setError('No optimizer configuration found. Use the AI assistant or code editor to create one.');
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    getOptimizerDefaults(experimentType).then((result) => {
      if (cancelled) return;
      if (result) {
        setDefaults(result);
      } else {
        setError('Failed to load optimizer defaults. Make sure the experiment is saved and loaded.');
      }
      setIsLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [experimentType, pythonContent]);

  const isBeacon = !pythonContent || pythonContent.includes('BeaconOptimizer');
  const isStandard = isBeacon && isStandardOptimizerPy(pythonContent);

  const handleSave = async (values: Record<string, unknown>, domain: DomainValue) => {
    const config = buildOptimizerConfig(values, domain);
    const code = generateOptimizerPython(config);
    updatePythonContent(code);

    try {
      await savePythonOnly(code);
    } catch (err) {
      console.error('Failed to save optimizer.py:', err);
    }
  };

  return (
    <div className="h-full flex flex-col bg-white dark:bg-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-slate-700">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Beacon Optimizer</h2>
        <button
          onClick={() => setIsOptimizerPanelOpen(false)}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
            <span className="ml-2 text-sm text-gray-500">Loading optimizer config...</span>
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md">
            <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
          </div>
        )}

        {!isLoading && !error && !isBeacon && (
          <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-md">
            <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-amber-700 dark:text-amber-400">
              Visual optimizer setup is only available for Beacon. This experiment uses a different optimizer. Please
              edit the code manually.
            </p>
          </div>
        )}

        {!isLoading && !error && isBeacon && !isStandard && (
          <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-md">
            <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-amber-700 dark:text-amber-400">
              Non-standard Beacon configuration detected. Please edit the code manually.
            </p>
          </div>
        )}

        {!isLoading && !error && isStandard && defaults && (
          <BeaconOptimizerPanel key={JSON.stringify(defaults)} mode="editor" defaults={defaults} onSave={handleSave} />
        )}
      </div>
    </div>
  );
}
