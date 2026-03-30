export type EntityType = 'devices' | 'tasks' | 'labs' | 'protocols';

export interface Package {
  name: string;
  path: string;
  hasDevices: boolean;
  hasTasks: boolean;
  hasLabs: boolean;
  hasProtocols: boolean;
}

export interface EntityNode {
  name: string;
  type: EntityType;
  packageName: string;
  hasYaml: boolean;
  hasPython: boolean;
}

export interface EntityTree {
  packageName: string;
  devices: EntityNode[];
  tasks: EntityNode[];
  labs: EntityNode[];
  protocols: EntityNode[];
}

export interface EntityFiles {
  yaml: string;
  python: string;
  yamlPath: string;
  pythonPath: string;
  json?: string; // Optional layout JSON for protocols
  jsonPath?: string;
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
}

// File name constants
export const ENTITY_FILE_NAMES: Record<EntityType, { yaml: string; python: string }> = {
  devices: { yaml: 'device.yml', python: 'device.py' },
  tasks: { yaml: 'task.yml', python: 'task.py' },
  labs: { yaml: 'lab.yml', python: '' }, // Labs don't have Python files
  protocols: { yaml: 'protocol.yml', python: 'optimizer.py' }, // optimizer.py is optional
};
