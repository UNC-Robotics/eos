'use server';

/**
 * Server Action for fetching loaded entity status
 */

import { getLoadedStatus as getLoadedStatusFromDb } from '@/lib/api/specs';

/**
 * Get loaded status for all entity types.
 * This is a server action that wraps the database query.
 */
export async function getLoadedStatus(): Promise<{
  labs: string[];
  experiments: string[];
  tasks: string[];
  devices: string[];
}> {
  return await getLoadedStatusFromDb();
}
