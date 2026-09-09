/**
 * Zitadel Management API Client
 *
 * Server-only client for account management, authenticated with a service user PAT.
 */

import 'server-only';
import { env } from '@/lib/env';

export interface ZitadelUser {
  userId: string;
  username: string;
  state: string;
  displayName: string;
  email: string;
}

async function zitadelFetch(path: string, init?: RequestInit): Promise<Record<string, unknown>> {
  const response = await fetch(`${env.AUTH_ISSUER}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${env.AUTH_PAT}`,
      'x-zitadel-orgid': env.AUTH_ORG_ID!,
      ...init?.headers,
    },
    cache: 'no-store',
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as { message?: string }).message ?? `Zitadel API error (${response.status})`);
  }
  return response.json().catch(() => ({}));
}

export async function listUsers(): Promise<ZitadelUser[]> {
  const result = await zitadelFetch('/v2/users', {
    method: 'POST',
    body: JSON.stringify({
      query: { limit: 1000 },
      queries: [{ organizationIdQuery: { organizationId: env.AUTH_ORG_ID } }, { typeQuery: { type: 'TYPE_HUMAN' } }],
    }),
  });

  type RawUser = {
    userId: string;
    username: string;
    state: string;
    human?: { profile?: { displayName?: string }; email?: { email?: string } };
  };
  return ((result.result as RawUser[]) ?? []).map((user) => ({
    userId: user.userId,
    username: user.username,
    state: user.state.replace('USER_STATE_', ''),
    displayName: user.human?.profile?.displayName ?? '',
    email: user.human?.email?.email ?? '',
  }));
}

export async function createUser(input: {
  username: string;
  email: string;
  givenName: string;
  familyName: string;
  temporaryPassword: string;
}): Promise<string> {
  const result = await zitadelFetch('/v2/users/human', {
    method: 'POST',
    body: JSON.stringify({
      username: input.username,
      organization: { orgId: env.AUTH_ORG_ID },
      profile: { givenName: input.givenName, familyName: input.familyName },
      email: { email: input.email, isVerified: true },
      password: { password: input.temporaryPassword, changeRequired: true },
    }),
  });
  return result.userId as string;
}

export async function deactivateUser(userId: string): Promise<void> {
  await zitadelFetch(`/v2/users/${userId}/deactivate`, { method: 'POST' });
}

export async function reactivateUser(userId: string): Promise<void> {
  await zitadelFetch(`/v2/users/${userId}/reactivate`, { method: 'POST' });
}

export async function deleteUser(userId: string): Promise<void> {
  await zitadelFetch(`/v2/users/${userId}`, { method: 'DELETE' });
}

/** Change a user's password, verifying their current password. */
export async function changePassword(userId: string, currentPassword: string, newPassword: string): Promise<void> {
  await zitadelFetch(`/v2/users/${userId}/password`, {
    method: 'POST',
    body: JSON.stringify({
      currentPassword,
      newPassword: { password: newPassword, changeRequired: false },
    }),
  });
}
