/**
 * Definition Data Access Layer
 * Provides optimized database queries for EOS definitions
 */

import { db } from '../db/client';
import { definitions } from '../db/schema';
import { eq, and, inArray } from 'drizzle-orm';
import { cache } from 'react';

// ============================================================================
// TypeScript Types
// ============================================================================

export interface TaskSpec {
  type: string;
  desc?: string;
  devices?: Record<string, { type: string }>;
  input_parameters?: Record<string, unknown>;
  input_resources?: Record<string, { type: string }>;
  output_parameters?: Record<string, unknown>;
  output_resources?: Record<string, { type: string }>;
}

export interface DeviceSpec {
  type: string;
  desc?: string;
  init_parameters?: Record<string, unknown>;
}

export interface LabSpec {
  name: string;
  desc: string;
  devices: Record<
    string,
    {
      type: string;
      computer: string;
      desc?: string;
      init_parameters?: Record<string, unknown>;
      meta?: Record<string, unknown>;
    }
  >;
  computers?: Record<string, { ip: string; desc?: string }>;
  resource_types?: Record<string, { meta?: Record<string, unknown> }>;
  resources?: Record<string, { type: string; meta?: Record<string, unknown> }>;
}

export interface ExperimentTaskConfig {
  name: string;
  type: string;
  desc?: string;
  parameters?: Record<string, unknown>;
  devices?: Record<string, unknown>;
  resources?: Record<string, unknown>;
  dependencies?: string[];
}

export interface ExperimentSpec {
  type: string;
  desc: string;
  labs: string[];
  tasks: ExperimentTaskConfig[];
  resources?: Record<string, unknown>;
}

export interface Definition {
  type: string;
  name: string;
  data: unknown;
  isLoaded: boolean;
  packageName: string;
  sourcePath: string;
  createdAt: Date;
  updatedAt: Date;
}

// ============================================================================
// Cached Query Functions
// ============================================================================

/**
 * Get all task definitions.
 * Cached for optimal performance in React Server Components.
 * Returns a map keyed by task type (from data.type field).
 */
export const getTaskSpecs = cache(async (): Promise<Record<string, TaskSpec & { packageName: string }>> => {
  const results = await db.select().from(definitions).where(eq(definitions.type, 'task')).execute();

  return results.reduce(
    (acc, def) => {
      const taskSpec = def.data as TaskSpec;
      // Use the task type from data as the key (not name which is the directory name)
      acc[taskSpec.type] = { ...taskSpec, packageName: def.packageName };
      return acc;
    },
    {} as Record<string, TaskSpec & { packageName: string }>
  );
});

/**
 * Get a specific task definition by name.
 */
export const getTaskSpec = cache(async (taskName: string): Promise<TaskSpec | null> => {
  const result = await db
    .select()
    .from(definitions)
    .where(and(eq(definitions.type, 'task'), eq(definitions.name, taskName)))
    .limit(1)
    .execute();

  return (result[0]?.data as TaskSpec) || null;
});

/**
 * Get all device definitions.
 * Cached for optimal performance in React Server Components.
 * Returns a map keyed by device type (from data.type field).
 */
export const getDeviceSpecs = cache(async (): Promise<Record<string, DeviceSpec>> => {
  const results = await db.select().from(definitions).where(eq(definitions.type, 'device')).execute();

  return results.reduce(
    (acc, def) => {
      const deviceSpec = def.data as DeviceSpec;
      // Use the device type from data as the key (not name which is the directory name)
      acc[deviceSpec.type] = deviceSpec;
      return acc;
    },
    {} as Record<string, DeviceSpec>
  );
});

/**
 * Get all lab definitions.
 * @param loadedOnly - If true, only return labs that are currently loaded in EOS
 */
export const getLabSpecs = cache(async (loadedOnly: boolean = false): Promise<Record<string, LabSpec>> => {
  const query = db
    .select()
    .from(definitions)
    .where(loadedOnly ? and(eq(definitions.type, 'lab'), eq(definitions.isLoaded, true)) : eq(definitions.type, 'lab'));

  const results = await query.execute();

  return results.reduce(
    (acc, def) => {
      acc[def.name] = def.data as LabSpec;
      return acc;
    },
    {} as Record<string, LabSpec>
  );
});

/**
 * Get a specific lab definition by name.
 */
export const getLabSpec = cache(async (labName: string): Promise<LabSpec | null> => {
  const result = await db
    .select()
    .from(definitions)
    .where(and(eq(definitions.type, 'lab'), eq(definitions.name, labName)))
    .limit(1)
    .execute();

  return (result[0]?.data as LabSpec) || null;
});

/**
 * Get all experiment definitions.
 * @param loadedOnly - If true, only return experiments that are currently loaded in EOS
 */
export const getExperimentSpecs = cache(
  async (loadedOnly: boolean = false): Promise<Record<string, ExperimentSpec>> => {
    const query = db
      .select()
      .from(definitions)
      .where(
        loadedOnly
          ? and(eq(definitions.type, 'experiment'), eq(definitions.isLoaded, true))
          : eq(definitions.type, 'experiment')
      );

    const results = await query.execute();

    return results.reduce(
      (acc, def) => {
        acc[def.name] = def.data as ExperimentSpec;
        return acc;
      },
      {} as Record<string, ExperimentSpec>
    );
  }
);

/**
 * Get devices available in specific labs.
 * Optimized to fetch in a single query with batch processing.
 * @param labNames - Array of lab names to get devices for
 * @returns Map of lab name to devices
 */
export const getLabDevices = cache(async (labNames: string[]): Promise<Record<string, Record<string, unknown>>> => {
  if (labNames.length === 0) {
    return {};
  }

  const results = await db
    .select()
    .from(definitions)
    .where(and(eq(definitions.type, 'lab'), inArray(definitions.name, labNames)))
    .execute();

  return results.reduce(
    (acc, def) => {
      const labSpec = def.data as LabSpec;
      acc[def.name] = labSpec.devices || {};
      return acc;
    },
    {} as Record<string, Record<string, unknown>>
  );
});

/**
 * Get all definitions of a particular type (for admin/debugging purposes).
 * @param defType - One of: 'task', 'device', 'lab', 'experiment'
 * @param loadedOnly - For labs/experiments, filter by loaded status
 */
export const getDefsByType = cache(
  async (defType: 'task' | 'device' | 'lab' | 'experiment', loadedOnly: boolean = false): Promise<Definition[]> => {
    const query = db
      .select()
      .from(definitions)
      .where(
        loadedOnly && (defType === 'lab' || defType === 'experiment')
          ? and(eq(definitions.type, defType), eq(definitions.isLoaded, true))
          : eq(definitions.type, defType)
      );

    return await query.execute();
  }
);

/**
 * Get all definitions (for admin/debugging purposes).
 */
export const getAllDefs = cache(async (): Promise<Definition[]> => {
  return await db.select().from(definitions).execute();
});

/**
 * Get definition metadata (without full data payload).
 * Useful for listing definitions without transferring large JSON payloads.
 */
export const getDefsMetadata = cache(
  async (defType?: 'task' | 'device' | 'lab' | 'experiment'): Promise<Array<Omit<Definition, 'data'>>> => {
    const query = db
      .select({
        type: definitions.type,
        name: definitions.name,
        isLoaded: definitions.isLoaded,
        packageName: definitions.packageName,
        sourcePath: definitions.sourcePath,
        createdAt: definitions.createdAt,
        updatedAt: definitions.updatedAt,
      })
      .from(definitions);

    if (defType) {
      query.where(eq(definitions.type, defType));
    }

    return await query.execute();
  }
);

/**
 * Get loaded status for all entity types.
 * Returns lists of entity names that are currently loaded in EOS.
 * Optimized with a single database query.
 */
export const getLoadedStatus = cache(
  async (): Promise<{
    labs: string[];
    experiments: string[];
    tasks: string[];
    devices: string[];
  }> => {
    const results = await db
      .select({
        type: definitions.type,
        name: definitions.name,
      })
      .from(definitions)
      .where(eq(definitions.isLoaded, true))
      .execute();

    // Group results by type
    const loaded = {
      labs: [] as string[],
      experiments: [] as string[],
      tasks: [] as string[],
      devices: [] as string[],
    };

    for (const def of results) {
      if (def.type === 'lab') {
        loaded.labs.push(def.name);
      } else if (def.type === 'experiment') {
        loaded.experiments.push(def.name);
      } else if (def.type === 'task') {
        loaded.tasks.push(def.name);
      } else if (def.type === 'device') {
        loaded.devices.push(def.name);
      }
    }

    return loaded;
  }
);
