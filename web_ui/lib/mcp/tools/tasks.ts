import { z } from 'zod/v3';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { getAllTasks, getTaskByName, getTasksByExperiment } from '@/lib/db/queries';
import { orchestratorPost } from '@/lib/api/orchestrator';
import { formatDate, formatDuration, formatPagination, textResult, errorResult } from '../helpers/format';

export function registerTaskTools(server: McpServer) {
  server.registerTool(
    'list_tasks',
    {
      title: 'List Tasks',
      description: 'List recent tasks with pagination. Returns name, type, status, experiment, and timing info.',
      inputSchema: {
        limit: z.number().int().min(1).max(200).default(20).describe('Max rows to return'),
        offset: z.number().int().min(0).default(0).describe('Number of rows to skip'),
      },
    },
    async ({ limit, offset }) => {
      const result = await getAllTasks({ limit, offset });
      const lines = result.data.map((t) => {
        const dur = formatDuration(t.startTime, t.endTime);
        return `• ${t.name} [${t.status}] type=${t.type} exp=${t.experimentName ?? 'standalone'} dur=${dur}`;
      });
      const header = formatPagination(result.total, result.limit, result.offset);
      return textResult(`${header}\n\n${lines.join('\n')}`);
    }
  );

  server.registerTool(
    'get_task',
    {
      title: 'Get Task',
      description: 'Get full details for a specific task including inputs, outputs, devices, and timing.',
      inputSchema: {
        task_name: z.string().describe('Task name'),
        experiment_name: z.string().describe('Experiment name the task belongs to'),
      },
    },
    async ({ task_name, experiment_name }) => {
      const task = await getTaskByName(task_name, experiment_name);
      if (!task) return errorResult(`Task "${task_name}" not found in experiment "${experiment_name}"`);

      const lines = [
        `Task: ${task.name}`,
        `Type: ${task.type}`,
        `Status: ${task.status}`,
        `Priority: ${task.priority}`,
        `Experiment: ${task.experimentName ?? 'standalone'}`,
        `Created: ${formatDate(task.createdAt)}`,
        `Started: ${formatDate(task.startTime)}`,
        `Ended: ${formatDate(task.endTime)}`,
        `Duration: ${formatDuration(task.startTime, task.endTime)}`,
        `Devices: ${JSON.stringify(task.devices)}`,
      ];
      if (task.inputParameters) lines.push(`Input Parameters: ${JSON.stringify(task.inputParameters, null, 2)}`);
      if (task.outputParameters) lines.push(`Output Parameters: ${JSON.stringify(task.outputParameters, null, 2)}`);
      if (task.inputResources) lines.push(`Input Resources: ${JSON.stringify(task.inputResources)}`);
      if (task.outputResources) lines.push(`Output Resources: ${JSON.stringify(task.outputResources)}`);
      if (task.outputFileNames?.length) lines.push(`Output Files: ${task.outputFileNames.join(', ')}`);

      return textResult(lines.join('\n'));
    }
  );

  server.registerTool(
    'get_tasks_by_experiment',
    {
      title: 'Get Tasks by Experiment',
      description: 'Get all tasks belonging to a specific experiment.',
      inputSchema: {
        experiment_name: z.string().describe('Experiment name'),
      },
    },
    async ({ experiment_name }) => {
      const tasks = await getTasksByExperiment(experiment_name);
      if (tasks.length === 0) return textResult(`No tasks found for experiment "${experiment_name}"`);

      const lines = tasks.map((t) => {
        const dur = formatDuration(t.startTime, t.endTime);
        return `• ${t.name} [${t.status}] type=${t.type} dur=${dur}`;
      });
      return textResult(`${tasks.length} task(s) in experiment "${experiment_name}":\n\n${lines.join('\n')}`);
    }
  );

  server.registerTool(
    'submit_task',
    {
      title: 'Submit Task',
      description: 'Submit a new task to the orchestrator for execution.',
      inputSchema: {
        name: z.string().describe('Unique task name'),
        type: z.string().describe('Task type (e.g. "Noop", "GoToAbsolutePosition")'),
        devices: z
          .record(
            z.object({
              lab: z.string(),
              type: z.string(),
            })
          )
          .describe('Device assignments: { device_role: { lab, type } }'),
        parameters: z.record(z.unknown()).optional().describe('Task input parameters'),
        experiment_name: z.string().optional().describe('Parent experiment name'),
      },
    },
    async ({ name, type, devices, parameters, experiment_name }) => {
      try {
        const body: Record<string, unknown> = { name, type, devices };
        if (parameters) body.input_parameters = parameters;
        if (experiment_name) body.experiment_name = experiment_name;
        const result = await orchestratorPost('/tasks/', body);
        return textResult(`Task submitted successfully.\n${JSON.stringify(result, null, 2)}`);
      } catch (e) {
        return errorResult(`Failed to submit task: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'cancel_task',
    {
      title: 'Cancel Task',
      description: 'Cancel a running task.',
      inputSchema: {
        task_name: z.string().describe('Name of the task to cancel'),
      },
    },
    async ({ task_name }) => {
      try {
        await orchestratorPost(`/tasks/${encodeURIComponent(task_name)}/cancel`);
        return textResult(`Task "${task_name}" cancelled.`);
      } catch (e) {
        return errorResult(`Failed to cancel task: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );
}
