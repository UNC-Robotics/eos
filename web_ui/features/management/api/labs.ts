'use server';

/**
 * Server Actions for Lab Management
 */

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import { db } from '@/lib/db/client';
import { definitions } from '@/lib/db/schema';
import { eq } from 'drizzle-orm';
import type { Lab, ActionResult } from '@/lib/types/management';

/**
 * Get all labs with their loaded status from the database
 */
export async function getLabs(): Promise<Lab[]> {
  try {
    const results = await db
      .select({
        name: definitions.name,
        loaded: definitions.isLoaded,
      })
      .from(definitions)
      .where(eq(definitions.type, 'lab'));

    return results.map((row) => ({
      name: row.name,
      loaded: row.loaded,
    }));
  } catch (error) {
    console.error('Failed to fetch labs:', error);
    throw new Error('Failed to fetch labs from database');
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

    // Revalidate the management page to show updated status
    revalidatePath('/management');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to load labs:', error);
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

    // Revalidate the management page to show updated status
    revalidatePath('/management');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to unload labs:', error);
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

    // Revalidate the management page to show updated status
    revalidatePath('/management');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to reload labs:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to reload labs',
    };
  }
}
