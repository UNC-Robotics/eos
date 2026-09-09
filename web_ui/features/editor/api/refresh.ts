'use server';

/**
 * Server Actions for Package Refresh
 */

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import { requireRole } from '@/lib/auth/authz';

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
    await requireRole('LAB_ADMIN');
    await orchestratorPost('/refresh/packages', {});

    // Revalidate every page whose server render reads spec data so the next
    // navigation reflects the freshly-synced definitions.
    revalidatePath('/editor');
    revalidatePath('/management');
    revalidatePath('/protocol-runs');
    revalidatePath('/tasks');
    revalidatePath('/campaigns');

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
