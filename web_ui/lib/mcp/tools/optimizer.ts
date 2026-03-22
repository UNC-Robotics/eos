import { z } from 'zod/v3';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { orchestratorGet, orchestratorPost, orchestratorPut } from '@/lib/api/orchestrator';
import { textResult, errorResult } from '../helpers/format';

export function registerOptimizerTools(server: McpServer) {
  server.registerTool(
    'get_optimizer_defaults',
    {
      title: 'Get Optimizer Defaults',
      description:
        'Get default optimizer parameters for an experiment type, including inputs, outputs, constraints, and tuning params.',
      inputSchema: {
        experiment_type: z.string().describe('Experiment type name'),
      },
    },
    async ({ experiment_type }) => {
      try {
        const result = (await orchestratorGet(
          `/campaigns/optimizer/defaults/${encodeURIComponent(experiment_type)}/`
        )) as Record<string, unknown>;

        const lines = [`Optimizer Defaults for "${experiment_type}"`, `Type: ${result.optimizer_type ?? 'unknown'}`];

        const params = result.params as Record<string, unknown> | undefined;
        if (params) {
          lines.push('', 'Parameters:');
          for (const [k, v] of Object.entries(params)) {
            lines.push(`  ${k}: ${JSON.stringify(v)}`);
          }
        }

        const inputs = result.inputs as unknown[];
        if (inputs?.length) lines.push('', `Inputs (${inputs.length}): ${JSON.stringify(inputs, null, 2)}`);

        const outputs = result.outputs as unknown[];
        if (outputs?.length) lines.push('', `Outputs (${outputs.length}): ${JSON.stringify(outputs, null, 2)}`);

        const constraints = result.constraints as unknown[];
        if (constraints?.length)
          lines.push('', `Constraints (${constraints.length}): ${JSON.stringify(constraints, null, 2)}`);

        return textResult(lines.join('\n'));
      } catch (e) {
        return errorResult(`Failed to get optimizer defaults: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'get_optimizer_info',
    {
      title: 'Get Optimizer Info',
      description: 'Get current optimizer state, runtime params, insights, and journal for a campaign.',
      inputSchema: {
        campaign_name: z.string().describe('Campaign name'),
      },
    },
    async ({ campaign_name }) => {
      try {
        const result = (await orchestratorGet(
          `/campaigns/${encodeURIComponent(campaign_name)}/optimizer/info/`
        )) as Record<string, unknown>;

        const lines = [`Optimizer Info for campaign "${campaign_name}"`, `Type: ${result.optimizer_type ?? 'unknown'}`];

        const runtimeParams = result.runtime_params as Record<string, unknown> | undefined;
        if (runtimeParams) {
          lines.push('', 'Runtime Parameters:');
          for (const [k, v] of Object.entries(runtimeParams)) {
            lines.push(`  ${k}: ${JSON.stringify(v)}`);
          }
        }

        const insights = result.insights as string[] | undefined;
        if (insights?.length) {
          lines.push('', `Insights (${insights.length}):`);
          for (const insight of insights) {
            lines.push(`  • ${insight}`);
          }
        }

        const journal = result.journal as string[] | undefined;
        if (journal?.length) {
          lines.push('', `Journal (${journal.length} entries, showing last 10):`);
          for (const entry of journal.slice(-10)) {
            lines.push(`  • ${entry}`);
          }
        }

        return textResult(lines.join('\n'));
      } catch (e) {
        return errorResult(`Failed to get optimizer info: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'update_optimizer_params',
    {
      title: 'Update Optimizer Params',
      description:
        'Update runtime optimizer parameters for a campaign. p_ai is automatically derived as 1 - p_bayesian.',
      inputSchema: {
        campaign_name: z.string().describe('Campaign name'),
        p_bayesian: z
          .number()
          .min(0)
          .max(1)
          .optional()
          .describe('Probability of using Bayesian optimization (0-1). p_ai is derived as 1 - p_bayesian.'),
        ai_history_size: z
          .number()
          .int()
          .min(1)
          .optional()
          .describe('Number of historical samples to include in AI context'),
        ai_additional_context: z.string().optional().describe('Additional context/instructions for the AI optimizer'),
      },
    },
    async ({ campaign_name, p_bayesian, ai_history_size, ai_additional_context }) => {
      try {
        const params: Record<string, unknown> = {};
        if (p_bayesian !== undefined) params.p_bayesian = p_bayesian;
        if (ai_history_size !== undefined) params.ai_history_size = ai_history_size;
        if (ai_additional_context !== undefined) params.ai_additional_context = ai_additional_context;

        if (Object.keys(params).length === 0) {
          return errorResult('No parameters provided to update.');
        }

        const result = await orchestratorPut(
          `/campaigns/${encodeURIComponent(campaign_name)}/optimizer/params/`,
          params
        );
        const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
        return textResult(`Optimizer params updated for "${campaign_name}".\n${text}`);
      } catch (e) {
        return errorResult(`Failed to update optimizer params: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'add_optimizer_insight',
    {
      title: 'Add Optimizer Insight',
      description:
        'Add an expert insight to the optimizer for a campaign. Insights guide the AI in future experiment suggestions.',
      inputSchema: {
        campaign_name: z.string().describe('Campaign name'),
        insight: z.string().describe('Expert insight text to add'),
      },
    },
    async ({ campaign_name, insight }) => {
      try {
        const result = await orchestratorPost(`/campaigns/${encodeURIComponent(campaign_name)}/optimizer/insight/`, {
          insight,
        });
        const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
        return textResult(`Insight added to campaign "${campaign_name}".\n${text}`);
      } catch (e) {
        return errorResult(`Failed to add insight: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );
}
