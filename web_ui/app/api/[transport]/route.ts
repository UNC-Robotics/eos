// NOTE: This MCP endpoint has no authentication. It should only be exposed
// in trusted environments (local network / behind a reverse proxy with auth).
import { mcpHandler } from '@/lib/mcp/server';

export { mcpHandler as GET, mcpHandler as POST, mcpHandler as DELETE };
