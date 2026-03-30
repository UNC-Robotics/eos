import { z } from 'zod/v3';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { getAllCampaigns, getCampaignByName, getCampaignSamples, getProtocolRunsByCampaign } from '@/lib/db/queries';
import { orchestratorPost } from '@/lib/api/orchestrator';
import { formatDate, formatDuration, formatPagination, textResult, errorResult } from '../helpers/format';

export function registerCampaignTools(server: McpServer) {
  server.registerTool(
    'list_campaigns',
    {
      title: 'List Campaigns',
      description: 'List recent campaigns with pagination.',
      inputSchema: {
        limit: z.number().int().min(1).max(200).default(20).describe('Max rows to return'),
        offset: z.number().int().min(0).default(0).describe('Number of rows to skip'),
      },
    },
    async ({ limit, offset }) => {
      const result = await getAllCampaigns({ limit, offset });
      const lines = result.data.map((c) => {
        const dur = formatDuration(c.startTime, c.endTime);
        return `• ${c.name} [${c.status}] type=${c.protocol} owner=${c.owner} completed=${c.protocolRunsCompleted}/${c.maxProtocolRuns} optimize=${c.optimize} dur=${dur}`;
      });
      return textResult(`${formatPagination(result.total, result.limit, result.offset)}\n\n${lines.join('\n')}`);
    }
  );

  server.registerTool(
    'get_campaign',
    {
      title: 'Get Campaign',
      description:
        'Get campaign configuration and metadata (status, parameters, timestamps). Does not include protocols or samples.',
      inputSchema: {
        name: z.string().describe('Campaign name'),
      },
    },
    async ({ name }) => {
      const c = await getCampaignByName(name);
      if (!c) return errorResult(`Campaign "${name}" not found`);

      const lines = [
        `Campaign: ${c.name}`,
        `Protocol: ${c.protocol}`,
        `Status: ${c.status}`,
        `Owner: ${c.owner}`,
        `Priority: ${c.priority}`,
        `Progress: ${c.protocolRunsCompleted}/${c.maxProtocolRuns} protocol_runs`,
        `Max Concurrent: ${c.maxConcurrentProtocolRuns}`,
        `Optimize: ${c.optimize}`,
        `Resume: ${c.resume}`,
        `Created: ${formatDate(c.createdAt)}`,
        `Started: ${formatDate(c.startTime)}`,
        `Ended: ${formatDate(c.endTime)}`,
        `Duration: ${formatDuration(c.startTime, c.endTime)}`,
      ];
      if (c.globalParameters) lines.push(`Global Parameters: ${JSON.stringify(c.globalParameters, null, 2)}`);
      if (c.meta) lines.push(`Meta: ${JSON.stringify(c.meta, null, 2)}`);
      if (c.paretoSolutions?.length) lines.push(`Pareto Solutions: ${JSON.stringify(c.paretoSolutions, null, 2)}`);

      return textResult(lines.join('\n'));
    }
  );

  server.registerTool(
    'get_campaign_details',
    {
      title: 'Get Campaign Details',
      description: 'Get campaign summary with the list of its protocols and optimization samples.',
      inputSchema: {
        name: z.string().describe('Campaign name'),
      },
    },
    async ({ name }) => {
      const [campaign, exps, samples] = await Promise.all([
        getCampaignByName(name),
        getProtocolRunsByCampaign(name),
        getCampaignSamples(name),
      ]);
      if (!campaign) return errorResult(`Campaign "${name}" not found`);

      const lines = [
        `Campaign: ${campaign.name}`,
        `Type: ${campaign.protocol}`,
        `Status: ${campaign.status}`,
        `Owner: ${campaign.owner}`,
        `Progress: ${campaign.protocolRunsCompleted}/${campaign.maxProtocolRuns}`,
        `Optimize: ${campaign.optimize}`,
        `Duration: ${formatDuration(campaign.startTime, campaign.endTime)}`,
        '',
        `--- Protocol Runs (${exps.length}) ---`,
      ];

      for (const e of exps) {
        lines.push(`• ${e.name} [${e.status}] dur=${formatDuration(e.startTime, e.endTime)}`);
      }

      if (samples.length > 0) {
        lines.push('', `--- Samples (${samples.length}) ---`);
        for (const s of samples) {
          lines.push(`• ${s.protocolRunName}: inputs=${JSON.stringify(s.inputs)} outputs=${JSON.stringify(s.outputs)}`);
        }
      }

      return textResult(lines.join('\n'));
    }
  );

  server.registerTool(
    'get_campaign_samples',
    {
      title: 'Get Campaign Samples',
      description: 'Get optimization sample data for a campaign.',
      inputSchema: {
        campaign_name: z.string().describe('Campaign name'),
      },
    },
    async ({ campaign_name }) => {
      const samples = await getCampaignSamples(campaign_name);
      if (samples.length === 0) return textResult(`No samples found for campaign "${campaign_name}"`);

      const lines = samples.map(
        (s, i) =>
          `${i + 1}. ${s.protocolRunName}: inputs=${JSON.stringify(s.inputs)} outputs=${JSON.stringify(s.outputs)}`
      );
      return textResult(`${samples.length} sample(s) for campaign "${campaign_name}":\n\n${lines.join('\n')}`);
    }
  );

  server.registerTool(
    'submit_campaign',
    {
      title: 'Submit Campaign',
      description: 'Submit a new campaign to the orchestrator.',
      inputSchema: {
        name: z.string().describe('Unique campaign name'),
        protocol: z.string().describe('ProtocolRun type to run'),
        owner: z.string().describe('Owner name'),
        max_protocol_runs: z.number().int().min(1).describe('Maximum number of protocols'),
        optimize: z.boolean().describe('Whether to use Bayesian optimization'),
        max_concurrent_protocol_runs: z.number().int().min(1).optional().describe('Max concurrent protocols'),
        priority: z.number().int().optional().describe('Priority (default 0)'),
        global_parameters: z
          .record(z.record(z.unknown()))
          .optional()
          .describe('Parameters shared across all protocols'),
        protocol_run_parameters: z
          .array(z.record(z.record(z.unknown())))
          .optional()
          .describe('Per-protocol-run parameter overrides'),
        meta: z.record(z.unknown()).optional().describe('Metadata (e.g. optimizer_overrides)'),
        resume: z.boolean().optional().describe('Whether to resume from previous state'),
      },
    },
    async ({
      name,
      protocol,
      owner,
      max_protocol_runs,
      optimize,
      max_concurrent_protocol_runs,
      priority,
      global_parameters,
      protocol_run_parameters,
      meta,
      resume,
    }) => {
      try {
        const body: Record<string, unknown> = { name, protocol, owner, max_protocol_runs, optimize };
        if (max_concurrent_protocol_runs !== undefined)
          body.max_concurrent_protocol_runs = max_concurrent_protocol_runs;
        if (priority !== undefined) body.priority = priority;
        if (global_parameters) body.global_parameters = global_parameters;
        if (protocol_run_parameters) body.protocol_run_parameters = protocol_run_parameters;
        if (meta) body.meta = meta;
        if (resume !== undefined) body.resume = resume;
        const result = await orchestratorPost('/campaigns/', body);
        return textResult(`Campaign submitted successfully.\n${JSON.stringify(result, null, 2)}`);
      } catch (e) {
        return errorResult(`Failed to submit campaign: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'cancel_campaign',
    {
      title: 'Cancel Campaign',
      description: 'Cancel a running campaign.',
      inputSchema: {
        name: z.string().describe('Campaign name to cancel'),
      },
    },
    async ({ name }) => {
      try {
        await orchestratorPost(`/campaigns/${encodeURIComponent(name)}/cancel`);
        return textResult(`Campaign "${name}" cancelled.`);
      } catch (e) {
        return errorResult(`Failed to cancel campaign: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );
}
