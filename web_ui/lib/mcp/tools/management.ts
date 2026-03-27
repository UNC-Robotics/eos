import { z } from 'zod/v3';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { orchestratorPost, orchestratorGet } from '@/lib/api/orchestrator';
import { textResult, errorResult } from '../helpers/format';

function orchestratorAction(
  server: McpServer,
  name: string,
  title: string,
  description: string,
  method: 'GET' | 'POST',
  endpoint: string | ((args: Record<string, unknown>) => string),
  inputSchema?: Record<string, z.ZodTypeAny>
) {
  server.registerTool(
    name,
    {
      title,
      description,
      inputSchema: inputSchema ?? {},
    },
    async (args: Record<string, unknown>) => {
      try {
        const url = typeof endpoint === 'function' ? endpoint(args) : endpoint;
        const result =
          method === 'GET' ? await orchestratorGet(url) : await orchestratorPost(url, inputSchema ? args : undefined);
        const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
        return textResult(`${title}: Success\n${text}`);
      } catch (e) {
        return errorResult(`${title} failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );
}

export function registerManagementTools(server: McpServer) {
  orchestratorAction(
    server,
    'load_labs',
    'Load Labs',
    'Load lab configurations into the orchestrator.',
    'POST',
    '/labs/load/',
    { lab_types: z.array(z.string()).describe('List of lab types to load') }
  );
  orchestratorAction(
    server,
    'unload_labs',
    'Unload Labs',
    'Unload lab configurations from the orchestrator.',
    'POST',
    '/labs/unload/',
    { lab_types: z.array(z.string()).describe('List of lab types to unload') }
  );
  orchestratorAction(
    server,
    'reload_labs',
    'Reload Labs',
    'Reload lab configurations in the orchestrator.',
    'POST',
    '/labs/reload/',
    { lab_types: z.array(z.string()).describe('List of lab types to reload') }
  );

  orchestratorAction(
    server,
    'load_protocols',
    'Load Protocols',
    'Load protocol configurations into the orchestrator.',
    'POST',
    '/protocols/load/',
    { protocol_types: z.array(z.string()).describe('List of protocol types to load') }
  );
  orchestratorAction(
    server,
    'unload_protocols',
    'Unload Protocols',
    'Unload protocol configurations from the orchestrator.',
    'POST',
    '/protocols/unload/',
    { protocol_types: z.array(z.string()).describe('List of protocol types to unload') }
  );
  orchestratorAction(
    server,
    'reload_protocols',
    'Reload Protocols',
    'Reload protocol configurations in the orchestrator.',
    'POST',
    '/protocols/reload/',
    { protocol_types: z.array(z.string()).describe('List of protocol types to reload') }
  );

  orchestratorAction(
    server,
    'reload_task_plugins',
    'Reload Task Plugins',
    'Reload task plugin definitions.',
    'POST',
    '/tasks/reload/',
    { task_types: z.array(z.string()).describe('List of task types to reload') }
  );

  server.registerTool(
    'reload_devices',
    {
      title: 'Reload Devices',
      description: 'Reload devices for a specific lab.',
      inputSchema: {
        lab_name: z.string().describe('Name of the lab whose devices to reload'),
        device_names: z.array(z.string()).describe('List of device names to reload'),
      },
    },
    async ({ lab_name, device_names }) => {
      try {
        const result = await orchestratorPost(`/labs/${encodeURIComponent(lab_name as string)}/devices/reload/`, {
          device_names,
        });
        const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
        return textResult(`Reload Devices: Success\n${text}`);
      } catch (e) {
        return errorResult(`Reload devices failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  orchestratorAction(
    server,
    'refresh_packages',
    'Refresh Packages',
    'Re-discover EOS packages and update definitions.',
    'POST',
    '/refresh/packages/'
  );

  orchestratorAction(
    server,
    'health_check',
    'Health Check',
    'Check the orchestrator health status.',
    'GET',
    '/health/'
  );
}
