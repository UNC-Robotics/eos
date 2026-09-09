'use server';

/**
 * Server Actions for Entity Reloading
 */

import path from 'path';
import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import { requireRole, requireSuperuser } from '@/lib/auth/authz';

export interface ActionResult {
  success: boolean;
  error?: string;
  message?: string;
}

export type EntityType = 'protocols' | 'labs' | 'tasks' | 'devices';
type EntityAction = 'load' | 'unload' | 'reload';

// The editor identifies entities by their path relative to the entity dir (e.g. "test/a"),
// but the orchestrator loads by the YAML `type:` field, which conventionally matches the
// folder basename. Strip any parent-folder prefix before sending to the orchestrator.
const toTypeName = (entityName: string) => path.posix.basename(entityName);

const ACTION_PAST_TENSE: Record<EntityAction, string> = {
  load: 'Loaded',
  unload: 'Unloaded',
  reload: 'Reloaded',
};

export interface ReloadOptions {
  /** If true, the orchestrator silently skips entities that are in use or not loaded. */
  ifUnused?: boolean;
}

// Build the orchestrator endpoint + request body for (action, entityType).
// Devices use a lab-scoped path when labName is provided.
function buildRequest(
  action: EntityAction,
  entityType: EntityType,
  typeName: string,
  labName: string | undefined,
  options: ReloadOptions
): { path: string; body: Record<string, unknown> } {
  // if_unused is only honored by the task and protocol reload endpoints.
  const includeFlag = action === 'reload' && options.ifUnused && (entityType === 'tasks' || entityType === 'protocols');
  const flag = includeFlag ? { if_unused: true } : {};

  switch (entityType) {
    case 'protocols':
      return { path: `/protocols/${action}`, body: { protocol_types: [typeName], ...flag } };
    case 'labs':
      return { path: `/labs/${action}`, body: { lab_types: [typeName] } };
    case 'tasks':
      return { path: `/tasks/${action}`, body: { task_types: [typeName], ...flag } };
    case 'devices':
      return {
        path: labName ? `/labs/${labName}/devices/${action}` : `/devices/${action}`,
        body: { device_names: [typeName] },
      };
  }
}

async function entityAction(
  action: EntityAction,
  entityType: EntityType,
  entityName: string,
  labName?: string,
  options: ReloadOptions = {}
): Promise<ActionResult> {
  if (entityType === 'devices' && !labName) {
    return { success: false, error: `Lab name is required for device ${action}` };
  }

  try {
    // Loading whole labs is superuser-only; protocols/tasks/devices are lab admin.
    if (entityType === 'labs') {
      await requireSuperuser();
    } else {
      await requireRole('LAB_ADMIN');
    }
    const { path: endpoint, body } = buildRequest(action, entityType, toTypeName(entityName), labName, options);
    await orchestratorPost(endpoint, body);

    revalidatePath('/editor');
    revalidatePath('/management');

    const verb = ACTION_PAST_TENSE[action];
    return { success: true, message: `${verb} ${entityType.slice(0, -1)} '${entityName}' successfully` };
  } catch (error) {
    console.error(`Failed to ${action} ${entityType} ${entityName}:`, error);
    return {
      success: false,
      error: error instanceof Error ? error.message : `Failed to ${action} ${entityType}`,
    };
  }
}

export async function loadEntity(entityType: EntityType, entityName: string, labName?: string): Promise<ActionResult> {
  return entityAction('load', entityType, entityName, labName);
}

export async function unloadEntity(
  entityType: EntityType,
  entityName: string,
  labName?: string
): Promise<ActionResult> {
  return entityAction('unload', entityType, entityName, labName);
}

export async function reloadEntity(
  entityType: EntityType,
  entityName: string,
  labName?: string,
  options: ReloadOptions = {}
): Promise<ActionResult> {
  return entityAction('reload', entityType, entityName, labName, options);
}
