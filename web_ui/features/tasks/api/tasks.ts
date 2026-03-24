'use server';

/**
 * Server Actions for Tasks
 *
 * Note: GET operations read from database, POST operations go to orchestrator API
 */

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import type { Task, TaskDefinition, ActionResult } from '@/lib/types/api';
import { DEFAULT_PAGE_SIZE, type TableQueryOptions } from '@/lib/types/table';
import { getAllTasks, type PaginatedResult } from '@/lib/db/queries';

export async function getTasks(options: TableQueryOptions = {}): Promise<PaginatedResult<Task>> {
  try {
    const result = await getAllTasks({ limit: DEFAULT_PAGE_SIZE, offset: 0, ...options });

    return {
      data: result.data.map((task) => ({
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
      })),
      total: result.total,
      limit: result.limit,
      offset: result.offset,
    };
  } catch (error) {
    console.error('Failed to fetch tasks:', error);
    throw new Error('Failed to fetch tasks from database');
  }
}

export async function submitTask(definition: TaskDefinition): Promise<ActionResult> {
  try {
    await orchestratorPost('/tasks/', definition);
    revalidatePath('/tasks');
    return { success: true };
  } catch (error) {
    console.error('Failed to submit task:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to submit task',
    };
  }
}

export async function cancelTask(taskName: string, experimentName?: string | null): Promise<ActionResult> {
  try {
    const params = experimentName ? `?experiment_name=${encodeURIComponent(experimentName)}` : '';
    await orchestratorPost(`/tasks/${taskName}/cancel${params}`);
    revalidatePath('/tasks');
    return { success: true };
  } catch (error) {
    console.error('Failed to cancel task:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to cancel task',
    };
  }
}
