import { AsyncLocalStorage } from 'node:async_hooks';
import { withMcpAuth } from 'mcp-handler';
import { mcpHandler } from '@/lib/mcp/server';
import { verifyToken } from '@/lib/mcp/auth';
import { env } from '@/lib/env';

// Shared with lib/auth/session.ts via globalThis so tools forward the caller's token to the EOS API
const bearerTokenStore = new AsyncLocalStorage<string>();
(globalThis as { __eosMcpBearerStore?: AsyncLocalStorage<string> }).__eosMcpBearerStore = bearerTokenStore;

const authedHandler = withMcpAuth(mcpHandler, verifyToken, { required: true });

function handler(req: Request): Promise<Response> | Response {
  if (!env.AUTH_ENABLED) return mcpHandler(req);
  const token = req.headers.get('authorization')?.replace(/^Bearer\s+/i, '') ?? '';
  return bearerTokenStore.run(token, () => authedHandler(req));
}

export { handler as GET, handler as POST, handler as DELETE };
