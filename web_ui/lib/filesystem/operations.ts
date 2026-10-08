import { promises as fs } from 'fs';
import path from 'path';
import { glob } from 'fast-glob';
import yaml from 'js-yaml';
import {
  ENTITY_FILE_NAMES,
  entityMarkerFile,
  type EntityType,
  type Package,
  type EntityTree,
  type EntityFiles,
  type TreeNode,
  type WriteFilesRequest,
} from '@/lib/types/filesystem';

export const getUserDir = () => {
  return process.env.USER_DIR || path.join(process.cwd(), '..', 'user');
};

const MAX_TREE_DEPTH = 16;
const IGNORED_DIR_NAMES = new Set(['__pycache__', 'node_modules', '.venv', 'venv']);

function sortTreeNodes(nodes: TreeNode[]): void {
  nodes.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'folder' ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

async function walkEntityDir(
  absDir: string,
  relDir: string,
  entityType: EntityType,
  packageName: string,
  depth: number
): Promise<TreeNode[]> {
  if (depth >= MAX_TREE_DEPTH) return [];

  const { yaml: yamlFile, python: pythonFile } = ENTITY_FILE_NAMES[entityType];
  const markerFile = entityMarkerFile(entityType);
  let entries;
  try {
    entries = await fs.readdir(absDir, { withFileTypes: true });
  } catch {
    return [];
  }

  let yamlPresent = false;
  let pythonPresent = false;
  const childDirs: string[] = [];
  for (const entry of entries) {
    if (entry.isFile()) {
      if (yamlFile && entry.name === yamlFile) yamlPresent = true;
      else if (pythonFile && entry.name === pythonFile) pythonPresent = true;
    } else if (entry.isDirectory() && !entry.name.startsWith('.') && !IGNORED_DIR_NAMES.has(entry.name)) {
      childDirs.push(entry.name);
    }
  }

  // Leaf: a directory containing the entity's marker file is a terminal entity.
  // The root entityDir itself is never a leaf (relDir === '').
  const markerPresent = markerFile === yamlFile ? yamlPresent : pythonPresent;
  if (markerPresent && relDir !== '') {
    return [
      {
        kind: 'entity',
        name: path.basename(relDir),
        path: relDir,
        type: entityType,
        packageName,
        hasYaml: yamlPresent,
        hasPython: pythonPresent,
      },
    ];
  }

  const childResults = await Promise.all(
    childDirs.map((name) =>
      walkEntityDir(
        path.join(absDir, name),
        relDir ? path.posix.join(relDir, name) : name,
        entityType,
        packageName,
        depth + 1
      )
    )
  );

  const out: TreeNode[] = [];
  for (let i = 0; i < childDirs.length; i++) {
    const name = childDirs[i];
    const sub = childResults[i];
    if (sub.length === 0) continue; // hide empty subtree
    const childRel = relDir ? path.posix.join(relDir, name) : name;
    if (sub.length === 1 && sub[0].kind === 'entity' && sub[0].path === childRel) {
      out.push(sub[0]);
    } else {
      out.push({ kind: 'folder', name, path: childRel, children: sub });
    }
  }
  sortTreeNodes(out);
  return out;
}

// Entity templates for creating new entities. __NAME__ and __CLASS__ are replaced with the entity name.
export const ENTITY_TEMPLATES = {
  devices: {
    yaml: '',
    python: `from eos import Device


class __CLASS__(Device, type="__NAME__"):
    """Description of the device."""
`,
  },
  tasks: {
    yaml: '',
    python: `from eos import task


@task("__NAME__")
async def __NAME__() -> None:
    """Description of the task."""
`,
  },
  labs: {
    yaml: `name: my_lab
desc: Description of the lab

computers: {}
devices: {}
`,
    python: '',
  },
  protocols: {
    yaml: `type: my_protocol
desc: Description of the protocol

labs: []

tasks: []
`,
    python: `from bofire.data_models.acquisition_functions.acquisition_function import qLogNEI
from bofire.data_models.enum import SamplingMethodEnum
from bofire.data_models.features.continuous import ContinuousInput, ContinuousOutput
from bofire.data_models.features.discrete import DiscreteInput
from bofire.data_models.objectives.identity import MinimizeObjective

from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer
from eos.optimization.beacon_optimizer import BeaconOptimizer


def eos_create_campaign_optimizer() -> tuple[dict, type[AbstractSequentialOptimizer]]:
    constructor_args = {
        "inputs": [],
        "outputs": [],
        "constraints": [],
        "acquisition_function": qLogNEI(),
        "num_initial_samples": 2,
        "initial_sampling_method": SamplingMethodEnum.SOBOL,
        "p_bayesian": 1.0,
        "p_ai": 0.0,
    }

    return constructor_args, BeaconOptimizer
`,
  },
};

// Scan for packages (directories with pyproject.toml and at least one entity directory)
export async function scanPackages(): Promise<Package[]> {
  const userDir = getUserDir();

  try {
    await fs.access(userDir);
  } catch {
    return [];
  }

  // Search recursively for pyproject.toml files (supports nested packages like eos_examples/*)
  const pyprojectFiles = await glob('**/pyproject.toml', {
    cwd: userDir,
    ignore: ['**/node_modules/**', '**/.venv/**', '**/venv/**'],
  });
  const packages: Package[] = [];

  for (const file of pyprojectFiles) {
    const packageName = path.dirname(file);
    const packagePath = path.join(userDir, packageName);

    // Check which entity types exist
    const [hasDevices, hasTasks, hasLabs, hasProtocols] = await Promise.all([
      fs
        .access(path.join(packagePath, 'devices'))
        .then(() => true)
        .catch(() => false),
      fs
        .access(path.join(packagePath, 'tasks'))
        .then(() => true)
        .catch(() => false),
      fs
        .access(path.join(packagePath, 'labs'))
        .then(() => true)
        .catch(() => false),
      fs
        .access(path.join(packagePath, 'protocols'))
        .then(() => true)
        .catch(() => false),
    ]);

    // Only include if it has at least one entity directory (valid EOS package)
    if (hasDevices || hasTasks || hasLabs || hasProtocols) {
      packages.push({
        name: packageName,
        path: packagePath,
        hasDevices,
        hasTasks,
        hasLabs,
        hasProtocols,
      });
    }
  }

  return packages.sort((a, b) => a.name.localeCompare(b.name));
}

// Get entity tree for a package
export async function getPackageTree(packageName: string): Promise<EntityTree> {
  const packagePath = path.join(getUserDir(), packageName);
  const entityTypes: EntityType[] = ['devices', 'tasks', 'labs', 'protocols'];

  const results = await Promise.all(
    entityTypes.map((type) => walkEntityDir(path.join(packagePath, type), '', type, packageName, 0))
  );

  return {
    packageName,
    devices: results[0],
    tasks: results[1],
    labs: results[2],
    protocols: results[3],
  };
}

// Get max mtime across all files belonging to an entity
async function getEntityMtime(entityPath: string, entityType: EntityType): Promise<number> {
  const fileNames = ENTITY_FILE_NAMES[entityType];
  const paths = [fileNames.yaml, fileNames.python].filter(Boolean).map((name) => path.join(entityPath, name));
  if (entityType === 'protocols') paths.push(path.join(entityPath, 'layout.json'));

  const mtimes = await Promise.all(
    paths.map((p) =>
      fs
        .stat(p)
        .then((s) => s.mtimeMs)
        .catch(() => 0)
    )
  );
  return Math.max(...mtimes);
}

// Lightweight mtime-only check (no file reads)
export async function getEntityMtimeOnly(
  packageName: string,
  entityType: EntityType,
  entityName: string
): Promise<number | null> {
  const entityPath = path.join(getUserDir(), packageName, entityType, entityName);
  try {
    await fs.access(entityPath);
  } catch {
    return null;
  }
  return getEntityMtime(entityPath, entityType);
}

// Read entity files
export async function readEntityFiles(
  packageName: string,
  entityType: EntityType,
  entityName: string
): Promise<EntityFiles | null> {
  const userDir = getUserDir();
  const fileNames = ENTITY_FILE_NAMES[entityType];
  const entityPath = path.join(userDir, packageName, entityType, entityName);

  // Check if entity directory exists
  try {
    await fs.access(entityPath);
  } catch {
    return null;
  }

  const yamlPath = fileNames.yaml ? path.join(entityPath, fileNames.yaml) : '';
  const pythonPath = fileNames.python ? path.join(entityPath, fileNames.python) : '';
  const jsonPath = entityType === 'protocols' ? path.join(entityPath, 'layout.json') : '';

  const [yamlContent, python, json, mtime] = await Promise.all([
    yamlPath ? fs.readFile(yamlPath, 'utf-8').catch(() => '') : Promise.resolve(''),
    pythonPath ? fs.readFile(pythonPath, 'utf-8').catch(() => '') : Promise.resolve(''),
    jsonPath ? fs.readFile(jsonPath, 'utf-8').catch(() => '') : Promise.resolve(''),
    getEntityMtime(entityPath, entityType),
  ]);

  return {
    yaml: yamlContent,
    python,
    yamlPath,
    pythonPath,
    json,
    jsonPath,
    mtime,
  };
}

// Write entity files with optional optimistic concurrency check
export async function writeEntityFiles(
  packageName: string,
  entityType: EntityType,
  entityName: string,
  files: WriteFilesRequest
): Promise<{ conflict: boolean; mtime: number }> {
  const userDir = getUserDir();
  const fileNames = ENTITY_FILE_NAMES[entityType];
  const entityPath = path.join(userDir, packageName, entityType, entityName);

  // Conflict check: reject if disk is newer than what the client last saw
  if (files.expectedMtime != null) {
    const currentMtime = await getEntityMtime(entityPath, entityType);
    if (currentMtime > files.expectedMtime) {
      return { conflict: true, mtime: currentMtime };
    }
  }

  // Ensure directory exists
  await fs.mkdir(entityPath, { recursive: true });

  // Write YAML file if applicable
  if (fileNames.yaml) {
    await fs.writeFile(path.join(entityPath, fileNames.yaml), files.yaml, 'utf-8');
  }

  // Write Python file if applicable
  if (fileNames.python && files.python != null) {
    await fs.writeFile(path.join(entityPath, fileNames.python), files.python, 'utf-8');
  }

  // Write JSON layout file for protocols
  if (entityType === 'protocols' && files.json) {
    await fs.writeFile(path.join(entityPath, 'layout.json'), files.json, 'utf-8');
  }

  const newMtime = await getEntityMtime(entityPath, entityType);
  return { conflict: false, mtime: newMtime };
}

// Create new entity
export async function createEntity(packageName: string, entityType: EntityType, entityName: string): Promise<void> {
  const userDir = getUserDir();
  const fileNames = ENTITY_FILE_NAMES[entityType];
  const entityPath = path.join(userDir, packageName, entityType, entityName);

  // Check if entity already exists
  try {
    await fs.access(entityPath);
    throw new Error('Entity already exists');
  } catch (err: unknown) {
    if (err instanceof Error && err.message === 'Entity already exists') throw err;
    // Directory doesn't exist, which is what we want
  }

  // Task and device templates use the name as a Python identifier
  const template = ENTITY_TEMPLATES[entityType];
  const name = path.basename(entityName);
  if (template.python && fileNames.python && !/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
    throw new Error(`'${name}' is not a valid Python identifier`);
  }

  // Create directory
  await fs.mkdir(entityPath, { recursive: true });

  // Create files from templates
  const className = name
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('');
  let yamlContent = template.yaml;

  // For protocols, replace the template type with the entity name
  if (entityType === 'protocols') {
    yamlContent = yamlContent.replace('type: my_protocol', `type: ${entityName}`);
  }

  if (fileNames.yaml) {
    await fs.writeFile(path.join(entityPath, fileNames.yaml), yamlContent, 'utf-8');
  }

  if (fileNames.python && template.python) {
    const python = template.python.replaceAll('__NAME__', name).replaceAll('__CLASS__', className);
    await fs.writeFile(path.join(entityPath, fileNames.python), python, 'utf-8');
  }
}

// Delete entity
export async function deleteEntity(packageName: string, entityType: EntityType, entityName: string): Promise<void> {
  const userDir = getUserDir();
  const entityPath = path.join(userDir, packageName, entityType, entityName);

  await fs.rm(entityPath, { recursive: true, force: true });
}

// Rename entity
export async function renameEntity(
  packageName: string,
  entityType: EntityType,
  oldName: string,
  newName: string
): Promise<void> {
  const userDir = getUserDir();
  const oldPath = path.join(userDir, packageName, entityType, oldName);
  const newPath = path.join(userDir, packageName, entityType, newName);

  // Check if old path exists
  try {
    await fs.access(oldPath);
  } catch {
    throw new Error('Entity not found');
  }

  // Check if new name already exists
  try {
    await fs.access(newPath);
    throw new Error('An entity with that name already exists');
  } catch (err: unknown) {
    if (err instanceof Error && err.message === 'An entity with that name already exists') throw err;
    // Path doesn't exist, which is what we want
  }

  // Rename the directory
  await fs.rename(oldPath, newPath);

  // For protocols, also update the type field in the YAML to match the new name
  if (entityType === 'protocols') {
    const fileNames = ENTITY_FILE_NAMES[entityType];
    const yamlPath = path.join(newPath, fileNames.yaml);

    try {
      const yamlContent = await fs.readFile(yamlPath, 'utf-8');
      const data = yaml.load(yamlContent) as { type?: string };

      if (data && data.type) {
        data.type = path.basename(newName);
        const newYamlContent = yaml.dump(data, { lineWidth: -1, noRefs: true });
        await fs.writeFile(yamlPath, newYamlContent, 'utf-8');
      }
    } catch (error) {
      console.error('Failed to update protocol type after rename:', error);
      // Don't fail the rename operation if we can't update the YAML
    }
  }
}
