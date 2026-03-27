'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Editor, { type BeforeMount } from '@monaco-editor/react';
import { Save, CheckCircle, AlertCircle, AlertTriangle, Code, Eye, RefreshCw, Download, Upload } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useEditorStore } from '@/lib/stores/editorStore';
import { validateYaml, entityHasPythonFile } from '@/lib/utils/editor-utils';
import { loadEntity, unloadEntity, reloadEntity } from '@/features/editor/api/reload';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';
import { getLoadedStatus } from '@/features/editor/api/loaded-status';
import { ENTITY_FILE_NAMES } from '@/lib/types/filesystem';
import type { editor } from 'monaco-editor';

interface CodeEditorPanelProps {
  onSave: () => void;
  onReload?: () => void;
  onToggleMode?: () => void;
  canUseVisualMode?: boolean;
  hasJinja?: boolean;
}

type FileTab = 'yaml' | 'python';

const BTN_BASE = 'flex items-center gap-2 px-3 py-1.5 text-sm rounded';
const BTN_PRIMARY = `${BTN_BASE} bg-blue-600 dark:bg-yellow-500 text-white dark:text-slate-900 hover:bg-blue-700 dark:hover:bg-yellow-600 disabled:opacity-50 disabled:cursor-not-allowed`;
const BTN_SECONDARY = `${BTN_BASE} hover:bg-gray-100 dark:hover:bg-gray-800`;

export function CodeEditorPanel({ onSave, onReload, onToggleMode, canUseVisualMode, hasJinja }: CodeEditorPanelProps) {
  const { resolvedTheme } = useTheme();
  const { isConnected } = useOrchestratorConnected();
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);

  const selectedPackage = useEditorStore((state) => state.selectedPackage);
  const selectedEntityType = useEditorStore((state) => state.selectedEntityType);
  const selectedEntityName = useEditorStore((state) => state.selectedEntityName);
  const yamlContent = useEditorStore((state) => state.yaml);
  const pythonContent = useEditorStore((state) => state.python);
  const updateYamlContent = useEditorStore((state) => state.updateYaml);
  const updatePythonContent = useEditorStore((state) => state.updatePython);
  const hasUnsavedChanges = useEditorStore((state) => state.isDirty);
  const editorMode = useEditorStore((state) => state.editorMode);

  const [activeTab, setActiveTab] = useState<FileTab>('yaml');
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [isReloading, setIsReloading] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isUnloading, setIsUnloading] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);

  const hasPythonFile = selectedEntityType && entityHasPythonFile(selectedEntityType);

  // Check if this entity type supports load/unload
  const supportsLoadUnload =
    selectedEntityType === 'protocols' || selectedEntityType === 'labs' || selectedEntityType === 'devices';

  // Fetch loaded status when entity changes
  useEffect(() => {
    if (!selectedEntityName || !selectedEntityType || !supportsLoadUnload) {
      setIsLoaded(false);
      return;
    }

    async function checkLoadedStatus() {
      try {
        const status = await getLoadedStatus();
        const entityTypeKey = selectedEntityType as 'protocols' | 'labs' | 'devices' | 'tasks';
        const loadedEntities = status[entityTypeKey];
        setIsLoaded(loadedEntities.includes(selectedEntityName!));
      } catch (error) {
        console.error('Failed to check loaded status:', error);
      }
    }

    checkLoadedStatus();
  }, [selectedEntityName, selectedEntityType, supportsLoadUnload]);

  // Reset to YAML tab when switching to an entity without Python file
  useEffect(() => {
    if (!hasPythonFile && activeTab === 'python') {
      setActiveTab('yaml');
    }
  }, [hasPythonFile, activeTab]);

  // Validate YAML when content changes
  useEffect(() => {
    if (activeTab === 'yaml' && yamlContent) {
      const result = validateYaml(yamlContent);
      setValidationErrors(result.errors.map((e) => e.message));
    } else {
      setValidationErrors([]);
    }
  }, [yamlContent, activeTab]);

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        if (hasUnsavedChanges) {
          onSave();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [hasUnsavedChanges, onSave]);

  const handleEditorDidMount = useCallback((editor: editor.IStandaloneCodeEditor) => {
    editorRef.current = editor;
  }, []);

  // Clear editor ref on unmount and when switching files
  useEffect(() => {
    editorRef.current = null;
    return () => {
      editorRef.current = null;
    };
  }, [selectedEntityName, activeTab]);

  const handleEditorChange = useCallback(
    (value: string | undefined) => {
      if (value === undefined) return;
      if (activeTab === 'yaml') {
        updateYamlContent(value);
      } else {
        updatePythonContent(value);
      }
    },
    [activeTab, updateYamlContent, updatePythonContent]
  );

  const handleEditorWillMount: BeforeMount = useCallback((monaco) => {
    // Define custom dark theme with dark blue background matching the web UI
    monaco.editor.defineTheme('dark-blue', {
      base: 'vs-dark',
      inherit: true,
      rules: [],
      colors: {
        'editor.background': '#111827', // Tailwind gray-900
        'editor.lineHighlightBackground': '#1f2937', // Tailwind gray-800
        'editorGutter.background': '#111827',
        'editorLineNumber.foreground': '#6b7280', // Tailwind gray-500
        'editorLineNumber.activeForeground': '#9ca3af', // Tailwind gray-400
      },
    });
  }, []);

  const handleLoad = useCallback(async () => {
    if (!selectedPackage || !selectedEntityType || !selectedEntityName) return;

    setIsLoading(true);
    try {
      const result = await loadEntity(selectedEntityType, selectedEntityName);
      if (result.success) {
        setIsLoaded(true);
        if (onReload) {
          onReload();
        }
      } else {
        alert(result.error || 'Failed to load entity');
      }
    } catch (error) {
      console.error('Error loading entity:', error);
      alert('Failed to load entity');
    } finally {
      setIsLoading(false);
    }
  }, [selectedPackage, selectedEntityType, selectedEntityName, onReload]);

  const handleUnload = useCallback(async () => {
    if (!selectedPackage || !selectedEntityType || !selectedEntityName) return;

    setIsUnloading(true);
    try {
      const result = await unloadEntity(selectedEntityType, selectedEntityName);
      if (result.success) {
        setIsLoaded(false);
        if (onReload) {
          onReload();
        }
      } else {
        alert(result.error || 'Failed to unload entity');
      }
    } catch (error) {
      console.error('Error unloading entity:', error);
      alert('Failed to unload entity');
    } finally {
      setIsUnloading(false);
    }
  }, [selectedPackage, selectedEntityType, selectedEntityName, onReload]);

  const handleReload = useCallback(async () => {
    if (!selectedPackage || !selectedEntityType || !selectedEntityName) return;

    setIsReloading(true);
    try {
      const result = await reloadEntity(selectedEntityType, selectedEntityName);
      if (result.success) {
        // Re-fetch entity files to get any changes from disk
        if (onReload) {
          onReload();
        }
      } else {
        alert(result.error || 'Failed to reload entity');
      }
    } catch (error) {
      console.error('Error reloading entity:', error);
      alert('Failed to reload entity');
    } finally {
      setIsReloading(false);
    }
  }, [selectedPackage, selectedEntityType, selectedEntityName, onReload]);

  const currentContent = activeTab === 'yaml' ? yamlContent : pythonContent;
  const currentLanguage = activeTab === 'yaml' ? 'yaml' : 'python';

  if (!selectedEntityName) {
    return (
      <div className="h-full flex items-center justify-center bg-white dark:bg-gray-900">
        <div className="text-center text-gray-500 dark:text-gray-400">
          <Code className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p className="text-lg">Select an entity to edit</p>
        </div>
      </div>
    );
  }

  if (editorMode === 'visual' && canUseVisualMode) {
    return null; // Visual editor will be rendered instead
  }

  const fileNames = selectedEntityType ? ENTITY_FILE_NAMES[selectedEntityType] : null;

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
            <span className="font-medium">{selectedPackage}</span>
            <span>/</span>
            <span>{selectedEntityType}</span>
            <span>/</span>
            <span className="font-medium">{selectedEntityName}</span>
          </div>
          {hasUnsavedChanges && <span className="text-xs text-orange-600 dark:text-orange-400">● Unsaved</span>}
        </div>

        <div className="flex items-center gap-2">
          {/* Validation Status */}
          {activeTab === 'yaml' && (
            <>
              {validationErrors.length === 0 ? (
                <div className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                  <CheckCircle className="w-4 h-4" />
                  Valid
                </div>
              ) : (
                <div
                  className="flex items-center gap-1 text-xs text-red-600 dark:text-red-400"
                  title={validationErrors.join('\n')}
                >
                  <AlertCircle className="w-4 h-4" />
                  {validationErrors.length} error{validationErrors.length > 1 ? 's' : ''}
                </div>
              )}
            </>
          )}

          {/* Visual Mode Toggle */}
          {canUseVisualMode && (
            <button onClick={onToggleMode} className={BTN_SECONDARY} title="Switch to visual editor">
              <Eye className="w-4 h-4" />
              Visual
            </button>
          )}

          {/* Load/Unload Buttons (for entities that support it) */}
          {supportsLoadUnload && !isLoaded && (
            <button
              onClick={handleLoad}
              disabled={isLoading || !isConnected}
              className={BTN_SECONDARY}
              title="Load entity"
            >
              <Download className={`w-4 h-4 ${isLoading ? 'animate-pulse' : ''}`} />
              Load
            </button>
          )}

          {supportsLoadUnload && isLoaded && (
            <button
              onClick={handleUnload}
              disabled={isUnloading || !isConnected}
              className={BTN_SECONDARY}
              title="Unload entity"
            >
              <Upload className={`w-4 h-4 ${isUnloading ? 'animate-pulse' : ''}`} />
              Unload
            </button>
          )}

          {/* Reload Button (only show for loaded entities or tasks) */}
          {(isLoaded || !supportsLoadUnload) && (
            <button
              onClick={handleReload}
              disabled={isReloading || !isConnected}
              className={BTN_SECONDARY}
              title="Reload entity from disk"
            >
              <RefreshCw className={`w-4 h-4 ${isReloading ? 'animate-spin' : ''}`} />
              Reload
            </button>
          )}

          {/* Save Button */}
          <button onClick={onSave} disabled={!hasUnsavedChanges} className={BTN_PRIMARY} title="Save (Cmd/Ctrl+S)">
            <Save className="w-4 h-4" />
            Save
          </button>
        </div>
      </div>

      {/* Jinja Warning Banner */}
      {hasJinja && (
        <div className="flex items-center gap-2 px-4 py-2 border-b border-yellow-300 dark:border-yellow-700 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-200 text-sm">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          This protocol contains Jinja2 template syntax. Use the code editor &mdash; visual editing is disabled to
          prevent template corruption.
        </div>
      )}

      {/* Tab Bar */}
      {fileNames && (
        <div className="flex items-center gap-1 px-4 py-1 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <button
            onClick={() => setActiveTab('yaml')}
            className={`px-3 py-1 text-sm rounded ${
              activeTab === 'yaml'
                ? 'bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700'
                : 'hover:bg-gray-100 dark:hover:bg-gray-700'
            }`}
          >
            {fileNames.yaml}
          </button>

          {hasPythonFile && (
            <button
              onClick={() => setActiveTab('python')}
              className={`px-3 py-1 text-sm rounded ${
                activeTab === 'python'
                  ? 'bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700'
                  : 'hover:bg-gray-100 dark:hover:bg-gray-700'
              }`}
            >
              {fileNames.python}
            </button>
          )}
        </div>
      )}

      {/* Editor */}
      <div className="flex-1 overflow-hidden">
        <Editor
          key={`${selectedEntityName}-${activeTab}`}
          height="100%"
          language={currentLanguage}
          value={currentContent}
          onChange={handleEditorChange}
          onMount={handleEditorDidMount}
          beforeMount={handleEditorWillMount}
          theme={resolvedTheme === 'dark' ? 'dark-blue' : 'light'}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: 'on',
            rulers: [120],
            wordWrap: 'on',
            scrollBeyondLastLine: false,
            automaticLayout: true,
            tabSize: 2,
            insertSpaces: true,
          }}
        />
      </div>

      {/* Validation Errors Panel */}
      {validationErrors.length > 0 && activeTab === 'yaml' && (
        <div className="border-t border-gray-200 dark:border-gray-700 bg-red-50 dark:bg-red-900/20 px-4 py-2">
          <div className="text-xs font-medium text-red-800 dark:text-red-200 mb-1">Validation Errors:</div>
          {validationErrors.map((error, idx) => (
            <div key={idx} className="text-xs text-red-700 dark:text-red-300">
              • {error}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
