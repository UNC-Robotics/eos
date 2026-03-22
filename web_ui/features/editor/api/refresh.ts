'use server';

/**
 * Server Actions for Package Refresh
 */

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';

export interface ActionResult {
  success: boolean;
  error?: string;
  message?: string;
}

/**
 * Refresh package discovery and sync definitions.
 * Triggers the EOS orchestrator to re-scan the filesystem for new/deleted entities.
 */
export async function refreshPackages(): Promise<ActionResult> {
  try {
    await orchestratorPost('/refresh/packages', {});

    // Revalidate both editor and management pages to reflect changes
    revalidatePath('/editor');
    revalidatePath('/management');

    return {
      success: true,
      message: 'Packages refreshed successfully',
    };
  } catch (error) {
    console.error('Failed to refresh packages:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to refresh packages',
    };
  }
}
