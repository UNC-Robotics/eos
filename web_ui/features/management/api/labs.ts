'use server';

/**
 * Server Actions for Lab Management
 */

import { revalidatePath } from 'next/cache';
import { orchestratorPost, orchestratorGet } from '@/lib/api/orchestrator';
import type { Lab, ActionResult } from '@/lib/types/management';

/**
 * Get all labs with their loaded status from the orchestrator API (single source of truth)
 */
export async function getLabs(): Promise<Lab[]> {
  try {
    const response = (await orchestratorGet('/labs/')) as Record<string, boolean>;
    return Object.entries(response).map(([name, loaded]) => ({ name, loaded }));
  } catch (error) {
    console.error('Failed to fetch labs:', error);
    throw new Error('Failed to fetch labs');
  }
}

/**
 * Load labs
 */
export async function loadLabs(labTypes: string[]): Promise<ActionResult> {
  try {
    await orchestratorPost('/labs/load', {
      lab_types: labTypes,
    });

    revalidatePath('/management');
    return { success: true };
  } catch (error) {
    console.error('Failed to load labs:', error);
    revalidatePath('/management');
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to load labs',
    };
  }
}

/**
 * Unload labs
 */
export async function unloadLabs(labTypes: string[]): Promise<ActionResult> {
  try {
    await orchestratorPost('/labs/unload', {
      lab_types: labTypes,
    });

    revalidatePath('/management');
    return { success: true };
  } catch (error) {
    console.error('Failed to unload labs:', error);
    revalidatePath('/management');
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to unload labs',
    };
  }
}

/**
 * Reload labs
 */
export async function reloadLabs(labTypes: string[]): Promise<ActionResult> {
  try {
    await orchestratorPost('/labs/reload', {
      lab_types: labTypes,
    });

    revalidatePath('/management');
    return { success: true };
  } catch (error) {
    console.error('Failed to reload labs:', error);
    revalidatePath('/management');
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to reload labs',
    };
  }
}
