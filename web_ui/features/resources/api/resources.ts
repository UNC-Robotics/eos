'use server';

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import { DEFAULT_PAGE_SIZE, type TableQueryOptions } from '@/lib/types/table';
import { getAllResources, type PaginatedResult, type ResourceRow } from '@/lib/db/queries';
import type { ActionResult } from '@/lib/types/management';

export async function getResources(options: TableQueryOptions = {}): Promise<PaginatedResult<ResourceRow>> {
  return await getAllResources({ limit: DEFAULT_PAGE_SIZE, offset: 0, ...options });
}

export async function resetResources(resourceNames: string[]): Promise<ActionResult> {
  try {
    await orchestratorPost('/resources/reset', { resource_names: resourceNames });
    revalidatePath('/resources');
    return { success: true };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to reset resources',
    };
  }
}
