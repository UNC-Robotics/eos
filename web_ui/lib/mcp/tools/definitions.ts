import { z } from 'zod/v3';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import {
  getTaskSpecs,
  getDeviceSpecs,
  getLabSpecs,
  getExperimentSpecs,
  getLoadedStatus,
  getDefsMetadata,
} from '@/lib/api/specs';
import { textResult } from '../helpers/format';

export function registerDefinitionTools(server: McpServer) {
  server.registerTool(
    'list_task_defs',
    {
      title: 'List Task Definitions',
      description: 'Get all task type definitions with their I/O schemas.',
      inputSchema: {},
    },
    async () => {
      const specs = await getTaskSpecs();
      const entries = Object.entries(specs);
      if (entries.length === 0) return textResult('No task definitions found.');

      const lines = entries.map(([type, spec]) => {
        const parts = [`Task: ${type}`];
        if (spec.desc) parts.push(`  Description: ${spec.desc}`);
        if (spec.devices) parts.push(`  Devices: ${Object.keys(spec.devices).join(', ')}`);
        if (spec.input_parameters) parts.push(`  Input Parameters: ${JSON.stringify(spec.input_parameters)}`);
        if (spec.output_parameters) parts.push(`  Output Parameters: ${JSON.stringify(spec.output_parameters)}`);
        if (spec.input_resources) parts.push(`  Input Resources: ${Object.keys(spec.input_resources).join(', ')}`);
        if (spec.output_resources) parts.push(`  Output Resources: ${Object.keys(spec.output_resources).join(', ')}`);
        return parts.join('\n');
      });

      return textResult(`${entries.length} task definition(s):\n\n${lines.join('\n\n')}`);
    }
  );

  server.registerTool(
    'list_device_defs',
    {
      title: 'List Device Definitions',
      description: 'Get all device type definitions.',
      inputSchema: {},
    },
    async () => {
      const specs = await getDeviceSpecs();
      const entries = Object.entries(specs);
      if (entries.length === 0) return textResult('No device definitions found.');

      const lines = entries.map(([type, spec]) => {
        const parts = [`Device: ${type}`];
        if (spec.desc) parts.push(`  Description: ${spec.desc}`);
        if (spec.init_parameters) parts.push(`  Init Parameters: ${JSON.stringify(spec.init_parameters)}`);
        return parts.join('\n');
      });

      return textResult(`${entries.length} device definition(s):\n\n${lines.join('\n\n')}`);
    }
  );

  server.registerTool(
    'list_lab_defs',
    {
      title: 'List Lab Definitions',
      description: 'Get all lab definitions with device layouts.',
      inputSchema: {
        loaded_only: z.boolean().default(false).describe('Only show currently loaded labs'),
      },
    },
    async ({ loaded_only }) => {
      const specs = await getLabSpecs(loaded_only);
      const entries = Object.entries(specs);
      if (entries.length === 0) return textResult('No lab definitions found.');

      const lines = entries.map(([name, spec]) => {
        const parts = [`Lab: ${name}`];
        if (spec.desc) parts.push(`  Description: ${spec.desc}`);
        const deviceNames = Object.keys(spec.devices);
        parts.push(`  Devices (${deviceNames.length}): ${deviceNames.join(', ')}`);
        if (spec.computers) parts.push(`  Computers: ${Object.keys(spec.computers).join(', ')}`);
        return parts.join('\n');
      });

      return textResult(`${entries.length} lab definition(s):\n\n${lines.join('\n\n')}`);
    }
  );

  server.registerTool(
    'list_experiment_defs',
    {
      title: 'List Experiment Definitions',
      description: 'Get all experiment type definitions with task workflows.',
      inputSchema: {
        loaded_only: z.boolean().default(false).describe('Only show currently loaded experiments'),
      },
    },
    async ({ loaded_only }) => {
      const specs = await getExperimentSpecs(loaded_only);
      const entries = Object.entries(specs);
      if (entries.length === 0) return textResult('No experiment definitions found.');

      const lines = entries.map(([type, spec]) => {
        const parts = [`Experiment: ${type}`];
        if (spec.desc) parts.push(`  Description: ${spec.desc}`);
        parts.push(`  Labs: ${spec.labs.join(', ')}`);
        parts.push(`  Tasks (${spec.tasks.length}):`);
        for (const task of spec.tasks) {
          const deps = task.dependencies?.length ? ` (depends on: ${task.dependencies.join(', ')})` : '';
          parts.push(`    • ${task.name} [${task.type}]${deps}`);
        }
        return parts.join('\n');
      });

      return textResult(`${entries.length} experiment definition(s):\n\n${lines.join('\n\n')}`);
    }
  );

  server.registerTool(
    'get_loaded_status',
    {
      title: 'Get Loaded Status',
      description: 'Show which entities (labs, experiments, tasks, devices) are currently loaded in EOS.',
      inputSchema: {},
    },
    async () => {
      const loaded = await getLoadedStatus();
      const lines = [
        `Labs (${loaded.labs.length}): ${loaded.labs.join(', ') || 'none'}`,
        `Experiments (${loaded.experiments.length}): ${loaded.experiments.join(', ') || 'none'}`,
        `Tasks (${loaded.tasks.length}): ${loaded.tasks.join(', ') || 'none'}`,
        `Devices (${loaded.devices.length}): ${loaded.devices.join(', ') || 'none'}`,
      ];
      return textResult(`Currently loaded entities:\n\n${lines.join('\n')}`);
    }
  );

  server.registerTool(
    'list_defs',
    {
      title: 'List Definitions',
      description:
        'Get lightweight definition metadata (name, type, package, loaded status) without full data payloads.',
      inputSchema: {
        type: z.enum(['task', 'device', 'lab', 'experiment']).optional().describe('Filter by definition type'),
      },
    },
    async ({ type }) => {
      const defs = await getDefsMetadata(type);
      if (defs.length === 0) return textResult('No definitions found.');

      const lines = defs.map(
        (d) => `• ${d.type}/${d.name} [${d.isLoaded ? 'loaded' : 'unloaded'}] pkg=${d.packageName}`
      );
      return textResult(`${defs.length} definition(s):\n\n${lines.join('\n')}`);
    }
  );
}
