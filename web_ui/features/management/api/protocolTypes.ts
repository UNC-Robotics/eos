'use server';

/**
 * Server Actions for ProtocolRun Type Management
 */

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import { db } from '@/lib/db/client';
import { definitions } from '@/lib/db/schema';
import { eq } from 'drizzle-orm';
import type { ProtocolType, ActionResult } from '@/lib/types/management';

/**
 * Get all protocol types with their loaded status from the database
 */
export async function getProtocolTypes(): Promise<ProtocolType[]> {
  try {
    const results = await db
      .select({
        name: definitions.name,
        loaded: definitions.isLoaded,
      })
      .from(definitions)
      .where(eq(definitions.type, 'protocol'));

    return results.map((row) => ({
      name: row.name,
      loaded: row.loaded,
    }));
  } catch (error) {
    console.error('Failed to fetch protocol types:', error);
    throw new Error('Failed to fetch protocol types from database');
  }
}

/**
 * Load protocol types
 */
export async function loadProtocolTypes(protocolTypes: string[]): Promise<ActionResult> {
  try {
    await orchestratorPost('/protocols/load', {
      protocol_types: protocolTypes,
    });

    // Revalidate the management page to show updated status
    revalidatePath('/management');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to load protocol types:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to load protocol types',
    };
  }
}

/**
 * Unload protocol types
 */
export async function unloadProtocolTypes(protocolTypes: string[]): Promise<ActionResult> {
  try {
    await orchestratorPost('/protocols/unload', {
      protocol_types: protocolTypes,
    });

    // Revalidate the management page to show updated status
    revalidatePath('/management');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to unload protocol types:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to unload protocol types',
    };
  }
}

/**
 * Reload protocol types
 */
export async function reloadProtocolTypes(protocolTypes: string[]): Promise<ActionResult> {
  try {
    await orchestratorPost('/protocols/reload', {
      protocol_types: protocolTypes,
    });

    // Revalidate the management page to show updated status
    revalidatePath('/management');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to reload protocol types:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to reload protocol types',
    };
  }
}
