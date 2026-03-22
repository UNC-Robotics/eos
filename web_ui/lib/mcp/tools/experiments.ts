import { z } from 'zod/v3';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import {
  getAllExperiments,
  getExperimentByName,
  getExperimentsByCampaign,
  getExperimentsByOwner,
  getTasksByExperiment,
} from '@/lib/db/queries';
import { orchestratorPost } from '@/lib/api/orchestrator';
import { formatDate, formatDuration, formatPagination, textResult, errorResult } from '../helpers/format';

export function registerExperimentTools(server: McpServer) {
  server.registerTool(
    'list_experiments',
    {
      title: 'List Experiments',
      description: 'List recent experiments with pagination.',
      inputSchema: {
        limit: z.number().int().min(1).max(200).default(20).describe('Max rows to return'),
        offset: z.number().int().min(0).default(0).describe('Number of rows to skip'),
      },
    },
    async ({ limit, offset }) => {
      const result = await getAllExperiments({ limit, offset });
      const lines = result.data.map((e) => {
        const dur = formatDuration(e.startTime, e.endTime);
        return `• ${e.name} [${e.status}] type=${e.type} owner=${e.owner} campaign=${e.campaign ?? 'none'} dur=${dur}`;
      });
      return textResult(`${formatPagination(result.total, result.limit, result.offset)}\n\n${lines.join('\n')}`);
    }
  );

  server.registerTool(
    'get_experiment',
    {
      title: 'Get Experiment',
      description: 'Get full details for a specific experiment.',
      inputSchema: {
        name: z.string().describe('Experiment name'),
      },
    },
    async ({ name }) => {
      const exp = await getExperimentByName(name);
      if (!exp) return errorResult(`Experiment "${name}" not found`);

      const lines = [
        `Experiment: ${exp.name}`,
        `Type: ${exp.type}`,
        `Status: ${exp.status}`,
        `Owner: ${exp.owner}`,
        `Priority: ${exp.priority}`,
        `Campaign: ${exp.campaign ?? 'none'}`,
        `Resume: ${exp.resume}`,
        `Created: ${formatDate(exp.createdAt)}`,
        `Started: ${formatDate(exp.startTime)}`,
        `Ended: ${formatDate(exp.endTime)}`,
        `Duration: ${formatDuration(exp.startTime, exp.endTime)}`,
        `Parameters: ${JSON.stringify(exp.parameters, null, 2)}`,
      ];
      if (exp.meta) lines.push(`Meta: ${JSON.stringify(exp.meta, null, 2)}`);

      return textResult(lines.join('\n'));
    }
  );

  server.registerTool(
    'get_experiment_details',
    {
      title: 'Get Experiment Details',
      description: 'Get experiment details along with all its tasks.',
      inputSchema: {
        name: z.string().describe('Experiment name'),
      },
    },
    async ({ name }) => {
      const [exp, tasks] = await Promise.all([getExperimentByName(name), getTasksByExperiment(name)]);
      if (!exp) return errorResult(`Experiment "${name}" not found`);

      const expLines = [
        `Experiment: ${exp.name}`,
        `Type: ${exp.type}`,
        `Status: ${exp.status}`,
        `Owner: ${exp.owner}`,
        `Campaign: ${exp.campaign ?? 'none'}`,
        `Duration: ${formatDuration(exp.startTime, exp.endTime)}`,
        `Parameters: ${JSON.stringify(exp.parameters, null, 2)}`,
        '',
        `--- Tasks (${tasks.length}) ---`,
      ];

      for (const t of tasks) {
        const dur = formatDuration(t.startTime, t.endTime);
        expLines.push(`• ${t.name} [${t.status}] type=${t.type} dur=${dur}`);
        if (t.outputParameters) {
          expLines.push(`  outputs: ${JSON.stringify(t.outputParameters)}`);
        }
      }

      return textResult(expLines.join('\n'));
    }
  );

  server.registerTool(
    'get_experiments_by_campaign',
    {
      title: 'Get Experiments by Campaign',
      description: 'Get all experiments belonging to a specific campaign.',
      inputSchema: {
        campaign_name: z.string().describe('Campaign name'),
      },
    },
    async ({ campaign_name }) => {
      const exps = await getExperimentsByCampaign(campaign_name);
      if (exps.length === 0) return textResult(`No experiments found for campaign "${campaign_name}"`);

      const lines = exps.map((e) => {
        const dur = formatDuration(e.startTime, e.endTime);
        return `• ${e.name} [${e.status}] type=${e.type} dur=${dur}`;
      });
      return textResult(`${exps.length} experiment(s) in campaign "${campaign_name}":\n\n${lines.join('\n')}`);
    }
  );

  server.registerTool(
    'get_experiments_by_owner',
    {
      title: 'Get Experiments by Owner',
      description: 'Get all experiments belonging to a specific owner.',
      inputSchema: {
        owner: z.string().describe('Owner name'),
      },
    },
    async ({ owner }) => {
      const exps = await getExperimentsByOwner(owner);
      if (exps.length === 0) return textResult(`No experiments found for owner "${owner}"`);

      const lines = exps.map((e) => {
        const dur = formatDuration(e.startTime, e.endTime);
        return `• ${e.name} [${e.status}] type=${e.type} campaign=${e.campaign ?? 'none'} dur=${dur}`;
      });
      return textResult(`${exps.length} experiment(s) by "${owner}":\n\n${lines.join('\n')}`);
    }
  );

  server.registerTool(
    'submit_experiment',
    {
      title: 'Submit Experiment',
      description: 'Submit a new experiment to the orchestrator.',
      inputSchema: {
        name: z.string().describe('Unique experiment name'),
        type: z.string().describe('Experiment type'),
        owner: z.string().describe('Owner name'),
        parameters: z
          .record(z.record(z.unknown()))
          .optional()
          .describe('Task parameters: { task_name: { param: value } }'),
        priority: z.number().int().optional().describe('Priority (default 0)'),
        resume: z.boolean().optional().describe('Whether to resume from previous state'),
        meta: z.record(z.unknown()).optional().describe('Metadata'),
      },
    },
    async ({ name, type, owner, parameters, priority, resume, meta }) => {
      try {
        const body: Record<string, unknown> = { name, type, owner };
        if (parameters) body.parameters = parameters;
        if (priority !== undefined) body.priority = priority;
        if (resume !== undefined) body.resume = resume;
        if (meta) body.meta = meta;
        const result = await orchestratorPost('/experiments/', body);
        return textResult(`Experiment submitted successfully.\n${JSON.stringify(result, null, 2)}`);
      } catch (e) {
        return errorResult(`Failed to submit experiment: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'cancel_experiment',
    {
      title: 'Cancel Experiment',
      description: 'Cancel a running experiment.',
      inputSchema: {
        name: z.string().describe('Experiment name to cancel'),
      },
    },
    async ({ name }) => {
      try {
        await orchestratorPost(`/experiments/${encodeURIComponent(name)}/cancel`);
        return textResult(`Experiment "${name}" cancelled.`);
      } catch (e) {
        return errorResult(`Failed to cancel experiment: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'validate_experiment_yaml',
    {
      title: 'Validate Experiment YAML',
      description:
        'Validate experiment YAML against lab and task specs (devices, resources, parameters, dependencies). Always call before applying YAML with updateExperimentYAML.',
      inputSchema: {
        yaml: z.string().describe('Complete experiment YAML content'),
      },
    },
    async ({ yaml: yamlString }) => {
      try {
        const result = (await orchestratorPost('/experiments/validate', {
          experiment_yaml: yamlString,
        })) as Record<string, unknown>;
        if (result.valid) {
          return textResult('Validation passed — all parameters, devices, resources, and dependencies check out.');
        }
        const errors = (result.errors as Array<{ task: string | null; message: string }>) || [];
        return errorResult(`Validation failed:\n${errors.map((e) => `- ${e.message}`).join('\n')}`);
      } catch (e) {
        return errorResult(`Validation request failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );
}
