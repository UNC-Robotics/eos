'use server';

/**
 * Server Actions for Tasks
 *
 * Note: GET operations read from database, POST operations go to orchestrator API
 */

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import type { Task, TaskDefinition, ActionResult } from '@/lib/types/api';
import { getAllTasks } from '@/lib/db/queries';

/**
 * Get tasks from database with server-side pagination
 * Default limit: 50 tasks per page
 */
export async function getTasks(): Promise<Task[]> {
  try {
    // Fetch first page with reasonable limit
    const result = await getAllTasks({ limit: 100, offset: 0 });

    return result.data.map((task) => ({
      ...task,
      created_at: task.createdAt.toISOString(),
      start_time: task.startTime?.toISOString() ?? null,
      end_time: task.endTime?.toISOString() ?? null,
      status: task.status as Task['status'],
      devices: (task.devices as Task['devices']) || {},
      input_parameters: task.inputParameters,
      input_resources: task.inputResources,
      output_parameters: task.outputParameters,
      output_resources: task.outputResources,
      output_file_names: task.outputFileNames,
      priority: task.priority,
      allocation_timeout: task.allocationTimeout,
      meta: task.meta,
      experiment_name: task.experimentName,
    }));
  } catch (error) {
    console.error('Failed to fetch tasks:', error);
    throw new Error('Failed to fetch tasks from database');
  }
}

/**
 * Submit a new task
 */
export async function submitTask(definition: TaskDefinition): Promise<ActionResult> {
  try {
    await orchestratorPost('/tasks/', definition);

    // Revalidate the tasks page to show the new task
    revalidatePath('/tasks');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to submit task:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to submit task',
    };
  }
}

/**
 * Cancel a running task
 * For tasks belonging to an experiment, provide the experimentName parameter
 */
export async function cancelTask(taskName: string, experimentName?: string | null): Promise<ActionResult> {
  try {
    const params = experimentName ? `?experiment_name=${encodeURIComponent(experimentName)}` : '';
    await orchestratorPost(`/tasks/${taskName}/cancel${params}`);

    // Revalidate the tasks page to show updated status
    revalidatePath('/tasks');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to cancel task:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to cancel task',
    };
  }
}
