import { z } from 'zod/v3';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { textResult, errorResult } from '../helpers/format';
import { ENTITY_FILE_NAMES, type EntityType } from '@/lib/types/filesystem';
import { scanPackages, getPackageTree, readEntityFiles } from '@/lib/filesystem/operations';

export function registerFilesystemTools(server: McpServer) {
  server.registerTool(
    'list_packages',
    {
      title: 'List Packages',
      description: 'List all EOS packages in the user directory with their available entity types.',
      inputSchema: {},
    },
    async () => {
      try {
        const packages = await scanPackages();
        if (packages.length === 0) return textResult('No packages found in user directory.');

        const lines = packages.map((p) => {
          const types = [
            p.hasDevices && 'devices',
            p.hasTasks && 'tasks',
            p.hasLabs && 'labs',
            p.hasExperiments && 'experiments',
          ]
            .filter(Boolean)
            .join(', ');
          return `• ${p.name} (${types})`;
        });

        return textResult(`${packages.length} package(s):\n\n${lines.join('\n')}`);
      } catch (e) {
        return errorResult(`Failed to list packages: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'list_package_entities',
    {
      title: 'List Package Entities',
      description: 'List all entities (devices, tasks, labs, experiments) in a package.',
      inputSchema: {
        package_name: z.string().describe('Package name (e.g. "eos_examples/color_lab")'),
        entity_type: z.enum(['devices', 'tasks', 'labs', 'experiments']).optional().describe('Filter by entity type'),
      },
    },
    async ({ package_name, entity_type }) => {
      try {
        const tree = await getPackageTree(package_name);
        const types = entity_type ? [entity_type] : (['devices', 'tasks', 'labs', 'experiments'] as const);

        const sections = types.map((type) => {
          const entities = tree[type];
          if (entities.length === 0) return `${type}: (none)`;
          return `${type}:\n${entities.map((e) => `  • ${e.name} (yaml: ${e.hasYaml ? 'yes' : 'no'}, python: ${e.hasPython ? 'yes' : 'no'})`).join('\n')}`;
        });

        return textResult(`Package "${package_name}":\n\n${sections.join('\n\n')}`);
      } catch (e) {
        return errorResult(`Failed to list entities: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );

  server.registerTool(
    'read_entity_file',
    {
      title: 'Read Entity File',
      description:
        'Read the YAML and/or Python file for an entity (task, device, lab, or experiment). For experiments, also returns layout.json if present.',
      inputSchema: {
        package_name: z.string().describe('Package name (e.g. "eos_examples/color_lab")'),
        entity_type: z.enum(['devices', 'tasks', 'labs', 'experiments']).describe('Entity type'),
        entity_name: z.string().describe('Entity name (directory name)'),
        file: z
          .enum(['yaml', 'python', 'all'])
          .default('all')
          .describe('Which file(s) to read: "yaml", "python", or "all"'),
      },
    },
    async ({ package_name, entity_type, entity_name, file }) => {
      try {
        const files = await readEntityFiles(package_name, entity_type as EntityType, entity_name);
        if (!files) {
          return errorResult(`Entity not found: ${package_name}/${entity_type}/${entity_name}`);
        }
        const fileNames = ENTITY_FILE_NAMES[entity_type as EntityType];
        const parts: string[] = [];

        if (file === 'yaml' || file === 'all') {
          parts.push(`--- ${fileNames.yaml} ---\n${files.yaml || '(empty or not found)'}`);
        }
        if ((file === 'python' || file === 'all') && fileNames.python) {
          parts.push(`--- ${fileNames.python} ---\n${files.python || '(empty or not found)'}`);
        }
        if (file === 'all' && entity_type === 'experiments' && files.json) {
          parts.push(`--- layout.json ---\n${files.json}`);
        }

        return textResult(`${package_name}/${entity_type}/${entity_name}:\n\n${parts.join('\n\n')}`);
      } catch (e) {
        return errorResult(`Failed to read entity file: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );
}
