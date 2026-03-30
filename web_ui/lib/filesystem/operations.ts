import { promises as fs } from 'fs';
import path from 'path';
import { glob } from 'fast-glob';
import yaml from 'js-yaml';
import {
  ENTITY_FILE_NAMES,
  type EntityType,
  type Package,
  type EntityTree,
  type EntityFiles,
  type WriteFilesRequest,
} from '@/lib/types/filesystem';

export const getUserDir = () => {
  return process.env.USER_DIR || path.join(process.cwd(), '..', 'user');
};

// Entity templates for creating new entities
export const ENTITY_TEMPLATES = {
  devices: {
    yaml: `type: my_device
desc: Description of the device

# Add your device configuration here
`,
    python: `from eos.devices.base_device import BaseDevice

class MyDevice(BaseDevice):
    """Device implementation"""

    def __init__(self, config):
        super().__init__(config)

    async def initialize(self):
        """Initialize the device"""
        pass

    async def cleanup(self):
        """Cleanup the device"""
        pass
`,
  },
  tasks: {
    yaml: `type: my_task
desc: Description of the task

input_parameters: {}
output_parameters: {}

devices: {}
input_resources: {}
output_resources: {}
`,
    python: `from eos.tasks.base_task import BaseTask

class MyTask(BaseTask):
    """Task implementation"""

    async def _execute(self):
        """Execute the task"""
        pass
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
  const userDir = getUserDir();
  const packagePath = path.join(userDir, packageName);

  const tree: EntityTree = {
    packageName,
    devices: [],
    tasks: [],
    labs: [],
    protocols: [],
  };

  const entityTypes: EntityType[] = ['devices', 'tasks', 'labs', 'protocols'];

  for (const entityType of entityTypes) {
    const entityDir = path.join(packagePath, entityType);

    try {
      const entries = await fs.readdir(entityDir, { withFileTypes: true });

      for (const entry of entries) {
        if (entry.isDirectory()) {
          const entityPath = path.join(entityDir, entry.name);
          const fileNames = ENTITY_FILE_NAMES[entityType];

          const [hasYaml, hasPython] = await Promise.all([
            fs
              .access(path.join(entityPath, fileNames.yaml))
              .then(() => true)
              .catch(() => false),
            fileNames.python
              ? fs
                  .access(path.join(entityPath, fileNames.python))
                  .then(() => true)
                  .catch(() => false)
              : Promise.resolve(false),
          ]);

          tree[entityType].push({
            name: entry.name,
            type: entityType,
            packageName,
            hasYaml,
            hasPython,
          });
        }
      }

      tree[entityType].sort((a, b) => a.name.localeCompare(b.name));
    } catch {
      // Directory doesn't exist, skip
    }
  }

  return tree;
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

  const yamlPath = path.join(entityPath, fileNames.yaml);
  const pythonPath = fileNames.python ? path.join(entityPath, fileNames.python) : '';
  const jsonPath = entityType === 'protocols' ? path.join(entityPath, 'layout.json') : '';

  const yamlContent = await fs.readFile(yamlPath, 'utf-8').catch(() => '');
  const python = pythonPath ? await fs.readFile(pythonPath, 'utf-8').catch(() => '') : '';
  const json = jsonPath ? await fs.readFile(jsonPath, 'utf-8').catch(() => '') : '';

  return {
    yaml: yamlContent,
    python,
    yamlPath,
    pythonPath,
    json,
    jsonPath,
  };
}

// Write entity files
export async function writeEntityFiles(
  packageName: string,
  entityType: EntityType,
  entityName: string,
  files: WriteFilesRequest
): Promise<void> {
  const userDir = getUserDir();
  const fileNames = ENTITY_FILE_NAMES[entityType];
  const entityPath = path.join(userDir, packageName, entityType, entityName);

  // Ensure directory exists
  await fs.mkdir(entityPath, { recursive: true });

  // Write YAML file
  await fs.writeFile(path.join(entityPath, fileNames.yaml), files.yaml, 'utf-8');

  // Write Python file if applicable
  if (fileNames.python && files.python != null) {
    await fs.writeFile(path.join(entityPath, fileNames.python), files.python, 'utf-8');
  }

  // Write JSON layout file for protocols
  if (entityType === 'protocols' && files.json) {
    await fs.writeFile(path.join(entityPath, 'layout.json'), files.json, 'utf-8');
  }
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

  // Create directory
  await fs.mkdir(entityPath, { recursive: true });

  // Create files from templates
  const template = ENTITY_TEMPLATES[entityType];
  let yamlContent = template.yaml;

  // For protocols, replace the template type with the entity name
  if (entityType === 'protocols') {
    yamlContent = yamlContent.replace('type: my_protocol', `type: ${entityName}`);
  }

  await fs.writeFile(path.join(entityPath, fileNames.yaml), yamlContent, 'utf-8');

  if (fileNames.python && template.python) {
    await fs.writeFile(path.join(entityPath, fileNames.python), template.python, 'utf-8');
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
        data.type = newName;
        const newYamlContent = yaml.dump(data, { lineWidth: -1, noRefs: true });
        await fs.writeFile(yamlPath, newYamlContent, 'utf-8');
      }
    } catch (error) {
      console.error('Failed to update protocol type after rename:', error);
      // Don't fail the rename operation if we can't update the YAML
    }
  }
}
