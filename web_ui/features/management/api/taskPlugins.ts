'use server';

/**
 * Server Actions for Task Plugin Management
 */

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import { requireRole } from '@/lib/auth/authz';
import { db } from '@/lib/db/client';
import { definitions } from '@/lib/db/schema';
import { eq } from 'drizzle-orm';
import type { TaskPluginInfo, ActionResult } from '@/lib/types/management';

/**
 * Get all task types with their definitions from the database
 */
export async function getTaskPlugins(): Promise<TaskPluginInfo[]> {
  try {
    const results = await db
      .select({
        type: definitions.name,
        data: definitions.data,
        packageName: definitions.packageName,
      })
      .from(definitions)
      .where(eq(definitions.type, 'task'));

    return results.map((row) => {
      const taskDef = row.data as { type: string; desc?: string };
      return {
        type: taskDef.type,
        description: taskDef.desc,
        package: row.packageName,
      };
    });
  } catch (error) {
    console.error('Failed to fetch task plugins:', error);
    throw new Error('Failed to fetch task plugins from database');
  }
}

/**
 * Reload task plugins
 */
export async function reloadTaskPlugins(taskTypes: string[]): Promise<ActionResult> {
  try {
    await requireRole('LAB_ADMIN');
    await orchestratorPost('/tasks/reload', {
      task_types: taskTypes,
    });

    // Revalidate the management page to show updated status
    revalidatePath('/management');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to reload task plugins:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to reload task plugins',
    };
  }
}
