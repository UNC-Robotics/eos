import { z } from 'zod/v3';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { textResult, errorResult } from '../helpers/format';
import { ENTITY_FILE_NAMES, type EntityType, type EntityLeafNode, type TreeNode } from '@/lib/types/filesystem';
import { scanPackages, getPackageTree, readEntityFiles } from '@/lib/filesystem/operations';

function flattenLeaves(nodes: TreeNode[]): EntityLeafNode[] {
  const out: EntityLeafNode[] = [];
  for (const node of nodes) {
    if (node.kind === 'entity') out.push(node);
    else out.push(...flattenLeaves(node.children));
  }
  return out;
}

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
            p.hasProtocols && 'protocols',
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
      description: 'List all entities (devices, tasks, labs, protocols) in a package.',
      inputSchema: {
        package_name: z.string().describe('Package name (e.g. "eos_examples/color_lab")'),
        entity_type: z.enum(['devices', 'tasks', 'labs', 'protocols']).optional().describe('Filter by entity type'),
      },
    },
    async ({ package_name, entity_type }) => {
      try {
        const tree = await getPackageTree(package_name);
        const types = entity_type ? [entity_type] : (['devices', 'tasks', 'labs', 'protocols'] as const);

        const sections = types.map((type) => {
          const entities = flattenLeaves(tree[type]);
          if (entities.length === 0) return `${type}: (none)`;
          const { yaml, python } = ENTITY_FILE_NAMES[type];
          const files = (e: (typeof entities)[number]) =>
            [e.hasYaml && yaml, e.hasPython && python].filter(Boolean).join(', ');
          return `${type}:\n${entities.map((e) => `  • ${e.path} (${files(e)})`).join('\n')}`;
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
        'Read the files of an entity. Tasks and devices are a Python file, labs a YAML file, and protocols a YAML file plus an optional optimizer.py and layout.json.',
      inputSchema: {
        package_name: z.string().describe('Package name (e.g. "eos_examples/color_lab")'),
        entity_type: z.enum(['devices', 'tasks', 'labs', 'protocols']).describe('Entity type'),
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

        if ((file === 'yaml' || file === 'all') && fileNames.yaml) {
          parts.push(`--- ${fileNames.yaml} ---\n${files.yaml || '(empty or not found)'}`);
        }
        if ((file === 'python' || file === 'all') && fileNames.python) {
          parts.push(`--- ${fileNames.python} ---\n${files.python || '(empty or not found)'}`);
        }
        if (file === 'all' && entity_type === 'protocols' && files.json) {
          parts.push(`--- layout.json ---\n${files.json}`);
        }

        return textResult(`${package_name}/${entity_type}/${entity_name}:\n\n${parts.join('\n\n')}`);
      } catch (e) {
        return errorResult(`Failed to read entity file: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );
}
