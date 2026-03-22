import { z } from 'zod/v3';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { db } from '@/lib/db/client';
import { devices } from '@/lib/db/schema';
import { orchestratorGet, orchestratorPost } from '@/lib/api/orchestrator';
import { textResult, errorResult } from '../helpers/format';

export function registerDeviceTools(server: McpServer) {
  server.registerTool(
    'list_devices',
    {
      title: 'List Devices',
      description: 'List all devices with their lab, type, computer, and status.',
      inputSchema: {},
    },
    async () => {
      const rows = await db.select().from(devices);
      if (rows.length === 0) return textResult('No devices found.');

      const lines = rows.map((d) => `• ${d.labName}/${d.name} [${d.status}] type=${d.type} computer=${d.computer}`);
      return textResult(`${rows.length} device(s):\n\n${lines.join('\n')}`);
    }
  );

  server.registerTool(
    'get_device_report',
    {
      title: 'Get Device Report',
      description: 'Get the full state/report for a device.',
      inputSchema: {
        lab_name: z.string().describe('Lab name'),
        device_name: z.string().describe('Device name'),
      },
    },
    async ({ lab_name, device_name }) => {
      try {
        const result = await orchestratorGet(
          `/labs/${encodeURIComponent(lab_name)}/device/${encodeURIComponent(device_name)}/report`
        );
        const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
        return textResult(`Device report for ${lab_name}/${device_name}:\n\n${text}`);
      } catch (e) {
        return errorResult(`Failed to get device report: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'get_device_status',
    {
      title: 'Get Device Status',
      description: 'Get the current status of a device.',
      inputSchema: {
        lab_name: z.string().describe('Lab name'),
        device_name: z.string().describe('Device name'),
      },
    },
    async ({ lab_name, device_name }) => {
      try {
        const result = (await orchestratorPost(
          `/rpc/${encodeURIComponent(lab_name)}/${encodeURIComponent(device_name)}/get_status`,
          {}
        )) as { name: string; lab_name: string; status: { _name_: string; _value_: string } | string };

        const status =
          typeof result.status === 'object' && '_value_' in result.status
            ? result.status._value_
            : String(result.status);

        return textResult(`Device: ${result.name}\nLab: ${result.lab_name}\nStatus: ${status}`);
      } catch (e) {
        return errorResult(`Failed to get device status: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'get_device_introspection',
    {
      title: 'Get Device Introspection',
      description:
        'Get available functions and their signatures for a device. Use this to discover what RPC calls a device supports before calling them.',
      inputSchema: {
        lab_name: z.string().describe('Lab name'),
        device_name: z.string().describe('Device name'),
      },
    },
    async ({ lab_name, device_name }) => {
      try {
        const result = await orchestratorPost(
          `/rpc/${encodeURIComponent(lab_name)}/${encodeURIComponent(device_name)}/get_available_functions`,
          {}
        );
        const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
        return textResult(`Available functions for ${lab_name}/${device_name}:\n\n${text}`);
      } catch (e) {
        return errorResult(`Failed to get device introspection: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'call_device_function',
    {
      title: 'Call Device Function',
      description:
        'Call an RPC function on a device. Use get_device_introspection first to discover available functions and their parameters.',
      inputSchema: {
        lab_name: z.string().describe('Lab name'),
        device_name: z.string().describe('Device name'),
        function_name: z.string().describe('Function name to call'),
        parameters: z.record(z.unknown()).default({}).describe('Function parameters as key-value pairs'),
      },
    },
    async ({ lab_name, device_name, function_name, parameters }) => {
      try {
        const result = await orchestratorPost(
          `/rpc/${encodeURIComponent(lab_name)}/${encodeURIComponent(device_name)}/${encodeURIComponent(function_name)}`,
          parameters
        );
        const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
        return textResult(`Function "${function_name}" on ${lab_name}/${device_name}:\n\n${text}`);
      } catch (e) {
        return errorResult(`RPC call failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'load_devices',
    {
      title: 'Load Devices',
      description: 'Load specific devices in a lab.',
      inputSchema: {
        lab_name: z.string().describe('Lab name'),
        device_names: z.array(z.string()).describe('Device names to load'),
      },
    },
    async ({ lab_name, device_names }) => {
      try {
        const result = await orchestratorPost(`/labs/${encodeURIComponent(lab_name)}/devices/load/`, { device_names });
        const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
        return textResult(`Load devices in ${lab_name}: Success\n${text}`);
      } catch (e) {
        return errorResult(`Failed to load devices: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'unload_devices',
    {
      title: 'Unload Devices',
      description: 'Unload specific devices in a lab.',
      inputSchema: {
        lab_name: z.string().describe('Lab name'),
        device_names: z.array(z.string()).describe('Device names to unload'),
      },
    },
    async ({ lab_name, device_names }) => {
      try {
        const result = await orchestratorPost(`/labs/${encodeURIComponent(lab_name)}/devices/unload/`, {
          device_names,
        });
        const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
        return textResult(`Unload devices in ${lab_name}: Success\n${text}`);
      } catch (e) {
        return errorResult(`Failed to unload devices: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );
}
