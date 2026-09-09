'use server';

import { revalidatePath } from 'next/cache';
import { orchestratorDelete, orchestratorGet, orchestratorPost } from '@/lib/api/orchestrator';
import { requireUser } from '@/lib/auth/authz';
import type { ActionResult } from '@/lib/types/management';

export interface ApiTokenRow {
  id: number;
  owner_sub: string;
  label: string | null;
  created_at: string;
}

export async function listApiTokens(): Promise<ApiTokenRow[]> {
  await requireUser();
  return (await orchestratorGet('/api-tokens')) as ApiTokenRow[];
}

export async function createApiToken(label: string): Promise<ActionResult & { token?: string }> {
  await requireUser();
  try {
    // EOS issues and hashes the token, so the secret is returned here once and never stored
    const created = (await orchestratorPost('/api-tokens', { label: label.trim() || null })) as { token: string };
    revalidatePath('/profile');
    return { success: true, token: created.token };
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : 'Failed to create token' };
  }
}

export async function revokeApiToken(id: number): Promise<ActionResult> {
  await requireUser();
  try {
    await orchestratorDelete(`/api-tokens/${id}`);
    revalidatePath('/profile');
    return { success: true };
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : 'Failed to revoke token' };
  }
}
