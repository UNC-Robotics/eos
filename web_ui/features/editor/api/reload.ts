'use server';

/**
 * Server Actions for Entity Reloading
 */

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';

export interface ActionResult {
  success: boolean;
  error?: string;
  message?: string;
}

export type EntityType = 'experiments' | 'labs' | 'tasks' | 'devices';

/**
 * Load a specific entity (experiment, lab, or device).
 * This triggers the EOS orchestrator to load the entity.
 *
 * @param entityType - The type of entity to load
 * @param entityName - The name of the entity to load
 * @param labName - Required for device loads, optional otherwise
 */
export async function loadEntity(entityType: EntityType, entityName: string, labName?: string): Promise<ActionResult> {
  try {
    // Map entity type to appropriate API endpoint and request body
    const endpointConfig = {
      experiments: {
        path: '/experiments/load',
        body: { experiment_types: [entityName] },
      },
      labs: {
        path: '/labs/load',
        body: { lab_types: [entityName] },
      },
      tasks: {
        path: '/tasks/load',
        body: { task_types: [entityName] },
      },
      devices: {
        path: labName ? `/labs/${labName}/devices/load` : '/devices/load',
        body: { device_names: [entityName] },
      },
    };

    const config = endpointConfig[entityType];

    if (!config) {
      return {
        success: false,
        error: `Invalid entity type: ${entityType}`,
      };
    }

    // For devices, lab name is required
    if (entityType === 'devices' && !labName) {
      return {
        success: false,
        error: 'Lab name is required for device load',
      };
    }

    await orchestratorPost(config.path, config.body);

    // Revalidate both editor and management pages
    revalidatePath('/editor');
    revalidatePath('/management');

    return {
      success: true,
      message: `Loaded ${entityType.slice(0, -1)} '${entityName}' successfully`,
    };
  } catch (error) {
    console.error(`Failed to load ${entityType} ${entityName}:`, error);
    return {
      success: false,
      error: error instanceof Error ? error.message : `Failed to load ${entityType}`,
    };
  }
}

/**
 * Unload a specific entity (experiment or lab).
 * This triggers the EOS orchestrator to unload the entity.
 *
 * @param entityType - The type of entity to unload
 * @param entityName - The name of the entity to unload
 * @param labName - Required for device unloads, optional otherwise
 */
export async function unloadEntity(
  entityType: EntityType,
  entityName: string,
  labName?: string
): Promise<ActionResult> {
  try {
    // Map entity type to appropriate API endpoint and request body
    const endpointConfig = {
      experiments: {
        path: '/experiments/unload',
        body: { experiment_types: [entityName] },
      },
      labs: {
        path: '/labs/unload',
        body: { lab_types: [entityName] },
      },
      tasks: {
        path: '/tasks/unload',
        body: { task_types: [entityName] },
      },
      devices: {
        path: labName ? `/labs/${labName}/devices/unload` : '/devices/unload',
        body: { device_names: [entityName] },
      },
    };

    const config = endpointConfig[entityType];

    if (!config) {
      return {
        success: false,
        error: `Invalid entity type: ${entityType}`,
      };
    }

    // For devices, lab name is required
    if (entityType === 'devices' && !labName) {
      return {
        success: false,
        error: 'Lab name is required for device unload',
      };
    }

    await orchestratorPost(config.path, config.body);

    // Revalidate both editor and management pages
    revalidatePath('/editor');
    revalidatePath('/management');

    return {
      success: true,
      message: `Unloaded ${entityType.slice(0, -1)} '${entityName}' successfully`,
    };
  } catch (error) {
    console.error(`Failed to unload ${entityType} ${entityName}:`, error);
    return {
      success: false,
      error: error instanceof Error ? error.message : `Failed to unload ${entityType}`,
    };
  }
}

/**
 * Reload a specific entity (experiment, lab, task, or device).
 * This triggers the EOS orchestrator to reload the entity's code from disk.
 *
 * @param entityType - The type of entity to reload
 * @param entityName - The name of the entity to reload
 * @param labName - Required for device reloads, optional otherwise
 */
export async function reloadEntity(
  entityType: EntityType,
  entityName: string,
  labName?: string
): Promise<ActionResult> {
  try {
    // Map entity type to appropriate API endpoint and request body
    const endpointConfig = {
      experiments: {
        path: '/experiments/reload',
        body: { experiment_types: [entityName] },
      },
      labs: {
        path: '/labs/reload',
        body: { lab_types: [entityName] },
      },
      tasks: {
        path: '/tasks/reload',
        body: { task_types: [entityName] },
      },
      devices: {
        path: labName ? `/labs/${labName}/devices/reload` : '/devices/reload',
        body: { device_names: [entityName] },
      },
    };

    const config = endpointConfig[entityType];

    if (!config) {
      return {
        success: false,
        error: `Invalid entity type: ${entityType}`,
      };
    }

    // For devices, lab name is required
    if (entityType === 'devices' && !labName) {
      return {
        success: false,
        error: 'Lab name is required for device reload',
      };
    }

    await orchestratorPost(config.path, config.body);

    // Revalidate both editor and management pages
    revalidatePath('/editor');
    revalidatePath('/management');

    return {
      success: true,
      message: `Reloaded ${entityType.slice(0, -1)} '${entityName}' successfully`,
    };
  } catch (error) {
    console.error(`Failed to reload ${entityType} ${entityName}:`, error);
    return {
      success: false,
      error: error instanceof Error ? error.message : `Failed to reload ${entityType}`,
    };
  }
}
