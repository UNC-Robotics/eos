import 'server-only';
import { cache } from 'react';
import { getUserRoles } from '@/lib/db/queries';
import { env } from '@/lib/env';
import { rolesSatisfy, type RoleName } from './roles';
import { getSessionUser, type SessionUser } from './session';

export type { RoleName } from './roles';

// Roles that can be required as a minimum via requireRole; superuser has its own guard.
export type RequirableRole = Exclude<RoleName, 'SUPERUSER'>;

export class AuthorizationError extends Error {}

// Memoized per request render so multiple guard checks in one render share a single query
const fetchRoles = cache(
  async (sub: string): Promise<RoleName[]> => (await getUserRoles(sub)).map((r) => r.role as RoleName)
);

export async function rolesFor(sub: string): Promise<RoleName[]> {
  // Auth disabled grants full access, mirroring the EOS API's is-auth-disabled short-circuit
  return env.AUTH_ENABLED ? fetchRoles(sub) : [];
}

export function isSuperuser(roles: RoleName[]): boolean {
  return !env.AUTH_ENABLED || roles.includes('SUPERUSER');
}

/** Get the session user with their local roles. Throws if unauthenticated. */
export async function requireUser(): Promise<SessionUser & { roles: RoleName[] }> {
  const user = await getSessionUser();
  if (!user) throw new AuthorizationError('Not authenticated');
  return { ...user, roles: await rolesFor(user.sub) };
}

/**
 * Require at least the given instance-wide role; superuser and lab admins always qualify.
 * Mirrors the EOS API guard semantics.
 */
export async function requireRole(minimum: RequirableRole): Promise<SessionUser> {
  const user = await requireUser();
  if (isSuperuser(user.roles) || rolesSatisfy(user.roles, minimum)) return user;
  throw new AuthorizationError(`Requires the ${minimum.toLowerCase()} role`);
}

/** Require the local superuser role for this instance. */
export async function requireSuperuser(): Promise<SessionUser> {
  const user = await requireUser();
  if (!isSuperuser(user.roles)) throw new AuthorizationError('Requires the superuser role');
  return user;
}

/** True when the current user is a superuser (or auth is disabled). Returns false if unauthenticated. */
export async function currentUserIsSuperuser(): Promise<boolean> {
  const user = await getSessionUser();
  if (!user) return false;
  return isSuperuser(await rolesFor(user.sub));
}

/** True when the current user is a lab admin or superuser (or auth is disabled). Gates the management page. */
export async function currentUserIsAdmin(): Promise<boolean> {
  const user = await getSessionUser();
  if (!user) return false;
  const roles = await rolesFor(user.sub);
  return isSuperuser(roles) || rolesSatisfy(roles, 'LAB_ADMIN');
}

/** Route-handler variant of requireRole: returns an error Response to send, or null when allowed. */
export async function requireRoleResponse(minimum: RequirableRole): Promise<Response | null> {
  try {
    await requireRole(minimum);
    return null;
  } catch (error) {
    const message = error instanceof AuthorizationError ? error.message : 'Forbidden';
    return Response.json({ error: message }, { status: 403 });
  }
}
