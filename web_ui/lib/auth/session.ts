// Server-only module: do not import from client components. (No 'server-only' marker;
// Turbopack's module merging falsely flags it through the server-action graph.)
import { auth } from '@/auth';
import { env } from '@/lib/env';

// The MCP route stores its AsyncLocalStorage on globalThis (a static node:async_hooks
// import here would leak into client chunks via the server-action module graph)
interface BearerStore {
  getStore(): string | undefined;
}

function mcpBearerToken(): string | undefined {
  return (globalThis as { __eosMcpBearerStore?: BearerStore }).__eosMcpBearerStore?.getStore();
}

export interface SessionUser {
  sub: string;
  name?: string | null;
  email?: string | null;
}

// Stand-in user when authentication is disabled (dev mode); roles/superuser come from is-auth-disabled checks
export const DEV_USER: SessionUser = { sub: 'dev', name: 'Dev User' };

/** Get the signed-in user, or null if unauthenticated. Returns a stand-in user when auth is disabled. */
export async function getSessionUser(): Promise<SessionUser | null> {
  if (!env.AUTH_ENABLED) return DEV_USER;
  const session = await auth();
  if (!session?.user || session.error === 'RefreshTokenError') return null;
  return {
    sub: session.user.sub,
    name: session.user.name,
    email: session.user.email,
  };
}

/** Get the Zitadel access token for forwarding to the EOS API, or null when auth is disabled. */
export async function getAccessToken(): Promise<string | null> {
  if (!env.AUTH_ENABLED) return null;
  const mcpToken = mcpBearerToken();
  if (mcpToken) return mcpToken;
  const session = await auth();
  if (!session || session.error === 'RefreshTokenError') return null;
  return session.accessToken ?? null;
}
