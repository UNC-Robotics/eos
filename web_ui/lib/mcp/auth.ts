import { createHash } from 'node:crypto';
import { createRemoteJWKSet, jwtVerify } from 'jose';
import type { AuthInfo } from '@modelcontextprotocol/sdk/server/auth/types.js';
import { getApiTokenOwner, getUserRoles } from '@/lib/db/queries';
import { env } from '@/lib/env';

const INTROSPECTION_CACHE_TTL_MS = 60_000;
const MAX_INTROSPECTION_CACHE = 1024;
const JWT_SEGMENTS = 3;
const EOS_TOKEN_PREFIX = 'eos_pat_';

const jwks = env.AUTH_ENABLED ? createRemoteJWKSet(new URL(`${env.AUTH_ISSUER}/oauth/v2/keys`)) : null;

const introspectionCache = new Map<string, { expiresAt: number; authInfo: AuthInfo }>();

function toAuthInfo(token: string, claims: Record<string, unknown>): AuthInfo {
  return {
    token,
    clientId: (claims.client_id as string) ?? (claims.sub as string),
    scopes: [],
    extra: { sub: claims.sub as string },
  };
}

async function introspect(token: string): Promise<AuthInfo | undefined> {
  const clientId = env.AUTH_INTROSPECTION_CLIENT_ID;
  const clientSecret = env.AUTH_INTROSPECTION_CLIENT_SECRET;
  if (!clientId || !clientSecret) return undefined;

  const cached = introspectionCache.get(token);
  if (cached && cached.expiresAt > Date.now()) return cached.authInfo;

  const response = await fetch(`${env.AUTH_ISSUER}/oauth/v2/introspect`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Authorization: `Basic ${Buffer.from(`${encodeURIComponent(clientId)}:${encodeURIComponent(clientSecret)}`).toString('base64')}`,
    },
    body: new URLSearchParams({ token }),
  });
  if (!response.ok) return undefined;

  const claims = await response.json();
  if (!claims.active) return undefined;

  // Reject tokens issued for another client/app in the same Zitadel instance (mirrors the JWT audience check)
  const audiences = Array.isArray(claims.aud) ? [...claims.aud] : claims.aud ? [claims.aud] : [];
  if (claims.client_id) audiences.push(claims.client_id);
  if (!audiences.includes(env.AUTH_PROJECT_ID)) return undefined;

  const authInfo = toAuthInfo(token, claims);
  const now = Date.now();
  let ttl = INTROSPECTION_CACHE_TTL_MS;
  if (typeof claims.exp === 'number') ttl = Math.min(ttl, Math.max(0, claims.exp * 1000 - now));
  for (const [key, entry] of introspectionCache) if (entry.expiresAt <= now) introspectionCache.delete(key);
  introspectionCache.set(token, { expiresAt: now + ttl, authInfo });
  while (introspectionCache.size > MAX_INTROSPECTION_CACHE) {
    const oldest = introspectionCache.keys().next().value;
    if (oldest === undefined) break;
    introspectionCache.delete(oldest);
  }
  return authInfo;
}

/** Resolve an EOS-issued API token to its owner. Mirrors the EOS API's local resolution. */
async function verifyEosToken(token: string): Promise<AuthInfo | undefined> {
  const ownerSub = await getApiTokenOwner(createHash('sha256').update(token).digest('hex'));
  if (!ownerSub) return undefined;
  return { token, clientId: ownerSub, scopes: [], extra: { sub: ownerSub } };
}

/**
 * Verify a bearer token for the MCP endpoint. EOS API tokens resolve locally, JWTs via JWKS,
 * and other opaque tokens via introspection.
 */
export async function verifyToken(_req: Request, bearerToken?: string): Promise<AuthInfo | undefined> {
  if (!bearerToken || !env.AUTH_ENABLED) return undefined;

  if (bearerToken.startsWith(EOS_TOKEN_PREFIX)) return verifyEosToken(bearerToken);
  if (!jwks) return undefined;

  if (bearerToken.split('.').length === JWT_SEGMENTS) {
    try {
      const { payload } = await jwtVerify(bearerToken, jwks, {
        issuer: env.AUTH_ISSUER,
        audience: env.AUTH_PROJECT_ID,
      });
      return toAuthInfo(bearerToken, payload as Record<string, unknown>);
    } catch {
      return undefined;
    }
  }
  return introspect(bearerToken);
}

/** True when the MCP caller has the local superuser role, or when auth is disabled. */
export async function isSuperuserCaller(authInfo: AuthInfo | undefined): Promise<boolean> {
  if (!env.AUTH_ENABLED) return true;
  const sub = authInfo?.extra?.sub as string | undefined;
  if (!sub) return false;
  return (await getUserRoles(sub)).some((r) => r.role === 'SUPERUSER');
}
