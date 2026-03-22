'use client';

import { useEffect, useCallback, useRef } from 'react';
import dynamic from 'next/dynamic';
import { Panel, Group, Separator } from 'react-resizable-panels';
import { Skeleton } from '@/components/ui/Skeleton';
import { PackageFileTree } from './PackageFileTree';

function EditorPanelSkeleton() {
  return (
    <div className="flex-1 flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-gray-700">
        <Skeleton className="h-4 w-48" />
        <div className="flex items-center gap-2">
          <Skeleton className="h-8 w-20" />
          <Skeleton className="h-8 w-20" />
        </div>
      </div>
      <div className="flex items-center gap-1 px-4 py-1 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
        <Skeleton className="h-7 w-24" />
        <Skeleton className="h-7 w-24" />
      </div>
      <div className="flex-1 p-4 space-y-2">
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-11/12" />
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-10/12" />
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-9/12" />
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-11/12" />
      </div>
    </div>
  );
}

const CodeEditorPanel = dynamic(() => import('./CodeEditorPanel').then((m) => m.CodeEditorPanel), {
  ssr: false,
  loading: () => <EditorPanelSkeleton />,
});

const VisualExperimentEditorWithProvider = dynamic(
  () => import('./VisualExperimentEditorWithProvider').then((m) => m.VisualExperimentEditorWithProvider),
  { ssr: false, loading: () => <EditorPanelSkeleton /> }
);
import { ToastContainer } from '@/components/ui/Toast';
import { useToast } from '@/components/ui/useToast';
import { useEditorStore } from '@/lib/stores/editorStore';
import { hasJinjaSyntax, parseYaml, extractHoldsFromRawTasks } from '@/lib/utils/editor-utils';
import { refreshPackages } from '@/features/editor/api/refresh';
import { serializeCurrentExperiment } from '@/lib/utils/experimentSerializer';
import { autoLayoutTasks } from '@/lib/utils/autoLayout';
import type { Package, EntityTree, EntityFiles, EntityType } from '@/lib/types/filesystem';
import type { TaskSpec, TaskNode, ExperimentDefinition } from '@/lib/types/experiment';
import type { LabSpec } from '@/lib/api/specs';
import type { EditorMode } from '@/lib/stores/editorStore';

interface InitialSelection {
  packageName: string;
  entityType: EntityType;
  entityName: string;
  editorMode?: EditorMode;
}

interface EditorClientProps {
  initialPackages: Package[];
  taskSpecs: TaskSpec[];
  labSpecs: Record<string, LabSpec>;
  initialSelection?: InitialSelection;
}

/**
 * Parse YAML, apply layout positions, load experiment fields, serialize back
 * (round-trip normalization), and update baseline so no false dirty.
 */
function loadVisualEditor() {
  const state = useEditorStore.getState();
  const { yaml, layout: layoutStr, python, selectedEntityName } = state;

  if (!yaml) {
    // Empty file — bootstrap with entity name as type
    const entityName = selectedEntityName || '';
    useEditorStore.getState().loadExperiment({ type: entityName, desc: '', labs: [], tasks: [] });
    // Clear history since this is a fresh load
    useEditorStore.setState({ past: [], future: [] });
    const { yaml: normalizedYaml, layoutJson: normalizedLayout } = serializeCurrentExperiment();
    useEditorStore.getState().setBaseline(normalizedYaml, python, normalizedLayout);
    return;
  }

  const { data, error } = parseYaml(yaml);
  if (error || !data) return;

  const typedData = data as { type?: string; tasks?: TaskNode[]; desc?: string; labs?: string[] };

  // Extract hold flags from raw YAML assignments into separate device_holds/resource_holds maps
  if (typedData.tasks) {
    typedData.tasks = extractHoldsFromRawTasks(
      typedData.tasks as unknown as Record<string, unknown>[]
    ) as unknown as TaskNode[];
  }

  // Ensure experiment type matches entity name
  if (selectedEntityName && typedData.type !== selectedEntityName) {
    typedData.type = selectedEntityName;
  }

  // Parse layout or auto-layout
  let layoutMap: Record<string, { x: number; y: number }> = {};
  if (layoutStr) {
    try {
      layoutMap = JSON.parse(layoutStr);
    } catch {
      // Invalid layout — will get default positions
    }
  } else if (typedData.tasks?.length) {
    layoutMap = autoLayoutTasks(typedData.tasks as TaskNode[]);
  }

  // Apply positions to tasks
  if (typedData.tasks) {
    typedData.tasks = typedData.tasks.map((task: TaskNode) => ({
      ...task,
      position: layoutMap[task.name] || { x: 100, y: 100 },
    }));
  }

  // Load experiment fields
  useEditorStore.getState().loadExperiment(typedData as ExperimentDefinition);
  // Clear history since this is a fresh load
  useEditorStore.setState({ past: [], future: [] });

  // Round-trip normalization
  const { yaml: normalizedYaml, layoutJson: normalizedLayout } = serializeCurrentExperiment();

  // Only normalize baseline if not dirty (no cached changes)
  if (!useEditorStore.getState().isDirty) {
    useEditorStore.getState().setBaseline(normalizedYaml, useEditorStore.getState().python, normalizedLayout);
  }
}

export function EditorClient({ initialPackages, taskSpecs, labSpecs, initialSelection }: EditorClientProps) {
  const selectedPackage = useEditorStore((s) => s.selectedPackage);
  const selectedEntityType = useEditorStore((s) => s.selectedEntityType);
  const selectedEntityName = useEditorStore((s) => s.selectedEntityName);
  const editorMode = useEditorStore((s) => s.editorMode);
  const yaml = useEditorStore((s) => s.yaml);

  const selectEntity = useEditorStore((s) => s.selectEntity);
  const setPackages = useEditorStore((s) => s.setPackages);
  const setEntityTree = useEditorStore((s) => s.setEntityTree);
  const setEditorMode = useEditorStore((s) => s.setEditorMode);
  const markSaved = useEditorStore((s) => s.markSaved);
  const setLoading = useEditorStore((s) => s.setLoading);
  const setError = useEditorStore((s) => s.setError);
  const clearSelection = useEditorStore((s) => s.clearSelection);
  const setIsSaving = useEditorStore((s) => s.setIsSaving);
  const setTaskTemplates = useEditorStore((s) => s.setTaskTemplates);
  const setLabSpecs = useEditorStore((s) => s.setLabSpecs);
  const refreshSpecs = useEditorStore((s) => s.refreshSpecsIfChanged);

  const { toasts, showToast, closeToast } = useToast();
  const isSyncingUrl = useRef(false);

  // -----------------------------------------------------------------------
  // Fetch helpers
  // -----------------------------------------------------------------------

  const fetchWithError = useCallback(
    async <T,>(url: string, errorMsg: string): Promise<T | null> => {
      try {
        setLoading(true);
        const response = await fetch(url, { cache: 'no-store', headers: { 'Cache-Control': 'no-cache' } });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
      } catch (error) {
        showToast('error', errorMsg);
        setError(error instanceof Error ? error.message : 'Unknown error');
        return null;
      } finally {
        setLoading(false);
      }
    },
    [setLoading, setError, showToast]
  );

  const fetchEntityTree = useCallback(
    async (packageName: string) => {
      const tree = await fetchWithError<EntityTree>(
        `/api/filesystem/packages/${encodeURIComponent(packageName)}`,
        'Failed to load package entities'
      );
      if (tree) setEntityTree(packageName, tree);
    },
    [fetchWithError, setEntityTree]
  );

  // -----------------------------------------------------------------------
  // Single fetch effect with cancelled flag for race safety
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!selectedPackage || !selectedEntityType || !selectedEntityName) return;

    let cancelled = false;

    async function fetchAndLoad() {
      try {
        const response = await fetch(
          `/api/filesystem/packages/${encodeURIComponent(selectedPackage!)}/${selectedEntityType}/${selectedEntityName}`,
          { cache: 'no-store', headers: { 'Cache-Control': 'no-cache' } }
        );

        if (cancelled) return;

        if (response.status === 404) {
          const cacheKey = `${selectedPackage}/${selectedEntityType}/${selectedEntityName}`;
          useEditorStore.getState().deleteCache(cacheKey);
          clearSelection();
          useEditorStore.getState().resetExperiment();
          showToast('error', `${selectedEntityName} no longer exists on disk`);
          return;
        }

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const files: EntityFiles = await response.json();
        if (cancelled) return;

        const layout = selectedEntityType === 'experiments' && files.json ? files.json : '';
        useEditorStore.getState().loadFromDisk({ yaml: files.yaml, python: files.python, layout });

        // Determine editor mode and load visual editor if needed
        if (selectedEntityType === 'experiments' && !hasJinjaSyntax(files.yaml)) {
          useEditorStore.getState().setEditorMode('visual');
          loadVisualEditor();
        } else {
          useEditorStore.getState().setEditorMode('code');
        }
      } catch (error) {
        if (cancelled) return;
        showToast('error', 'Failed to load entity files');
        setError(error instanceof Error ? error.message : 'Unknown error');
        setLoading(false);
      }
    }

    fetchAndLoad();
    return () => {
      cancelled = true;
    };
  }, [selectedPackage, selectedEntityType, selectedEntityName, clearSelection, setError, setLoading, showToast]);

  // -----------------------------------------------------------------------
  // Initialize packages and specs
  // -----------------------------------------------------------------------

  useEffect(() => {
    setPackages(initialPackages);
    setTaskTemplates(taskSpecs);
    setLabSpecs(labSpecs);
  }, [initialPackages, taskSpecs, labSpecs, setPackages, setTaskTemplates, setLabSpecs]);

  // Fetch entity tree when package is selected
  useEffect(() => {
    if (selectedPackage) fetchEntityTree(selectedPackage);
  }, [selectedPackage, fetchEntityTree]);

  // Refresh specs when window regains focus (catches changes from management page)
  useEffect(() => {
    let lastCheck = 0;
    const DEBOUNCE_MS = 5000;

    const handleFocus = () => {
      const now = Date.now();
      if (now - lastCheck < DEBOUNCE_MS) return;
      lastCheck = now;
      refreshSpecs();
    };

    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [refreshSpecs]);

  // -----------------------------------------------------------------------
  // URL sync
  // -----------------------------------------------------------------------

  const appliedSelectionRef = useRef<string | null>(null);
  useEffect(() => {
    if (!initialSelection) return;

    const { packageName, entityType, entityName, editorMode: mode } = initialSelection;
    const selectionKey = `${packageName}/${entityType}/${entityName}`;
    if (appliedSelectionRef.current === selectionKey) return;
    appliedSelectionRef.current = selectionKey;

    const validEntityTypes: EntityType[] = ['devices', 'tasks', 'labs', 'experiments'];
    if (!validEntityTypes.includes(entityType)) {
      showToast('error', `Invalid entity type: ${entityType}`);
      return;
    }

    isSyncingUrl.current = true;
    selectEntity(packageName, entityType, entityName);
    if (mode && entityType === 'experiments') setEditorMode(mode);
    isSyncingUrl.current = false;
  }, [initialSelection, selectEntity, setEditorMode, showToast]);

  useEffect(() => {
    if (isSyncingUrl.current) return;

    const params = new URLSearchParams();
    if (selectedPackage && selectedEntityType && selectedEntityName) {
      params.set('pkg', selectedPackage);
      params.set('type', selectedEntityType);
      params.set('name', selectedEntityName);
      if (selectedEntityType === 'experiments' && editorMode) params.set('mode', editorMode);
      window.history.pushState(null, '', `/editor?${params.toString()}`);
    } else {
      window.history.pushState(null, '', '/editor');
    }
  }, [selectedPackage, selectedEntityType, selectedEntityName, editorMode]);

  useEffect(() => {
    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search);
      const pkg = params.get('pkg');
      const type = params.get('type');
      const name = params.get('name');
      const mode = params.get('mode');

      if (pkg && type && name) {
        isSyncingUrl.current = true;
        selectEntity(pkg, type as EntityType, name);
        if (mode && type === 'experiments') setEditorMode(mode as EditorMode);
        isSyncingUrl.current = false;
      } else {
        clearSelection();
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [selectEntity, clearSelection, setEditorMode]);

  // -----------------------------------------------------------------------
  // Save
  // -----------------------------------------------------------------------

  const handleSave = useCallback(async () => {
    if (!selectedPackage || !selectedEntityType || !selectedEntityName) return;
    if (useEditorStore.getState().isSaving) return;

    setIsSaving(true);
    try {
      setLoading(true);

      // In visual mode, synchronously derive YAML and layout from experiment state
      const currentMode = useEditorStore.getState().editorMode;
      if (currentMode === 'visual' && selectedEntityType === 'experiments') {
        const { yaml: serializedYaml, layoutJson: serializedLayout } = serializeCurrentExperiment();
        useEditorStore.getState().updateYaml(serializedYaml);
        useEditorStore.getState().updateLayout(serializedLayout);
      }

      const state = useEditorStore.getState();
      const body: Record<string, string> = { yaml: state.yaml, python: state.python };

      if (selectedEntityType === 'experiments' && state.layout) {
        body.json = state.layout;
      }

      const response = await fetch(
        `/api/filesystem/packages/${encodeURIComponent(selectedPackage)}/${selectedEntityType}/${selectedEntityName}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      );

      if (!response.ok) throw new Error('Failed to save files');

      markSaved();
      showToast('success', 'Saved successfully');
    } catch (error) {
      console.error('Error saving files:', error);
      showToast('error', 'Failed to save files');
    } finally {
      setIsSaving(false);
      setLoading(false);
    }
  }, [selectedPackage, selectedEntityType, selectedEntityName, setIsSaving, setLoading, markSaved, showToast]);

  const refetchCurrentEntity = useCallback(() => {
    if (selectedPackage && selectedEntityType && selectedEntityName) {
      // Re-trigger the fetch effect by toggling selection
      const pkg = selectedPackage;
      const type = selectedEntityType;
      const name = selectedEntityName;
      // Clear and re-select to trigger the fetch effect
      useEditorStore.setState({ selectedEntityName: null });
      // Use setTimeout to ensure the state change triggers a new effect cycle
      setTimeout(() => selectEntity(pkg, type, name), 0);
    }
    // Also refresh specs in case task/lab definitions changed
    refreshSpecs();
  }, [selectedPackage, selectedEntityType, selectedEntityName, selectEntity, refreshSpecs]);

  // -----------------------------------------------------------------------
  // Entity CRUD
  // -----------------------------------------------------------------------

  const handleCreateEntity = async (packageName: string, entityType: EntityType, entityName: string) => {
    try {
      setLoading(true);
      const response = await fetch(`/api/filesystem/packages/${encodeURIComponent(packageName)}/${entityType}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entityName }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to create entity');
      }

      showToast('success', `Created ${entityName}`);
      await fetchEntityTree(packageName);
      refreshPackages();
    } catch (error) {
      console.error('Error creating entity:', error);
      showToast('error', error instanceof Error ? error.message : 'Failed to create entity');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteEntity = async (packageName: string, entityType: EntityType, entityName: string) => {
    try {
      setLoading(true);
      const response = await fetch(
        `/api/filesystem/packages/${encodeURIComponent(packageName)}/${entityType}/${entityName}`,
        { method: 'DELETE' }
      );

      if (!response.ok) throw new Error('Failed to delete entity');

      showToast('success', `Deleted ${entityName}`);

      const cacheKey = `${packageName}/${entityType}/${entityName}`;
      useEditorStore.getState().deleteCache(cacheKey);

      if (selectedPackage === packageName && selectedEntityType === entityType && selectedEntityName === entityName) {
        clearSelection();
        useEditorStore.getState().resetExperiment();
      }

      await fetchEntityTree(packageName);
      refreshPackages();
    } catch (error) {
      console.error('Error deleting entity:', error);
      showToast('error', 'Failed to delete entity');
    } finally {
      setLoading(false);
    }
  };

  const handleRenameEntity = async (packageName: string, entityType: EntityType, oldName: string, newName: string) => {
    try {
      setLoading(true);

      const oldCacheKey = `${packageName}/${entityType}/${oldName}`;
      const newCacheKey = `${packageName}/${entityType}/${newName}`;
      useEditorStore.getState().renameCache(oldCacheKey, newCacheKey);

      const response = await fetch(
        `/api/filesystem/packages/${encodeURIComponent(packageName)}/${entityType}/${oldName}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ newName }),
        }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to rename entity');
      }

      showToast('success', `Renamed ${oldName} to ${newName}`);

      if (selectedPackage === packageName && selectedEntityType === entityType && selectedEntityName === oldName) {
        useEditorStore.setState({ selectedEntityName: newName });

        if (entityType === 'experiments') {
          useEditorStore.setState({ experimentType: newName });
          const currentYaml = useEditorStore.getState().yaml;
          if (currentYaml) {
            const updatedYaml = currentYaml.replace(/^type:\s*['"]?[^'"#\n]+['"]?/m, `type: ${newName}`);
            useEditorStore.getState().updateYaml(updatedYaml);
          }
        }
      }

      fetchEntityTree(packageName);
      refreshPackages();
    } catch (error) {
      console.error('Error renaming entity:', error);
      showToast('error', error instanceof Error ? error.message : 'Failed to rename entity');
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshPackages = useCallback(async () => {
    const packages = await fetchWithError<Package[]>('/api/filesystem/packages', 'Failed to refresh packages');
    if (packages) {
      setPackages(packages);
      showToast('success', `Refreshed: ${packages.length} package(s)`);
    }
  }, [fetchWithError, setPackages, showToast]);

  const handleToggleMode = useCallback(() => {
    const newMode = editorMode === 'code' ? 'visual' : 'code';
    setEditorMode(newMode);
    if (newMode === 'visual') loadVisualEditor();
  }, [editorMode, setEditorMode]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  const canUseVisualMode = selectedEntityType === 'experiments' && !hasJinjaSyntax(yaml);
  const isVisualMode = editorMode === 'visual' && canUseVisualMode;

  return (
    <>
      <ToastContainer toasts={toasts} onClose={closeToast} />

      <div className="h-screen flex flex-col">
        <Group orientation="horizontal">
          <Panel defaultSize="15%" minSize="8%" maxSize="25%">
            <PackageFileTree
              onCreateEntity={handleCreateEntity}
              onDeleteEntity={handleDeleteEntity}
              onRenameEntity={handleRenameEntity}
              onRefresh={handleRefreshPackages}
              onPackageExpand={fetchEntityTree}
            />
          </Panel>

          <Separator className="w-1 bg-gray-200 dark:bg-gray-700 hover:bg-blue-500 dark:hover:bg-yellow-500 transition-colors" />

          <Panel defaultSize="85%" minSize="50%">
            {isVisualMode ? (
              <VisualExperimentEditorWithProvider
                hasJinja={hasJinjaSyntax(yaml)}
                onSave={handleSave}
                onReload={refetchCurrentEntity}
                onSwitchToCode={() => setEditorMode('code')}
              />
            ) : (
              <CodeEditorPanel
                onSave={handleSave}
                onReload={refetchCurrentEntity}
                onToggleMode={canUseVisualMode ? handleToggleMode : undefined}
                canUseVisualMode={canUseVisualMode}
                hasJinja={!canUseVisualMode && selectedEntityType === 'experiments'}
              />
            )}
          </Panel>
        </Group>
      </div>
    </>
  );
}
