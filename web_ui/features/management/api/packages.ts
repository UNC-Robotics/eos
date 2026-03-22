'use server';

import { revalidatePath } from 'next/cache';
import { orchestratorGet, orchestratorPost } from '@/lib/api/orchestrator';
import type { PackageInfo, ActionResult } from '@/lib/types/management';

/**
 * Get all packages with their active status from the orchestrator
 */
export async function getPackages(): Promise<PackageInfo[]> {
  try {
    const data = (await orchestratorGet('/packages')) as Record<string, boolean>;

    return Object.entries(data).map(([name, active]) => ({
      name,
      active,
    }));
  } catch (error) {
    console.error('Failed to fetch packages:', error);
    return [];
  }
}

/**
 * Load packages into the active set
 */
export async function loadPackages(packageNames: string[]): Promise<ActionResult> {
  try {
    await orchestratorPost('/packages/load', {
      package_names: packageNames,
    });

    revalidatePath('/management');

    return { success: true };
  } catch (error) {
    console.error('Failed to load packages:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to load packages',
    };
  }
}

/**
 * Unload packages from the active set
 */
export async function unloadPackages(packageNames: string[]): Promise<ActionResult> {
  try {
    await orchestratorPost('/packages/unload', {
      package_names: packageNames,
    });

    revalidatePath('/management');

    return { success: true };
  } catch (error) {
    console.error('Failed to unload packages:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to unload packages',
    };
  }
}
