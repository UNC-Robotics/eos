'use server';

/**
 * Server Actions for Experiment Type Management
 */

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import { db } from '@/lib/db/client';
import { definitions } from '@/lib/db/schema';
import { eq } from 'drizzle-orm';
import type { ExperimentType, ActionResult } from '@/lib/types/management';

/**
 * Get all experiment types with their loaded status from the database
 */
export async function getExperimentTypes(): Promise<ExperimentType[]> {
  try {
    const results = await db
      .select({
        name: definitions.name,
        loaded: definitions.isLoaded,
      })
      .from(definitions)
      .where(eq(definitions.type, 'experiment'));

    return results.map((row) => ({
      name: row.name,
      loaded: row.loaded,
    }));
  } catch (error) {
    console.error('Failed to fetch experiment types:', error);
    throw new Error('Failed to fetch experiment types from database');
  }
}

/**
 * Load experiment types
 */
export async function loadExperimentTypes(experimentTypes: string[]): Promise<ActionResult> {
  try {
    await orchestratorPost('/experiments/load', {
      experiment_types: experimentTypes,
    });

    // Revalidate the management page to show updated status
    revalidatePath('/management');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to load experiment types:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to load experiment types',
    };
  }
}

/**
 * Unload experiment types
 */
export async function unloadExperimentTypes(experimentTypes: string[]): Promise<ActionResult> {
  try {
    await orchestratorPost('/experiments/unload', {
      experiment_types: experimentTypes,
    });

    // Revalidate the management page to show updated status
    revalidatePath('/management');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to unload experiment types:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to unload experiment types',
    };
  }
}

/**
 * Reload experiment types
 */
export async function reloadExperimentTypes(experimentTypes: string[]): Promise<ActionResult> {
  try {
    await orchestratorPost('/experiments/reload', {
      experiment_types: experimentTypes,
    });

    // Revalidate the management page to show updated status
    revalidatePath('/management');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to reload experiment types:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to reload experiment types',
    };
  }
}
