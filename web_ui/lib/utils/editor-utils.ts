import yaml from 'js-yaml';
import type { EntityType, ValidationError, ValidationResult } from '@/lib/types/filesystem';
import { ENTITY_FILE_NAMES } from '@/lib/types/filesystem';

/**
 * Detects if content contains Jinja2 template syntax
 */
export function hasJinjaSyntax(content: string): boolean {
  const jinjaPatterns = [
    /\{\{.*?\}\}/, // Variables: {{ variable }}
    /\{%.*?%\}/, // Statements: {% if %}, {% for %}, etc.
    /\{#.*?#\}/, // Comments: {# comment #}
  ];

  return jinjaPatterns.some((pattern) => pattern.test(content));
}

/**
 * Parse YAML content safely
 */
export function parseYaml(content: string): { data: unknown; error: string | null } {
  try {
    const data = yaml.load(content);
    return { data, error: null };
  } catch (error) {
    if (error instanceof Error) {
      return { data: null, error: error.message };
    }
    return { data: null, error: 'Unknown YAML parsing error' };
  }
}

/**
 * Serialize object to YAML with formatting
 */
export function serializeYaml(data: unknown): string {
  try {
    const raw = yaml.dump(data, {
      indent: 2,
      lineWidth: 120,
      noRefs: true,
      sortKeys: false,
    });

    // Add blank lines before top-level 'labs:' and 'tasks:' keys,
    // and between each task entry (- name: ...) except the last.
    const lines = raw.split('\n');
    const result: string[] = [];
    let inTasks = false;
    let seenFirstTask = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // Blank line before top-level 'labs:' and 'tasks:'
      if (/^(labs|tasks):/.test(line) && result.length > 0) {
        result.push('');
      }

      // Blank line between task entries (before '  - name:' except the first)
      if (inTasks && /^\s{2}- name:/.test(line)) {
        if (seenFirstTask) {
          result.push('');
        }
        seenFirstTask = true;
      }

      if (/^tasks:/.test(line)) {
        inTasks = true;
      } else if (inTasks && /^\S/.test(line)) {
        inTasks = false;
      }

      result.push(line);
    }

    return result.join('\n');
  } catch (error) {
    console.error('YAML serialization error:', error);
    return '';
  }
}

/**
 * Extract hold flags from raw YAML-parsed task objects into separate device_holds/resource_holds maps.
 * Normalizes reference-with-hold objects ({ref: "...", hold: true}) back to plain strings,
 * and strips the hold field from static/dynamic assignment objects.
 */
export function extractHoldsFromRawTasks(tasks: Record<string, unknown>[]): Record<string, unknown>[] {
  return tasks.map((rawTask) => {
    const task = { ...rawTask };
    const deviceHolds: Record<string, boolean> = {};
    const resourceHolds: Record<string, boolean> = {};

    if (task.devices && typeof task.devices === 'object') {
      const devices: Record<string, unknown> = {};
      for (const [slot, raw] of Object.entries(task.devices as Record<string, unknown>)) {
        if (raw && typeof raw === 'object') {
          const obj = raw as Record<string, unknown>;
          if ('ref' in obj) {
            if (obj.hold === true) deviceHolds[slot] = true;
            devices[slot] = obj.ref;
          } else if (obj.hold === true) {
            deviceHolds[slot] = true;
            const { hold: _, ...rest } = obj;
            devices[slot] = rest;
          } else {
            devices[slot] = raw;
          }
        } else {
          devices[slot] = raw;
        }
      }
      task.devices = devices;
    }

    if (task.resources && typeof task.resources === 'object') {
      const resources: Record<string, unknown> = {};
      for (const [slot, raw] of Object.entries(task.resources as Record<string, unknown>)) {
        if (raw && typeof raw === 'object') {
          const obj = raw as Record<string, unknown>;
          if ('ref' in obj) {
            if (obj.hold === true) resourceHolds[slot] = true;
            resources[slot] = obj.ref;
          } else if ('name' in obj && !('allocation_type' in obj)) {
            if (obj.hold === true) resourceHolds[slot] = true;
            resources[slot] = obj.name;
          } else if (obj.hold === true) {
            resourceHolds[slot] = true;
            const { hold: _, ...rest } = obj;
            resources[slot] = rest;
          } else {
            resources[slot] = raw;
          }
        } else {
          resources[slot] = raw;
        }
      }
      task.resources = resources;
    }

    if (Object.keys(deviceHolds).length > 0) task.device_holds = deviceHolds;
    if (Object.keys(resourceHolds).length > 0) task.resource_holds = resourceHolds;

    return task;
  });
}

/**
 * Validate YAML content
 */
export function validateYaml(content: string): ValidationResult {
  const errors: ValidationError[] = [];

  try {
    yaml.load(content);
  } catch (error: unknown) {
    const err = error as { mark?: { line?: number; column?: number }; message?: string };
    errors.push({
      line: err.mark?.line,
      column: err.mark?.column,
      message: err.message || 'YAML parsing error',
      severity: 'error',
    });
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

/**
 * Check if entity type has a Python file
 */
export function entityHasPythonFile(entityType: EntityType): boolean {
  return ENTITY_FILE_NAMES[entityType].python !== '';
}

/**
 * Get entity file paths
 */
export function getEntityFilePaths(
  userDir: string,
  packageName: string,
  entityType: EntityType,
  entityName: string
): { yamlPath: string; pythonPath: string } {
  const basePath = `${userDir}/${packageName}/${entityType}/${entityName}`;
  const fileNames = ENTITY_FILE_NAMES[entityType];

  return {
    yamlPath: `${basePath}/${fileNames.yaml}`,
    pythonPath: fileNames.python ? `${basePath}/${fileNames.python}` : '',
  };
}

/**
 * Validate entity name (lowercase, alphanumeric + underscores)
 */
export function validateEntityName(name: string): { valid: boolean; error?: string } {
  if (!name) {
    return { valid: false, error: 'Name is required' };
  }

  if (!/^[a-z0-9_]+$/.test(name)) {
    return {
      valid: false,
      error: 'Name must be lowercase alphanumeric with underscores only',
    };
  }

  if (name.startsWith('_') || name.endsWith('_')) {
    return {
      valid: false,
      error: 'Name cannot start or end with underscore',
    };
  }

  return { valid: true };
}

/**
 * Get icon name for entity type (Lucide React icon)
 */
export function getEntityIcon(entityType: EntityType): string {
  const icons: Record<EntityType, string> = {
    devices: 'Cpu',
    tasks: 'Settings',
    labs: 'FlaskConical',
    protocols: 'Microscope',
  };
  return icons[entityType];
}

/**
 * Get color for entity type
 */
export function getEntityColor(entityType: EntityType): string {
  const colors: Record<EntityType, string> = {
    devices: 'text-blue-600 dark:text-blue-400',
    tasks: 'text-green-600 dark:text-green-400',
    labs: 'text-purple-600 dark:text-purple-400',
    protocols: 'text-orange-600 dark:text-orange-400',
  };
  return colors[entityType];
}
