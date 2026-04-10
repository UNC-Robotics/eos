import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { Package, EntityTree, EntityType } from '@/lib/types/filesystem';
import type { TaskNode, TaskSpec, ProtocolDefinition } from '@/lib/types/protocol';
import type { LabSpec } from '@/lib/api/specs';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type EditorMode = 'code' | 'visual';

interface CachedFiles {
  yaml: string;
  python: string;
  layout: string;
}

interface ProtocolState {
  protocolType: string;
  protocolDesc: string;
  labs: string[];
  tasks: TaskNode[];
  nextTaskNumber: number;
}

// ---------------------------------------------------------------------------
// Store interface
// ---------------------------------------------------------------------------

interface EditorStore {
  // --- Editor slice (file I/O, selection, cache) ---
  packages: Package[];
  selectedPackage: string | null;
  selectedEntityType: EntityType | null;
  selectedEntityName: string | null;
  entityTrees: Record<string, EntityTree>;

  yaml: string;
  python: string;
  layout: string;
  baselineYaml: string;
  baselinePython: string;
  baselineLayout: string;

  cache: Record<string, CachedFiles>;

  editorMode: EditorMode;
  isDirty: boolean;
  isSaving: boolean;
  isLoading: boolean;
  error: string | null;

  // --- File sync state (not persisted) ---
  diskMtime: number | null;
  diskChanged: boolean;
  conflictMtime: number | null;

  // --- ProtocolRun slice (visual editor state) ---
  protocolType: string;
  protocolDesc: string;
  labs: string[];
  tasks: TaskNode[];
  nextTaskNumber: number;

  past: ProtocolState[];
  future: ProtocolState[];

  taskTemplates: TaskSpec[];
  labSpecs: Record<string, LabSpec>;
  specTimestamps: Record<string, string>;

  selectedNodeName: string | null;
  clipboard: TaskNode[];
  viewport: { x: number; y: number; zoom: number };

  isPropertiesPanelOpen: boolean;
  isOptimizerPanelOpen: boolean;

  isBatchOperation: boolean;
  overlapResolutionRequested: boolean;
  needsOverlapResolution: boolean;

  // --- Validation state ---
  validationErrors: Array<{ task: string | null; message: string }>;
  taskValidationErrors: Record<string, string[]>;
  isValidating: boolean;
  isValid: boolean | null; // null = not yet validated
  isValidationPanelOpen: boolean;

  // --- Editor actions ---
  setPackages: (packages: Package[]) => void;
  setEntityTree: (packageName: string, tree: EntityTree) => void;
  getEntityTree: (packageName: string) => EntityTree | undefined;
  selectEntity: (packageName: string, entityType: EntityType, entityName: string) => void;
  loadFromDisk: (files: { yaml: string; python: string; layout?: string; mtime?: number }) => void;
  setBaseline: (yaml: string, python: string, layout: string) => void;
  updateYaml: (content: string) => void;
  updatePython: (content: string) => void;
  updateLayout: (content: string) => void;
  setEditorMode: (mode: EditorMode) => void;
  setIsSaving: (saving: boolean) => void;
  markSaved: (newMtime?: number) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setDiskMtime: (mtime: number) => void;
  setDiskChanged: (changed: boolean) => void;
  setConflictMtime: (mtime: number | null) => void;
  reset: () => void;
  clearSelection: () => void;
  hasUnsavedFile: (key: string) => boolean;
  deleteCache: (key: string) => void;
  renameCache: (oldKey: string, newKey: string) => void;

  // --- ProtocolRun actions ---
  setProtocolType: (type: string) => void;
  setProtocolDesc: (desc: string) => void;
  setLabs: (labs: string[]) => void;
  addTask: (task: TaskNode) => void;
  updateTask: (taskName: string, updates: Partial<TaskNode>) => void;
  deleteTask: (taskName: string) => void;
  setSelectedNodeName: (nodeName: string | null) => void;
  setIsPropertiesPanelOpen: (isOpen: boolean) => void;
  setIsOptimizerPanelOpen: (isOpen: boolean) => void;
  setTaskTemplates: (templates: TaskSpec[]) => void;
  mergeTaskTemplates: (templates: Record<string, TaskSpec>) => void;
  setLabSpecs: (labSpecs: Record<string, LabSpec>) => void;
  mergeLabSpecs: (specs: Record<string, LabSpec>) => void;
  refreshSpecsIfChanged: () => Promise<boolean>;
  resetProtocol: () => void;
  loadProtocol: (protocol: ProtocolDefinition) => void;
  exportProtocol: () => ProtocolDefinition;
  getNextTaskName: () => string;
  copyNodes: (nodeNames: string[]) => void;
  pasteNodes: (position: { x: number; y: number }) => string[];
  setViewport: (viewport: { x: number; y: number; zoom: number }) => void;
  batchOperation: (operation: () => void) => void;
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  // --- Validation actions ---
  setValidationResult: (result: { valid: boolean; errors: Array<{ task: string | null; message: string }> }) => void;
  setIsValidating: (validating: boolean) => void;
  setIsValidationPanelOpen: (open: boolean) => void;
  clearValidation: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const getCacheKey = (
  packageName: string | null,
  entityType: EntityType | null,
  entityName: string | null
): string | null => {
  if (!packageName || !entityType || !entityName) return null;
  return `${packageName}/${entityType}/${entityName}`;
};

const computeDirty = (
  yaml: string,
  python: string,
  layout: string,
  baselineYaml: string,
  baselinePython: string,
  baselineLayout: string
): boolean => yaml !== baselineYaml || python !== baselinePython || layout !== baselineLayout;

const MAX_HISTORY_SIZE = 64;

const getCurrentProtocolState = (state: EditorStore): ProtocolState => ({
  protocolType: state.protocolType,
  protocolDesc: state.protocolDesc,
  labs: state.labs,
  tasks: state.tasks,
  nextTaskNumber: state.nextTaskNumber,
});

/**
 * Reconcile task nodes with current task specs.
 * Removes stale parameters, devices, and resources that no longer exist in the spec.
 */
const reconcileTasksWithSpecs = (get: () => EditorStore) => {
  const { tasks, taskTemplates } = get();
  if (tasks.length === 0 || taskTemplates.length === 0) return;

  const specMap = new Map(taskTemplates.map((t) => [t.type, t]));
  let changed = false;

  const reconciled = tasks.map((task) => {
    const spec = specMap.get(task.type);
    if (!spec) return task;

    let taskChanged = false;
    const updates: Partial<TaskNode> = {};

    // Filter parameters to only those in spec
    if (task.parameters && spec.input_parameters) {
      const validKeys = new Set(Object.keys(spec.input_parameters));
      const filtered: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(task.parameters)) {
        if (validKeys.has(key)) {
          filtered[key] = value;
        } else {
          taskChanged = true;
        }
      }
      if (taskChanged) updates.parameters = filtered;
    } else if (task.parameters && !spec.input_parameters) {
      updates.parameters = {};
      taskChanged = true;
    }

    // Filter devices to only those in spec
    if (task.devices && spec.input_devices) {
      const validSlots = new Set(Object.keys(spec.input_devices));
      const filtered: Record<string, unknown> = {};
      let devChanged = false;
      for (const [slot, assignment] of Object.entries(task.devices)) {
        if (validSlots.has(slot)) {
          filtered[slot] = assignment;
        } else {
          devChanged = true;
        }
      }
      if (devChanged) {
        updates.devices = filtered as TaskNode['devices'];
        taskChanged = true;
      }
    }

    // Filter resources to only those in spec
    if (task.resources && spec.input_resources) {
      const validSlots = new Set(Object.keys(spec.input_resources));
      const filtered: Record<string, unknown> = {};
      let resChanged = false;
      for (const [slot, assignment] of Object.entries(task.resources)) {
        if (validSlots.has(slot)) {
          filtered[slot] = assignment;
        } else {
          resChanged = true;
        }
      }
      if (resChanged) {
        updates.resources = filtered as TaskNode['resources'];
        taskChanged = true;
      }
    }

    if (taskChanged) {
      changed = true;
      return { ...task, ...updates };
    }
    return task;
  });

  if (changed) {
    useEditorStore.setState({ tasks: reconciled, isDirty: true });
  }
};

const saveToHistory = () => {
  const state = useEditorStore.getState();
  if (state.isBatchOperation) return;

  const currentState = getCurrentProtocolState(state);
  useEditorStore.setState({
    past: [...state.past, currentState].slice(-MAX_HISTORY_SIZE),
    future: [],
  });
};

// ---------------------------------------------------------------------------
// Reference remapping helpers (for rename / paste)
// ---------------------------------------------------------------------------

type ReferenceRemapper = (value: unknown) => unknown;

const createReferenceRemapper = (oldName: string, newName: string, shouldRemap: boolean = true): ReferenceRemapper => {
  if (!shouldRemap) return (value) => value;
  return (value: unknown): unknown => {
    if (typeof value === 'string' && value.includes('.')) {
      const [refTaskName, outputName] = value.split('.');
      if (refTaskName === oldName) return `${newName}.${outputName}`;
    }
    return value;
  };
};

const remapObjectFields = <T extends Record<string, unknown>>(
  obj: T | undefined,
  remapper: ReferenceRemapper
): T | undefined => {
  if (!obj) return undefined;
  return Object.fromEntries(Object.entries(obj).map(([key, value]) => [key, remapper(value)])) as T;
};

const remapTaskReferences = (
  task: TaskNode,
  remapper: ReferenceRemapper,
  dependencyRemapper?: (deps: string[]) => string[]
): TaskNode => {
  const updated = { ...task };
  if (dependencyRemapper && task.dependencies) {
    updated.dependencies = dependencyRemapper(task.dependencies);
  }
  if (task.devices) updated.devices = remapObjectFields(task.devices, remapper);
  if (task.resources) updated.resources = remapObjectFields(task.resources, remapper);
  if (task.parameters) updated.parameters = remapObjectFields(task.parameters, remapper);
  return updated;
};

// ---------------------------------------------------------------------------
// Auto-cache helper: given updated working copies + baselines + current cache,
// returns { isDirty, cache } with the cache entry updated or removed.
// ---------------------------------------------------------------------------

function withAutoCache(
  cacheKey: string | null,
  currentCache: Record<string, CachedFiles>,
  yaml: string,
  python: string,
  layout: string,
  baselineYaml: string,
  baselinePython: string,
  baselineLayout: string
): { isDirty: boolean; cache: Record<string, CachedFiles> } {
  const isDirty = computeDirty(yaml, python, layout, baselineYaml, baselinePython, baselineLayout);
  let cache = currentCache;

  if (cacheKey) {
    if (isDirty) {
      cache = { ...cache, [cacheKey]: { yaml, python, layout } };
    } else if (cacheKey in cache) {
      const { [cacheKey]: _removed, ...rest } = cache;
      cache = rest;
    }
  }

  return { isDirty, cache };
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useEditorStore = create<EditorStore>()(
  persist(
    (set, get) => ({
      // =====================================================================
      // Initial state — Editor slice
      // =====================================================================
      packages: [],
      selectedPackage: null,
      selectedEntityType: null,
      selectedEntityName: null,
      entityTrees: {},

      yaml: '',
      python: '',
      layout: '',
      baselineYaml: '',
      baselinePython: '',
      baselineLayout: '',

      cache: {},

      editorMode: 'code' as EditorMode,
      isDirty: false,
      isSaving: false,
      isLoading: false,
      error: null,

      diskMtime: null,
      diskChanged: false,
      conflictMtime: null,

      // =====================================================================
      // Initial state — ProtocolRun slice
      // =====================================================================
      protocolType: '',
      protocolDesc: '',
      labs: [],
      tasks: [],
      nextTaskNumber: 1,

      past: [],
      future: [],

      taskTemplates: [],
      labSpecs: {},
      specTimestamps: {},

      selectedNodeName: null,
      clipboard: [],
      viewport: { x: 0, y: 0, zoom: 1 },

      isPropertiesPanelOpen: false,
      isOptimizerPanelOpen: false,

      isBatchOperation: false,
      overlapResolutionRequested: false,
      needsOverlapResolution: false,

      // Validation state
      validationErrors: [],
      taskValidationErrors: {},
      isValidating: false,
      isValid: null,
      isValidationPanelOpen: false,

      // =====================================================================
      // Editor actions
      // =====================================================================

      setPackages: (packages) => set({ packages }),

      setEntityTree: (packageName, tree) =>
        set((state) => ({
          entityTrees: { ...state.entityTrees, [packageName]: tree },
        })),

      getEntityTree: (packageName) => get().entityTrees[packageName],

      selectEntity: (packageName, entityType, entityName) =>
        set((state) => {
          // No-op if already selected
          if (
            state.selectedPackage === packageName &&
            state.selectedEntityType === entityType &&
            state.selectedEntityName === entityName
          ) {
            return {};
          }

          // Don't clear content — avoids flash. Content stays until loadFromDisk.
          return {
            selectedPackage: packageName,
            selectedEntityType: entityType,
            selectedEntityName: entityName,
            isLoading: true,
          };
        }),

      loadFromDisk: (files) =>
        set((state) => {
          const cacheKey = getCacheKey(state.selectedPackage, state.selectedEntityType, state.selectedEntityName);
          const cached = cacheKey ? state.cache[cacheKey] : undefined;
          const diskLayout = files.layout || '';
          const mtime = files.mtime ?? null;

          if (cached) {
            return {
              yaml: cached.yaml,
              python: cached.python,
              layout: cached.layout,
              baselineYaml: files.yaml,
              baselinePython: files.python,
              baselineLayout: diskLayout,
              isDirty: true,
              isLoading: false,
              diskMtime: mtime,
              diskChanged: false,
            };
          }

          return {
            yaml: files.yaml,
            python: files.python,
            layout: diskLayout,
            baselineYaml: files.yaml,
            baselinePython: files.python,
            baselineLayout: diskLayout,
            isDirty: false,
            isLoading: false,
            diskMtime: mtime,
            diskChanged: false,
          };
        }),

      setBaseline: (yaml, python, layout) =>
        set({
          baselineYaml: yaml,
          baselinePython: python,
          baselineLayout: layout,
          yaml,
          python,
          layout,
          isDirty: false,
        }),

      updateYaml: (content) =>
        set((state) => {
          const cacheKey = getCacheKey(state.selectedPackage, state.selectedEntityType, state.selectedEntityName);
          const { isDirty, cache } = withAutoCache(
            cacheKey,
            state.cache,
            content,
            state.python,
            state.layout,
            state.baselineYaml,
            state.baselinePython,
            state.baselineLayout
          );
          return { yaml: content, isDirty, cache };
        }),

      updatePython: (content) =>
        set((state) => {
          const cacheKey = getCacheKey(state.selectedPackage, state.selectedEntityType, state.selectedEntityName);
          const { isDirty, cache } = withAutoCache(
            cacheKey,
            state.cache,
            state.yaml,
            content,
            state.layout,
            state.baselineYaml,
            state.baselinePython,
            state.baselineLayout
          );
          return { python: content, isDirty, cache };
        }),

      updateLayout: (content) =>
        set((state) => {
          const cacheKey = getCacheKey(state.selectedPackage, state.selectedEntityType, state.selectedEntityName);
          const { isDirty, cache } = withAutoCache(
            cacheKey,
            state.cache,
            state.yaml,
            state.python,
            content,
            state.baselineYaml,
            state.baselinePython,
            state.baselineLayout
          );
          return { layout: content, isDirty, cache };
        }),

      setEditorMode: (mode) => set({ editorMode: mode }),

      setIsSaving: (saving) => set({ isSaving: saving }),

      markSaved: (newMtime) =>
        set((state) => {
          const cacheKey = getCacheKey(state.selectedPackage, state.selectedEntityType, state.selectedEntityName);
          let cache = state.cache;
          if (cacheKey && cacheKey in cache) {
            const { [cacheKey]: _removed, ...rest } = cache;
            cache = rest;
          }
          return {
            baselineYaml: state.yaml,
            baselinePython: state.python,
            baselineLayout: state.layout,
            isDirty: false,
            cache,
            diskMtime: newMtime ?? state.diskMtime,
            diskChanged: false,
            conflictMtime: null,
          };
        }),

      setLoading: (loading) => set({ isLoading: loading }),

      setError: (error) => set({ error }),

      setDiskMtime: (mtime) => set({ diskMtime: mtime }),
      setDiskChanged: (changed) => set({ diskChanged: changed }),
      setConflictMtime: (mtime) => set({ conflictMtime: mtime }),

      reset: () =>
        set({
          packages: [],
          selectedPackage: null,
          selectedEntityType: null,
          selectedEntityName: null,
          entityTrees: {},
          yaml: '',
          python: '',
          layout: '',
          baselineYaml: '',
          baselinePython: '',
          baselineLayout: '',
          cache: {},
          editorMode: 'code' as EditorMode,
          isDirty: false,
          isSaving: false,
          isLoading: false,
          error: null,
          protocolType: '',
          protocolDesc: '',
          labs: [],
          tasks: [],
          nextTaskNumber: 1,
          past: [],
          future: [],
          selectedNodeName: null,
          isPropertiesPanelOpen: false,
          isOptimizerPanelOpen: false,
          validationErrors: [],
          taskValidationErrors: {},
          isValidating: false,
          isValid: null,
          isValidationPanelOpen: false,
          diskMtime: null,
          diskChanged: false,
          conflictMtime: null,
        }),

      clearSelection: () =>
        set({
          selectedEntityType: null,
          selectedEntityName: null,
          yaml: '',
          python: '',
          layout: '',
          baselineYaml: '',
          baselinePython: '',
          baselineLayout: '',
          isDirty: false,
          editorMode: 'code' as EditorMode,
          diskMtime: null,
          diskChanged: false,
          conflictMtime: null,
        }),

      hasUnsavedFile: (key: string) => key in get().cache,

      deleteCache: (key: string) =>
        set((state) => {
          if (!(key in state.cache)) return {};
          const { [key]: _removed, ...rest } = state.cache;
          return { cache: rest };
        }),

      renameCache: (oldKey: string, newKey: string) =>
        set((state) => {
          if (!(oldKey in state.cache)) return {};
          const cached = state.cache[oldKey];
          const { [oldKey]: _removed, ...rest } = state.cache;
          return { cache: { ...rest, [newKey]: cached } };
        }),

      // =====================================================================
      // ProtocolRun actions
      // =====================================================================

      setProtocolType: (type) => {
        saveToHistory();
        set({ protocolType: type });
      },

      setProtocolDesc: (desc) => {
        saveToHistory();
        set({ protocolDesc: desc });
      },

      setLabs: (labs) => {
        saveToHistory();
        set({ labs });
      },

      addTask: (task) => {
        saveToHistory();
        set((state) => ({ tasks: [...state.tasks, task] }));
      },

      getNextTaskName: () => {
        const state = get();
        const name = `task-${state.nextTaskNumber}`;
        set({ nextTaskNumber: state.nextTaskNumber + 1 });
        return name;
      },

      updateTask: (taskName, updates) => {
        saveToHistory();
        set((state) => {
          const isRenaming = !!(updates.name && updates.name !== taskName);
          const newName = updates.name!;
          const remapper = createReferenceRemapper(taskName, newName, isRenaming);

          const updatedTasks = state.tasks.map((task) => {
            if (task.name === taskName) return { ...task, ...updates };
            if (!isRenaming) return task;
            return remapTaskReferences(task, remapper, (deps) => deps.map((dep) => (dep === taskName ? newName : dep)));
          });

          const newSelectedNodeName =
            state.selectedNodeName === taskName && isRenaming ? newName : state.selectedNodeName;

          return { tasks: updatedTasks, selectedNodeName: newSelectedNodeName };
        });
      },

      deleteTask: (taskName) => {
        saveToHistory();
        set((state) => ({
          tasks: state.tasks.filter((task) => task.name !== taskName),
          selectedNodeName: state.selectedNodeName === taskName ? null : state.selectedNodeName,
        }));
      },

      setSelectedNodeName: (nodeName) =>
        set({
          selectedNodeName: nodeName,
          isPropertiesPanelOpen: nodeName !== null,
        }),

      setIsPropertiesPanelOpen: (isOpen) =>
        set({
          isPropertiesPanelOpen: isOpen,
          selectedNodeName: isOpen ? get().selectedNodeName : null,
        }),

      setIsOptimizerPanelOpen: (isOpen) => set({ isOptimizerPanelOpen: isOpen }),

      setViewport: (viewport) => set({ viewport }),

      setTaskTemplates: (templates) => {
        set({ taskTemplates: templates });
        reconcileTasksWithSpecs(get);
      },

      mergeTaskTemplates: (specsByType) => {
        const existing = get().taskTemplates;
        const merged = existing.map((t) => specsByType[t.type] ?? t);
        // Add any new types not already in the array
        for (const [type, spec] of Object.entries(specsByType)) {
          if (!existing.some((t) => t.type === type)) {
            merged.push(spec);
          }
        }
        set({ taskTemplates: merged });
        reconcileTasksWithSpecs(get);
      },

      setLabSpecs: (labSpecs) => set({ labSpecs }),

      mergeLabSpecs: (specs) => {
        set({ labSpecs: { ...get().labSpecs, ...specs } });
      },

      refreshSpecsIfChanged: async () => {
        const state = get();

        // Fetch lightweight timestamps
        let timestamps: Record<string, string>;
        try {
          const res = await fetch('/api/specs/timestamps');
          if (!res.ok) return false;
          timestamps = await res.json();
        } catch {
          return false;
        }

        // Diff against stored timestamps
        const changedTasks: string[] = [];
        const changedLabs: string[] = [];

        for (const [key, ts] of Object.entries(timestamps)) {
          if (state.specTimestamps[key] !== ts) {
            const [defType, name] = key.split(':');
            if (defType === 'task') changedTasks.push(name);
            else if (defType === 'lab') changedLabs.push(name);
          }
        }

        // Also detect removed definitions
        for (const key of Object.keys(state.specTimestamps)) {
          if (!(key in timestamps)) {
            const [defType, name] = key.split(':');
            if (defType === 'task') changedTasks.push(name);
            else if (defType === 'lab') changedLabs.push(name);
          }
        }

        if (changedTasks.length === 0 && changedLabs.length === 0) {
          set({ specTimestamps: timestamps });
          return false;
        }

        // Fetch only changed specs
        const params = new URLSearchParams();
        if (changedTasks.length > 0) params.set('tasks', changedTasks.join(','));
        if (changedLabs.length > 0) params.set('labs', changedLabs.join(','));

        try {
          const res = await fetch(`/api/specs?${params.toString()}`);
          if (!res.ok) return false;
          const data = await res.json();

          if (data.taskSpecs) get().mergeTaskTemplates(data.taskSpecs);
          if (data.labSpecs) get().mergeLabSpecs(data.labSpecs);
          set({ specTimestamps: timestamps });
          return true;
        } catch {
          return false;
        }
      },

      resetProtocol: () =>
        set({
          protocolType: '',
          protocolDesc: '',
          labs: [],
          tasks: [],
          past: [],
          future: [],
          selectedNodeName: null,
          isPropertiesPanelOpen: false,
        }),

      loadProtocol: (protocol) => {
        saveToHistory();

        const taskNumbers = protocol.tasks
          .map((t) => parseInt(t.name.match(/^task-(\d+)$/)?.[1] ?? '0', 10))
          .filter((n) => n > 0);

        const nextTaskNumber = taskNumbers.length > 0 ? Math.max(...taskNumbers) + 1 : 1;

        set({
          protocolType: protocol.type,
          protocolDesc: protocol.desc,
          labs: protocol.labs,
          tasks: protocol.tasks,
          nextTaskNumber,
        });
      },

      exportProtocol: () => {
        const state = get();
        return {
          type: state.protocolType,
          desc: state.protocolDesc,
          labs: state.labs,
          tasks: state.tasks,
        };
      },

      copyNodes: (nodeNames) => {
        const state = get();
        const nodesToCopy = state.tasks.filter((task) => nodeNames.includes(task.name));
        set({ clipboard: nodesToCopy });
      },

      pasteNodes: (position) => {
        const state = get();
        if (state.clipboard.length === 0) return [];

        saveToHistory();

        const minX = Math.min(...state.clipboard.map((t) => t.position.x));
        const minY = Math.min(...state.clipboard.map((t) => t.position.y));

        const oldToNewNames = new Map<string, string>();
        const copiedNodeNames = new Set(state.clipboard.map((t) => t.name));

        const newTasks: TaskNode[] = state.clipboard.map((task) => {
          const newName = get().getNextTaskName();
          oldToNewNames.set(task.name, newName);

          return {
            ...task,
            name: newName,
            position: {
              x: position.x + (task.position.x - minX),
              y: position.y + (task.position.y - minY),
            },
          };
        });

        const remapper: ReferenceRemapper = (value) => {
          if (typeof value === 'string' && value.includes('.')) {
            const [taskName, outputName] = value.split('.');
            if (copiedNodeNames.has(taskName)) {
              const newTaskName = oldToNewNames.get(taskName);
              return newTaskName ? `${newTaskName}.${outputName}` : value;
            }
          }
          return value;
        };

        newTasks.forEach((task, index) => {
          newTasks[index] = remapTaskReferences(task, remapper, (deps) =>
            deps.filter((dep) => copiedNodeNames.has(dep)).map((dep) => oldToNewNames.get(dep) || dep)
          );
        });

        set((state) => ({ tasks: [...state.tasks, ...newTasks] }));
        return newTasks.map((t) => t.name);
      },

      batchOperation: (operation) => {
        saveToHistory();
        set({ isBatchOperation: true });
        try {
          operation();
        } finally {
          set({ isBatchOperation: false });
        }
      },

      undo: () => {
        const state = get();
        if (state.past.length === 0) return;

        const previous = state.past[state.past.length - 1];
        const newPast = state.past.slice(0, -1);

        set({
          ...previous,
          past: newPast,
          future: [getCurrentProtocolState(state), ...state.future],
        });
      },

      redo: () => {
        const state = get();
        if (state.future.length === 0) return;

        const next = state.future[0];
        const newFuture = state.future.slice(1);

        set({
          ...next,
          past: [...state.past, getCurrentProtocolState(state)],
          future: newFuture,
        });
      },

      canUndo: () => get().past.length > 0,
      canRedo: () => get().future.length > 0,

      // =====================================================================
      // Validation actions
      // =====================================================================

      setValidationResult: (result) => {
        const taskErrors: Record<string, string[]> = {};
        for (const error of result.errors) {
          if (error.task) {
            if (!taskErrors[error.task]) taskErrors[error.task] = [];
            taskErrors[error.task].push(error.message);
          }
        }
        set({
          isValid: result.valid,
          validationErrors: result.errors,
          taskValidationErrors: taskErrors,
          isValidating: false,
        });
      },

      setIsValidating: (validating) => set({ isValidating: validating }),

      setIsValidationPanelOpen: (open) => set({ isValidationPanelOpen: open }),

      clearValidation: () =>
        set({
          validationErrors: [],
          taskValidationErrors: {},
          isValidating: false,
          isValid: null,
          isValidationPanelOpen: false,
        }),
    }),
    {
      name: 'eos-editor-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        selectedPackage: state.selectedPackage,
        selectedEntityType: state.selectedEntityType,
        selectedEntityName: state.selectedEntityName,
        editorMode: state.editorMode,
        cache: state.cache,
        viewport: state.viewport,
      }),
    }
  )
);
