'use client';

import { useState, useCallback, useMemo, useEffect } from 'react';
import {
  ChevronRight,
  ChevronDown,
  FileCode,
  Plus,
  Trash2,
  Search,
  X,
  Package as PackageIcon,
  RefreshCw,
  Edit,
  Cpu,
  Settings,
  FlaskConical,
  Microscope,
} from 'lucide-react';
import { useEditorStore } from '@/lib/stores/editorStore';
import { getEntityColor, validateEntityName } from '@/lib/utils/editor-utils';
import { ConfirmationDialog } from '@/features/management/components/dialogs/ConfirmationDialog';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { TIMING } from '@/lib/constants/theme';
import type { Package, EntityType, EntityNode, EntityTree } from '@/lib/types/filesystem';

const EXPANDED_PACKAGES_KEY = 'eos-editor-expanded-packages';
const EXPANDED_ENTITY_TYPES_KEY = 'eos-editor-expanded-entity-types';

// Simple localStorage helpers
const loadExpandedState = (key: string): Set<string> => {
  if (typeof window === 'undefined') return new Set();
  try {
    const stored = localStorage.getItem(key);
    return stored ? new Set(JSON.parse(stored)) : new Set();
  } catch {
    return new Set();
  }
};

const saveExpandedState = (key: string, state: Set<string>): void => {
  if (typeof window !== 'undefined') {
    try {
      localStorage.setItem(key, JSON.stringify(Array.from(state)));
    } catch {}
  }
};

type FilteredPackage = { pkg: Package; matchingTypes: Partial<Record<EntityType, EntityNode[]>> };

const ENTITY_TYPE_LABELS: Record<EntityType, string> = {
  devices: 'Devices',
  tasks: 'Tasks',
  labs: 'Labs',
  protocols: 'Protocols',
};

const ENTITY_TYPE_KEYS = Object.keys(ENTITY_TYPE_LABELS) as EntityType[];

const ENTITY_ICONS: Record<EntityType, React.ReactNode> = {
  devices: <Cpu className="w-3.5 h-3.5" />,
  tasks: <Settings className="w-3.5 h-3.5" />,
  labs: <FlaskConical className="w-3.5 h-3.5" />,
  protocols: <Microscope className="w-3.5 h-3.5" />,
};

function hasEntities(pkg: Package, type: EntityType): boolean {
  if (type === 'devices') return pkg.hasDevices;
  if (type === 'tasks') return pkg.hasTasks;
  if (type === 'labs') return pkg.hasLabs;
  if (type === 'protocols') return pkg.hasProtocols;
  return false;
}

// --- Sub-components ---

interface EntityItemProps {
  entity: EntityNode;
  packageName: string;
  entityType: EntityType;
  isSelected: boolean;
  hasUnsaved: boolean;
  isRenaming: boolean;
  renameValue: string;
  onRenameValueChange: (value: string) => void;
  onRenameConfirm: () => void;
  onRenameCancel: () => void;
  onClick: (packageName: string, entityType: EntityType, entityName: string) => void;
  onContextMenu: (e: React.MouseEvent, packageName: string, entityType: EntityType, entityName: string) => void;
  onDeleteRequest: (packageName: string, entityType: EntityType, entityName: string) => void;
}

function EntityItem({
  entity,
  packageName,
  entityType,
  isSelected,
  hasUnsaved,
  isRenaming,
  renameValue,
  onRenameValueChange,
  onRenameConfirm,
  onRenameCancel,
  onClick,
  onContextMenu,
  onDeleteRequest,
}: EntityItemProps) {
  if (isRenaming) {
    return (
      <div className="flex items-center gap-1 px-2 py-1">
        <FileCode className="w-3 h-3 text-gray-400 flex-shrink-0" />
        <input
          type="text"
          value={renameValue}
          onChange={(e) => onRenameValueChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onRenameConfirm();
            if (e.key === 'Escape') onRenameCancel();
          }}
          onBlur={onRenameCancel}
          placeholder="entity_name"
          className="text-xs flex-1 px-1 py-0.5 border border-blue-500 dark:border-yellow-500 rounded bg-white dark:bg-gray-800 min-w-0"
          autoFocus
        />
      </div>
    );
  }

  return (
    <div
      className={`flex items-center gap-1 px-2 py-1 rounded cursor-pointer group ${
        isSelected ? 'bg-blue-100 dark:bg-yellow-900' : 'hover:bg-gray-100 dark:hover:bg-gray-800'
      }`}
      onClick={() => onClick(packageName, entityType, entity.name)}
      onContextMenu={(e) => onContextMenu(e, packageName, entityType, entity.name)}
    >
      <FileCode className="w-3 h-3 text-gray-500 flex-shrink-0" />
      <span className="text-sm flex-1 flex items-center gap-1 min-w-0">
        {hasUnsaved && (
          <span
            className="w-1.5 h-1.5 rounded-full bg-blue-500 dark:bg-yellow-500 flex-shrink-0"
            title="Unsaved changes"
          />
        )}
        <span className="truncate">{entity.name}</span>
      </span>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDeleteRequest(packageName, entityType, entity.name);
        }}
        className="p-0.5 opacity-0 group-hover:opacity-100 hover:bg-red-100 dark:hover:bg-red-900 rounded flex-shrink-0"
        title="Delete"
      >
        <Trash2 className="w-3.5 h-3.5 text-red-600" />
      </button>
    </div>
  );
}

interface EntityTypeSectionProps {
  packageName: string;
  entityType: EntityType;
  entities: EntityNode[];
  isExpanded: boolean;
  cache: Record<string, unknown>;
  selectedEntityType: EntityType | null;
  selectedEntityName: string | null;
  renamingEntity: { packageName: string; entityType: EntityType; oldName: string } | null;
  renameValue: string;
  creatingEntity: { packageName: string; entityType: EntityType } | null;
  newEntityName: string;
  onToggle: (key: string) => void;
  onCreateStart: (packageName: string, entityType: EntityType) => void;
  onCreateConfirm: () => void;
  onCreateCancel: () => void;
  onNewEntityNameChange: (value: string) => void;
  onRenameValueChange: (value: string) => void;
  onRenameConfirm: () => void;
  onRenameCancel: () => void;
  onEntityClick: (packageName: string, entityType: EntityType, entityName: string) => void;
  onContextMenu: (e: React.MouseEvent, packageName: string, entityType: EntityType, entityName: string) => void;
  onDeleteRequest: (packageName: string, entityType: EntityType, entityName: string) => void;
}

function EntityTypeSection({
  packageName,
  entityType,
  entities,
  isExpanded,
  cache,
  selectedEntityType,
  selectedEntityName,
  renamingEntity,
  renameValue,
  creatingEntity,
  newEntityName,
  onToggle,
  onCreateStart,
  onCreateConfirm,
  onCreateCancel,
  onNewEntityNameChange,
  onRenameValueChange,
  onRenameConfirm,
  onRenameCancel,
  onEntityClick,
  onContextMenu,
  onDeleteRequest,
}: EntityTypeSectionProps) {
  const typeKey = `${packageName}-${entityType}`;

  return (
    <div className="mb-1">
      {/* Entity Type Header */}
      <div className="flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 group">
        <div className="flex-1 flex items-center gap-1 cursor-pointer min-w-0" onClick={() => onToggle(typeKey)}>
          {isExpanded ? (
            <ChevronDown className="w-3 h-3 flex-shrink-0" />
          ) : (
            <ChevronRight className="w-3 h-3 flex-shrink-0" />
          )}
          <span className={`text-sm ${getEntityColor(entityType)} flex-shrink-0`}>{ENTITY_ICONS[entityType]}</span>
          <span className={`text-sm ${getEntityColor(entityType)} truncate`}>{ENTITY_TYPE_LABELS[entityType]}</span>
        </div>
        <button
          onClick={() => onCreateStart(packageName, entityType)}
          className="p-0.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded opacity-0 group-hover:opacity-100 flex-shrink-0"
          title="Create new"
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Entities */}
      {isExpanded && (
        <div className="ml-4">
          {entities.map((entity: EntityNode) => {
            const cacheKey = `${packageName}/${entityType}/${entity.name}`;
            const hasUnsaved = cacheKey in cache;
            const isRenaming =
              renamingEntity &&
              renamingEntity.packageName === packageName &&
              renamingEntity.entityType === entityType &&
              renamingEntity.oldName === entity.name;

            return (
              <EntityItem
                key={entity.name}
                entity={entity}
                packageName={packageName}
                entityType={entityType}
                isSelected={selectedEntityType === entityType && selectedEntityName === entity.name}
                hasUnsaved={hasUnsaved}
                isRenaming={!!isRenaming}
                renameValue={renameValue}
                onRenameValueChange={onRenameValueChange}
                onRenameConfirm={onRenameConfirm}
                onRenameCancel={onRenameCancel}
                onClick={onEntityClick}
                onContextMenu={onContextMenu}
                onDeleteRequest={onDeleteRequest}
              />
            );
          })}

          {/* Create Entity Inline */}
          {creatingEntity && creatingEntity.packageName === packageName && creatingEntity.entityType === entityType && (
            <div className="flex items-center gap-1 px-2 py-1">
              <FileCode className="w-3 h-3 text-gray-400 flex-shrink-0" />
              <input
                type="text"
                value={newEntityName}
                onChange={(e) => onNewEntityNameChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onCreateConfirm();
                  if (e.key === 'Escape') onCreateCancel();
                }}
                onBlur={onCreateCancel}
                placeholder="entity_name"
                className="text-xs flex-1 px-1 py-0.5 border border-blue-500 dark:border-yellow-500 rounded bg-white dark:bg-gray-800 min-w-0"
                autoFocus
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface PackageNodeProps {
  pkg: Package;
  matchingTypes: Partial<Record<EntityType, EntityNode[]>>;
  isExpanded: boolean;
  isSearching: boolean;
  expandedEntityTypes: Set<string>;
  cache: Record<string, unknown>;
  selectedEntityType: EntityType | null;
  selectedEntityName: string | null;
  renamingEntity: { packageName: string; entityType: EntityType; oldName: string } | null;
  renameValue: string;
  creatingEntity: { packageName: string; entityType: EntityType } | null;
  newEntityName: string;
  entityTrees: Record<string, EntityTree>;
  onTogglePackage: (packageName: string) => void;
  onToggleEntityType: (key: string) => void;
  onCreateStart: (packageName: string, entityType: EntityType) => void;
  onCreateConfirm: () => void;
  onCreateCancel: () => void;
  onNewEntityNameChange: (value: string) => void;
  onRenameValueChange: (value: string) => void;
  onRenameConfirm: () => void;
  onRenameCancel: () => void;
  onEntityClick: (packageName: string, entityType: EntityType, entityName: string) => void;
  onContextMenu: (e: React.MouseEvent, packageName: string, entityType: EntityType, entityName?: string) => void;
  onDeleteRequest: (packageName: string, entityType: EntityType, entityName: string) => void;
}

function PackageNode({
  pkg,
  matchingTypes,
  isExpanded,
  isSearching,
  expandedEntityTypes,
  cache,
  selectedEntityType,
  selectedEntityName,
  renamingEntity,
  renameValue,
  creatingEntity,
  newEntityName,
  entityTrees,
  onTogglePackage,
  onToggleEntityType,
  onCreateStart,
  onCreateConfirm,
  onCreateCancel,
  onNewEntityNameChange,
  onRenameValueChange,
  onRenameConfirm,
  onRenameCancel,
  onEntityClick,
  onContextMenu,
  onDeleteRequest,
}: PackageNodeProps) {
  const entityTree = isExpanded ? entityTrees[pkg.name] : null;

  return (
    <div className="mb-1">
      {/* Package Header */}
      <div
        className="flex items-center gap-1 px-2 py-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer"
        onClick={() => onTogglePackage(pkg.name)}
      >
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 flex-shrink-0" />
        )}
        <PackageIcon className="w-4 h-4 text-blue-500 dark:text-yellow-500 flex-shrink-0" />
        <span className="text-sm font-medium min-w-0 truncate">{pkg.name}</span>
      </div>

      {/* Entity Types */}
      {isExpanded && entityTree && (
        <div className="ml-4">
          {ENTITY_TYPE_KEYS.map((entityType) => {
            if (!hasEntities(pkg, entityType)) return null;

            const entities =
              isSearching && matchingTypes[entityType]
                ? matchingTypes[entityType]
                : isSearching
                  ? []
                  : entityTree[entityType] || [];

            if (isSearching && entities.length === 0) return null;

            const typeKey = `${pkg.name}-${entityType}`;

            return (
              <EntityTypeSection
                key={entityType}
                packageName={pkg.name}
                entityType={entityType}
                entities={entities}
                isExpanded={expandedEntityTypes.has(typeKey)}
                cache={cache}
                selectedEntityType={selectedEntityType}
                selectedEntityName={selectedEntityName}
                renamingEntity={renamingEntity}
                renameValue={renameValue}
                creatingEntity={creatingEntity}
                newEntityName={newEntityName}
                onToggle={onToggleEntityType}
                onCreateStart={onCreateStart}
                onCreateConfirm={onCreateConfirm}
                onCreateCancel={onCreateCancel}
                onNewEntityNameChange={onNewEntityNameChange}
                onRenameValueChange={onRenameValueChange}
                onRenameConfirm={onRenameConfirm}
                onRenameCancel={onRenameCancel}
                onEntityClick={onEntityClick}
                onContextMenu={onContextMenu}
                onDeleteRequest={onDeleteRequest}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

// --- Main component ---

interface PackageFileTreeProps {
  onCreateEntity: (packageName: string, entityType: EntityType, entityName: string) => void;
  onDeleteEntity: (packageName: string, entityType: EntityType, entityName: string) => void;
  onRenameEntity: (packageName: string, entityType: EntityType, oldName: string, newName: string) => void;
  onRefresh?: () => void;
  onPackageExpand: (packageName: string) => Promise<void>;
}

export function PackageFileTree({
  onCreateEntity,
  onDeleteEntity,
  onRenameEntity,
  onRefresh,
  onPackageExpand,
}: PackageFileTreeProps) {
  const packages = useEditorStore((state) => state.packages);
  const selectedPackage = useEditorStore((state) => state.selectedPackage);
  const selectedEntityType = useEditorStore((state) => state.selectedEntityType);
  const selectedEntityName = useEditorStore((state) => state.selectedEntityName);
  const entityTrees = useEditorStore((state) => state.entityTrees);
  const selectEntity = useEditorStore((state) => state.selectEntity);
  const cache = useEditorStore((state) => state.cache);

  const [expandedPackages, setExpandedPackages] = useState<Set<string>>(() => loadExpandedState(EXPANDED_PACKAGES_KEY));
  const [expandedEntityTypes, setExpandedEntityTypes] = useState<Set<string>>(() =>
    loadExpandedState(EXPANDED_ENTITY_TYPES_KEY)
  );
  const [creatingEntity, setCreatingEntity] = useState<{ packageName: string; entityType: EntityType } | null>(null);
  const [newEntityName, setNewEntityName] = useState('');
  const [renamingEntity, setRenamingEntity] = useState<{
    packageName: string;
    entityType: EntityType;
    oldName: string;
  } | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    packageName: string;
    entityType: EntityType;
    entityName?: string;
  } | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{
    packageName: string;
    entityType: EntityType;
    entityName: string;
  } | null>(null);

  const debouncedQuery = useDebouncedValue(searchQuery, TIMING.debounceDelay);

  // Save expanded packages to localStorage
  useEffect(() => {
    saveExpandedState(EXPANDED_PACKAGES_KEY, expandedPackages);
  }, [expandedPackages]);

  // Save expanded entity types to localStorage
  useEffect(() => {
    saveExpandedState(EXPANDED_ENTITY_TYPES_KEY, expandedEntityTypes);
  }, [expandedEntityTypes]);

  // Auto-expand package and entity type when entity is selected
  useEffect(() => {
    if (selectedPackage && selectedEntityType) {
      setExpandedPackages((prev) => {
        if (!prev.has(selectedPackage)) {
          return new Set([...prev, selectedPackage]);
        }
        return prev;
      });

      const typeKey = `${selectedPackage}-${selectedEntityType}`;
      setExpandedEntityTypes((prev) => {
        if (!prev.has(typeKey)) {
          return new Set([...prev, typeKey]);
        }
        return prev;
      });
    }
  }, [selectedPackage, selectedEntityType]);

  // Fetch entity trees for all packages on mount
  useEffect(() => {
    Promise.all(packages.map((pkg) => onPackageExpand(pkg.name))).then(() => {
      // Auto-expand packages if none are expanded
      setExpandedPackages((prev) => {
        if (prev.size === 0) {
          return new Set(packages.map((p) => p.name));
        }
        return prev;
      });
    });
  }, [packages, onPackageExpand]);

  const togglePackage = useCallback(
    (packageName: string) => {
      const newExpanded = new Set(expandedPackages);
      if (newExpanded.has(packageName)) {
        newExpanded.delete(packageName);
      } else {
        newExpanded.add(packageName);
        onPackageExpand(packageName);
      }
      setExpandedPackages(newExpanded);
    },
    [expandedPackages, onPackageExpand]
  );

  const toggleEntityType = useCallback(
    (key: string) => {
      const newExpanded = new Set(expandedEntityTypes);
      if (newExpanded.has(key)) {
        newExpanded.delete(key);
      } else {
        newExpanded.add(key);
      }
      setExpandedEntityTypes(newExpanded);
    },
    [expandedEntityTypes]
  );

  const handleEntityClick = useCallback(
    (packageName: string, entityType: EntityType, entityName: string) => {
      if (selectedPackage === packageName && selectedEntityType === entityType && selectedEntityName === entityName) {
        return;
      }
      selectEntity(packageName, entityType, entityName);
    },
    [selectEntity, selectedPackage, selectedEntityType, selectedEntityName]
  );

  const handleCreateEntityStart = useCallback((packageName: string, entityType: EntityType) => {
    const typeKey = `${packageName}-${entityType}`;
    setExpandedEntityTypes((prev) => {
      if (prev.has(typeKey)) return prev;
      return new Set([...prev, typeKey]);
    });
    setCreatingEntity({ packageName, entityType });
    setNewEntityName('');
    setContextMenu(null);
  }, []);

  const handleCreateEntityConfirm = useCallback(() => {
    if (creatingEntity && newEntityName) {
      const validation = validateEntityName(newEntityName);
      if (!validation.valid) {
        alert(validation.error);
        return;
      }
      onCreateEntity(creatingEntity.packageName, creatingEntity.entityType, newEntityName);
      setCreatingEntity(null);
      setNewEntityName('');
    }
  }, [creatingEntity, newEntityName, onCreateEntity]);

  const handleCreateCancel = useCallback(() => {
    setCreatingEntity(null);
  }, []);

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, packageName: string, entityType: EntityType, entityName?: string) => {
      e.preventDefault();
      setContextMenu({ x: e.clientX, y: e.clientY, packageName, entityType, entityName });
    },
    []
  );

  const handleDeleteFromContext = useCallback(() => {
    if (contextMenu && contextMenu.entityName) {
      setDeleteTarget({
        packageName: contextMenu.packageName,
        entityType: contextMenu.entityType,
        entityName: contextMenu.entityName,
      });
      setDeleteDialogOpen(true);
    }
    setContextMenu(null);
  }, [contextMenu]);

  const handleDeleteRequest = useCallback((packageName: string, entityType: EntityType, entityName: string) => {
    setDeleteTarget({ packageName, entityType, entityName });
    setDeleteDialogOpen(true);
  }, []);

  const handleRenameStart = useCallback(() => {
    if (contextMenu && contextMenu.entityName) {
      setRenamingEntity({
        packageName: contextMenu.packageName,
        entityType: contextMenu.entityType,
        oldName: contextMenu.entityName,
      });
      setRenameValue(contextMenu.entityName);
      setContextMenu(null);
    }
  }, [contextMenu]);

  const handleRenameConfirm = useCallback(() => {
    if (renamingEntity && renameValue && renameValue !== renamingEntity.oldName) {
      const validation = validateEntityName(renameValue);
      if (!validation.valid) {
        alert(validation.error);
        return;
      }
      onRenameEntity(renamingEntity.packageName, renamingEntity.entityType, renamingEntity.oldName, renameValue);
      setRenamingEntity(null);
      setRenameValue('');
    }
  }, [renamingEntity, renameValue, onRenameEntity]);

  const handleRenameCancel = useCallback(() => {
    setRenamingEntity(null);
    setRenameValue('');
  }, []);

  // Filter entities based on debounced search query
  const filteredPackages = useMemo(() => {
    if (!debouncedQuery.trim()) {
      return packages.map((pkg) => ({ pkg, matchingTypes: {} })).sort((a, b) => a.pkg.name.localeCompare(b.pkg.name));
    }

    const query = debouncedQuery.toLowerCase();
    const filtered: FilteredPackage[] = [];

    packages.forEach((pkg) => {
      const entityTree = entityTrees[pkg.name];
      if (!entityTree) return;

      const matchingTypes: Partial<Record<EntityType, EntityNode[]>> = {};
      let hasMatchesInPackage = false;

      ENTITY_TYPE_KEYS.forEach((entityType) => {
        if (!hasEntities(pkg, entityType)) return;

        const entities = entityTree[entityType] || [];
        const matchingEntities = entities.filter((entity) => entity.name.toLowerCase().includes(query));

        if (matchingEntities.length > 0) {
          matchingTypes[entityType] = matchingEntities;
          hasMatchesInPackage = true;
        }
      });

      if (hasMatchesInPackage) {
        filtered.push({ pkg, matchingTypes });
      }
    });

    return filtered;
  }, [debouncedQuery, packages, entityTrees]);

  // Auto-expand packages and entity types when searching
  useEffect(() => {
    if (debouncedQuery.trim() && filteredPackages.length > 0) {
      const packagesToExpand: string[] = [];

      setExpandedPackages((prev) => {
        const newExpanded = new Set(prev);
        filteredPackages.forEach(({ pkg }) => {
          if (!prev.has(pkg.name)) {
            packagesToExpand.push(pkg.name);
          }
          newExpanded.add(pkg.name);
        });
        return newExpanded;
      });

      setExpandedEntityTypes((prev) => {
        const newExpanded = new Set(prev);
        filteredPackages.forEach(({ pkg, matchingTypes }) => {
          Object.keys(matchingTypes).forEach((entityType) => {
            const typeKey = `${pkg.name}-${entityType}`;
            newExpanded.add(typeKey);
          });
        });
        return newExpanded;
      });

      packagesToExpand.forEach((packageName) => {
        onPackageExpand(packageName);
      });
    }
  }, [debouncedQuery, filteredPackages, onPackageExpand]);

  const handleClearSearch = useCallback(() => {
    setSearchQuery('');
  }, []);

  const handleRefreshPackages = useCallback(async () => {
    setIsRefreshing(true);
    try {
      if (onRefresh) {
        onRefresh();
      }
    } finally {
      setIsRefreshing(false);
    }
  }, [onRefresh]);

  const isSearching = debouncedQuery.trim().length > 0;

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700">
      <div className="p-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Packages</h2>
        {onRefresh && (
          <button
            onClick={handleRefreshPackages}
            disabled={isRefreshing}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors disabled:opacity-50"
            title="Refresh packages"
          >
            <RefreshCw className={`w-4 h-4 text-gray-600 dark:text-gray-400 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>
        )}
      </div>

      {/* Search Bar */}
      <div className="p-2">
        <div className="relative flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search entities..."
              className="w-full pl-8 pr-8 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-yellow-500"
            />
            {searchQuery && (
              <button
                onClick={handleClearSearch}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
                title="Clear search"
              >
                <X className="w-3.5 h-3.5 text-gray-500" />
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {packages.length === 0 ? (
          <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">No packages found</div>
        ) : isSearching && filteredPackages.length === 0 ? (
          <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">No matches found</div>
        ) : (
          filteredPackages.map(({ pkg, matchingTypes }: FilteredPackage) => (
            <PackageNode
              key={pkg.name}
              pkg={pkg}
              matchingTypes={matchingTypes}
              isExpanded={expandedPackages.has(pkg.name)}
              isSearching={isSearching}
              expandedEntityTypes={expandedEntityTypes}
              cache={cache}
              selectedEntityType={selectedEntityType}
              selectedEntityName={selectedEntityName}
              renamingEntity={renamingEntity}
              renameValue={renameValue}
              creatingEntity={creatingEntity}
              newEntityName={newEntityName}
              entityTrees={entityTrees}
              onTogglePackage={togglePackage}
              onToggleEntityType={toggleEntityType}
              onCreateStart={handleCreateEntityStart}
              onCreateConfirm={handleCreateEntityConfirm}
              onCreateCancel={handleCreateCancel}
              onNewEntityNameChange={setNewEntityName}
              onRenameValueChange={setRenameValue}
              onRenameConfirm={handleRenameConfirm}
              onRenameCancel={handleRenameCancel}
              onEntityClick={handleEntityClick}
              onContextMenu={handleContextMenu}
              onDeleteRequest={handleDeleteRequest}
            />
          ))
        )}
      </div>

      {/* Context Menu */}
      {contextMenu && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setContextMenu(null)} />
          <div
            className="fixed z-50 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded shadow-lg py-1"
            style={{ left: contextMenu.x, top: contextMenu.y }}
          >
            <button
              onClick={() => handleCreateEntityStart(contextMenu.packageName, contextMenu.entityType)}
              className="w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              New {contextMenu.entityType.slice(0, -1)}
            </button>
            {contextMenu.entityName && (
              <>
                <button
                  onClick={handleRenameStart}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                >
                  <Edit className="w-4 h-4" />
                  Rename
                </button>
                <button
                  onClick={handleDeleteFromContext}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2 text-red-600"
                >
                  <Trash2 className="w-4 h-4" />
                  Delete
                </button>
              </>
            )}
          </div>
        </>
      )}

      {deleteTarget && (
        <ConfirmationDialog
          open={deleteDialogOpen}
          onOpenChange={setDeleteDialogOpen}
          title="Delete Entity"
          description={`Are you sure you want to delete "${deleteTarget.entityName}"? This action cannot be undone.`}
          confirmLabel="Delete"
          variant="destructive"
          items={[deleteTarget.entityName]}
          onConfirm={async () => {
            await onDeleteEntity(deleteTarget.packageName, deleteTarget.entityType, deleteTarget.entityName);
            setDeleteTarget(null);
          }}
        />
      )}
    </div>
  );
}
