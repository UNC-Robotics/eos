export type EntityType = 'devices' | 'tasks' | 'labs' | 'protocols';

export interface Package {
  name: string;
  path: string;
  hasDevices: boolean;
  hasTasks: boolean;
  hasLabs: boolean;
  hasProtocols: boolean;
}

export interface EntityLeafNode {
  kind: 'entity';
  name: string; // basename, e.g. "a"
  path: string; // path relative to entityDir, e.g. "test/a"
  type: EntityType;
  packageName: string;
  hasYaml: boolean;
  hasPython: boolean;
}

export interface FolderNode {
  kind: 'folder';
  name: string; // basename, e.g. "test"
  path: string; // path relative to entityDir, e.g. "test"
  children: TreeNode[];
}

export type TreeNode = FolderNode | EntityLeafNode;

export interface EntityTree {
  packageName: string;
  devices: TreeNode[];
  tasks: TreeNode[];
  labs: TreeNode[];
  protocols: TreeNode[];
}

export interface EntityFiles {
  yaml: string;
  python: string;
  yamlPath: string;
  pythonPath: string;
  json?: string; // Optional layout JSON for protocols
  jsonPath?: string;
  mtime: number; // Max mtime across entity files (Unix epoch ms)
}

export interface ValidationError {
  line?: number;
  column?: number;
  message: string;
  severity: 'error' | 'warning';
}

export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
}

export interface CreateEntityRequest {
  packageName: string;
  entityType: EntityType;
  entityName: string;
}

export interface WriteFilesRequest {
  yaml: string;
  python: string;
  json?: string; // Optional layout JSON for protocols
  expectedMtime?: number; // If set, reject write when disk mtime is newer
}

// File name constants. An empty name means the entity type has no file of that kind.
export const ENTITY_FILE_NAMES: Record<EntityType, { yaml: string; python: string }> = {
  devices: { yaml: '', python: 'device.py' },
  tasks: { yaml: '', python: 'task.py' },
  labs: { yaml: 'lab.yml', python: '' },
  protocols: { yaml: 'protocol.yml', python: 'optimizer.py' }, // optimizer.py is optional
};

/** The file whose presence marks a directory as an entity. */
export function entityMarkerFile(entityType: EntityType): string {
  const { yaml, python } = ENTITY_FILE_NAMES[entityType];
  return yaml || python;
}
