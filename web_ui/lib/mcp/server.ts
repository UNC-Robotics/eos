import { createMcpHandler } from 'mcp-handler';
import { registerAllTools } from './tools/register';

export const mcpHandler = createMcpHandler(
  (server) => {
    registerAllTools(server);
  },
  {
    capabilities: {},
    serverInfo: {
      name: 'EOS',
      version: '1.0.0',
    },
  },
  {
    basePath: '/api',
  }
);
