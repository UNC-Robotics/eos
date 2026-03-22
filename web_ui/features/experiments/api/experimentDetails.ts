'use server';

import {
  getExperimentByName,
  getTasksByExperiment,
  getTaskStatusesByExperiment,
  getTaskByName,
  ExperimentRow,
  TaskRow,
  TaskStatusRow,
} from '@/lib/db/queries';
import type { Experiment, Task, TaskStatus, TaskDeviceConfig } from '@/lib/types/api';

export interface TaskStatusInfo {
  name: string;
  type: string;
  status: TaskStatus;
}

function transformDbExperiment(exp: ExperimentRow): Experiment {
  return {
    name: exp.name,
    type: exp.type,
    owner: exp.owner,
    priority: exp.priority,
    parameters: exp.parameters || {},
    meta: exp.meta ?? null,
    resume: exp.resume,
    status: exp.status as Experiment['status'],
    error_message: exp.errorMessage ?? null,
    created_at: exp.createdAt.toISOString(),
    start_time: exp.startTime?.toISOString() ?? null,
    end_time: exp.endTime?.toISOString() ?? null,
  };
}

function transformDbTask(task: TaskRow): Task {
  return {
    name: task.name,
    experiment_name: task.experimentName,
    type: task.type,
    devices: task.devices as Record<string, TaskDeviceConfig>,
    input_parameters: task.inputParameters ?? null,
    input_resources: task.inputResources ?? null,
    output_parameters: task.outputParameters ?? null,
    output_resources: task.outputResources ?? null,
    output_file_names: task.outputFileNames ?? null,
    priority: task.priority,
    allocation_timeout: task.allocationTimeout,
    meta: task.meta,
    status: task.status as Task['status'],
    error_message: task.errorMessage ?? null,
    created_at: task.createdAt.toISOString(),
    start_time: task.startTime?.toISOString() ?? null,
    end_time: task.endTime?.toISOString() ?? null,
  };
}

export async function getExperimentDetails(experimentName: string): Promise<{
  experiment: Experiment | null;
  tasks: Task[];
}> {
  try {
    const [experimentRow, taskRows] = await Promise.all([
      getExperimentByName(experimentName),
      getTasksByExperiment(experimentName),
    ]);

    if (!experimentRow) {
      return { experiment: null, tasks: [] };
    }

    return {
      experiment: transformDbExperiment(experimentRow),
      tasks: taskRows.map(transformDbTask),
    };
  } catch (error) {
    console.error('Failed to fetch experiment details:', error);
    throw new Error('Failed to fetch experiment details');
  }
}

export async function getExperimentTasks(experimentName: string): Promise<Task[]> {
  try {
    const taskRows = await getTasksByExperiment(experimentName);
    return taskRows.map(transformDbTask);
  } catch (error) {
    console.error('Failed to fetch experiment tasks:', error);
    throw new Error('Failed to fetch experiment tasks');
  }
}

export async function getTaskStatuses(experimentName: string): Promise<TaskStatusInfo[]> {
  try {
    const statusRows = await getTaskStatusesByExperiment(experimentName);
    return statusRows.map((row: TaskStatusRow) => ({
      name: row.name,
      type: row.type,
      status: row.status as TaskStatus,
    }));
  } catch (error) {
    console.error('Failed to fetch task statuses:', error);
    throw new Error('Failed to fetch task statuses');
  }
}

export async function getTaskDetails(taskName: string, experimentName: string): Promise<Task | null> {
  try {
    const taskRow = await getTaskByName(taskName, experimentName);
    if (!taskRow) return null;
    return transformDbTask(taskRow);
  } catch (error) {
    console.error('Failed to fetch task details:', error);
    throw new Error('Failed to fetch task details');
  }
}

export async function getExperimentWithTaskStatuses(experimentName: string): Promise<{
  experiment: Experiment | null;
  taskStatuses: TaskStatusInfo[];
}> {
  try {
    const [experimentRow, statusRows] = await Promise.all([
      getExperimentByName(experimentName),
      getTaskStatusesByExperiment(experimentName),
    ]);

    if (!experimentRow) {
      return { experiment: null, taskStatuses: [] };
    }

    return {
      experiment: transformDbExperiment(experimentRow),
      taskStatuses: statusRows.map((row: TaskStatusRow) => ({
        name: row.name,
        type: row.type,
        status: row.status as TaskStatus,
      })),
    };
  } catch (error) {
    console.error('Failed to fetch experiment with task statuses:', error);
    throw new Error('Failed to fetch experiment with task statuses');
  }
}
