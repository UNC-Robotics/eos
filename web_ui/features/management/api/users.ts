'use server';

/**
 * Server Actions for User Management
 *
 * Accounts live in Zitadel (shared across EOS instances); role assignments are local
 * to this instance and are written through the EOS API.
 */

import { randomBytes } from 'node:crypto';
import { revalidatePath } from 'next/cache';
import { requireSuperuser } from '@/lib/auth/authz';
import { partitionSuperuser } from '@/lib/auth/roles';
import { orchestratorPost, orchestratorGet, orchestratorDelete } from '@/lib/api/orchestrator';
import * as zitadel from '@/lib/api/zitadel';
import { getAllUserRoles, getUserRoles, type UserRoleRow } from '@/lib/db/queries';
import type { ActionResult } from '@/lib/types/management';

export interface ManagedUser extends zitadel.ZitadelUser {
  superuser: boolean;
  roles: UserRoleRow[];
}

export interface CreateUserInput {
  username: string;
  email: string;
  givenName: string;
  familyName: string;
  superuser: boolean;
  roles: { role: string; labName?: string }[];
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

/** Run a superuser-only mutation, revalidate /management, and normalize success/error. */
async function superuserAction(fallback: string, op: () => Promise<unknown>): Promise<ActionResult> {
  await requireSuperuser();
  try {
    await op();
    revalidatePath('/management');
    return { success: true };
  } catch (error) {
    return { success: false, error: errorMessage(error, fallback) };
  }
}

export async function getUsers(): Promise<ManagedUser[]> {
  await requireSuperuser();
  const [users, allRoles] = await Promise.all([zitadel.listUsers(), getAllUserRoles()]);
  const rolesBySub = new Map<string, UserRoleRow[]>();
  for (const role of allRoles) {
    rolesBySub.set(role.sub, [...(rolesBySub.get(role.sub) ?? []), role]);
  }
  // Superuser is shown via its own toggle, so partitionSuperuser keeps it out of the per-instance role list
  return users.map((user) => ({ ...user, ...partitionSuperuser(rolesBySub.get(user.userId) ?? []) }));
}

export async function getLabNames(): Promise<string[]> {
  await requireSuperuser();
  const labs = (await orchestratorGet('/labs/')) as Record<string, boolean>;
  return Object.keys(labs);
}

/** Create an account with a temporary password and assign its roles. Returns the password once. */
export async function createUser(
  input: CreateUserInput
): Promise<ActionResult & { temporaryPassword?: string; userId?: string }> {
  await requireSuperuser();
  try {
    const temporaryPassword = `${randomBytes(9).toString('base64url')}!1Aa`;
    const userId = await zitadel.createUser({ ...input, temporaryPassword });

    if (input.superuser) {
      await orchestratorPost('/admin/roles', { sub: userId, role: 'SUPERUSER', lab_name: null });
    }
    for (const role of input.roles) {
      await orchestratorPost('/admin/roles', { sub: userId, role: role.role, lab_name: role.labName ?? null });
    }

    revalidatePath('/management');
    return { success: true, temporaryPassword, userId };
  } catch (error) {
    return { success: false, error: errorMessage(error, 'Failed to create user') };
  }
}

export async function setUserActive(userId: string, active: boolean): Promise<ActionResult> {
  return superuserAction('Failed to update user', () =>
    active ? zitadel.reactivateUser(userId) : zitadel.deactivateUser(userId)
  );
}

export async function deleteUser(userId: string): Promise<ActionResult> {
  return superuserAction('Failed to delete user', () => zitadel.deleteUser(userId));
}

export async function setSuperuser(userId: string, superuser: boolean): Promise<ActionResult> {
  return superuserAction('Failed to update superuser role', async () => {
    if (superuser) {
      await orchestratorPost('/admin/roles', { sub: userId, role: 'SUPERUSER', lab_name: null });
    } else {
      const row = (await getUserRoles(userId)).find((r) => r.role === 'SUPERUSER');
      if (row) await orchestratorDelete(`/admin/roles/${row.id}`);
    }
  });
}

export async function assignRole(sub: string, role: string, labName?: string): Promise<ActionResult> {
  return superuserAction('Failed to assign role', () =>
    orchestratorPost('/admin/roles', { sub, role, lab_name: labName ?? null })
  );
}

export async function revokeRole(roleId: number): Promise<ActionResult> {
  return superuserAction('Failed to revoke role', () => orchestratorDelete(`/admin/roles/${roleId}`));
}
