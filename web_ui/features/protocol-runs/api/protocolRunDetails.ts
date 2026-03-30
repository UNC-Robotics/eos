'use server';

import {
  getProtocolRunByName,
  getTasksByProtocolRun,
  getTaskStatusesByProtocolRun,
  getTaskByName,
  ProtocolRunRow,
  TaskRow,
  TaskStatusRow,
} from '@/lib/db/queries';
import type { ProtocolRun, Task, TaskStatus, TaskDeviceConfig } from '@/lib/types/api';

export interface TaskStatusInfo {
  name: string;
  type: string;
  status: TaskStatus;
}

function transformDbProtocolRun(exp: ProtocolRunRow): ProtocolRun {
  return {
    name: exp.name,
    type: exp.type,
    owner: exp.owner,
    priority: exp.priority,
    parameters: exp.parameters || {},
    meta: exp.meta ?? null,
    resume: exp.resume,
    status: exp.status as ProtocolRun['status'],
    error_message: exp.errorMessage ?? null,
    created_at: exp.createdAt.toISOString(),
    start_time: exp.startTime?.toISOString() ?? null,
    end_time: exp.endTime?.toISOString() ?? null,
  };
}

function transformDbTask(task: TaskRow): Task {
  return {
    name: task.name,
    protocol_run_name: task.protocolRunName,
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

export async function getProtocolRunDetails(protocolRunName: string): Promise<{
  protocolRun: ProtocolRun | null;
  tasks: Task[];
}> {
  try {
    const [protocolRunRow, taskRows] = await Promise.all([
      getProtocolRunByName(protocolRunName),
      getTasksByProtocolRun(protocolRunName),
    ]);

    if (!protocolRunRow) {
      return { protocolRun: null, tasks: [] };
    }

    return {
      protocolRun: transformDbProtocolRun(protocolRunRow),
      tasks: taskRows.map(transformDbTask),
    };
  } catch (error) {
    console.error('Failed to fetch protocol run details:', error);
    throw new Error('Failed to fetch protocol run details');
  }
}

export async function getProtocolRunTasks(protocolRunName: string): Promise<Task[]> {
  try {
    const taskRows = await getTasksByProtocolRun(protocolRunName);
    return taskRows.map(transformDbTask);
  } catch (error) {
    console.error('Failed to fetch protocol run tasks:', error);
    throw new Error('Failed to fetch protocol run tasks');
  }
}

export async function getTaskStatuses(protocolRunName: string): Promise<TaskStatusInfo[]> {
  try {
    const statusRows = await getTaskStatusesByProtocolRun(protocolRunName);
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

export async function getTaskDetails(taskName: string, protocolRunName: string): Promise<Task | null> {
  try {
    const taskRow = await getTaskByName(taskName, protocolRunName);
    if (!taskRow) return null;
    return transformDbTask(taskRow);
  } catch (error) {
    console.error('Failed to fetch task details:', error);
    throw new Error('Failed to fetch task details');
  }
}

export async function getProtocolRunWithTaskStatuses(protocolRunName: string): Promise<{
  protocolRun: ProtocolRun | null;
  taskStatuses: TaskStatusInfo[];
}> {
  try {
    const [protocolRunRow, statusRows] = await Promise.all([
      getProtocolRunByName(protocolRunName),
      getTaskStatusesByProtocolRun(protocolRunName),
    ]);

    if (!protocolRunRow) {
      return { protocolRun: null, taskStatuses: [] };
    }

    return {
      protocolRun: transformDbProtocolRun(protocolRunRow),
      taskStatuses: statusRows.map((row: TaskStatusRow) => ({
        name: row.name,
        type: row.type,
        status: row.status as TaskStatus,
      })),
    };
  } catch (error) {
    console.error('Failed to fetch protocol run with task statuses:', error);
    throw new Error('Failed to fetch protocol run with task statuses');
  }
}
