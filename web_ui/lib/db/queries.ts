/**
 * Database Query Functions
 *
 * These functions query the EOS database for tasks, experiments, and campaigns.
 * Implements server-side pagination, filtering, sorting, and search.
 */

import { desc, count, eq, and, asc, or, ilike, inArray } from 'drizzle-orm';
import type { SQL } from 'drizzle-orm';
import { db } from './client';
import { tasks, experiments, campaigns, campaignSamples } from './schema';
import { DEFAULT_PAGE_SIZE, type TableQueryOptions, type ColumnFilterOption } from '@/lib/types/table';

// Paginated result wrapper
export interface PaginatedResult<T> {
  data: T[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Query helpers (shared across all entity types) ─────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type DrizzleColumn = any;

function buildWhereClause(
  filters: ColumnFilterOption[] | undefined,
  search: string | undefined,
  columnMap: Record<string, DrizzleColumn>,
  searchColumns: DrizzleColumn[]
): SQL | undefined {
  const conditions: SQL[] = [];

  if (filters?.length) {
    for (const filter of filters) {
      const col = columnMap[filter.column];
      if (!col) continue;
      if (Array.isArray(filter.value)) {
        if (filter.value.length > 0) {
          conditions.push(inArray(col, filter.value));
        }
      } else if (typeof filter.value === 'string' && filter.value.length > 0) {
        conditions.push(ilike(col, `%${filter.value}%`));
      }
    }
  }

  if (search?.trim()) {
    const searchOr = or(...searchColumns.map((col) => ilike(col, `%${search.trim()}%`)));
    if (searchOr) conditions.push(searchOr);
  }

  return conditions.length > 0 ? and(...conditions) : undefined;
}

function buildOrderBy(
  sort: TableQueryOptions['sort'],
  columnMap: Record<string, DrizzleColumn>,
  defaultColumn: DrizzleColumn
): SQL {
  if (sort && columnMap[sort.column]) {
    const col = columnMap[sort.column];
    return sort.direction === 'asc' ? asc(col) : desc(col);
  }
  return desc(defaultColumn);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type DrizzleTable = any;

async function queryPaginated(
  table: DrizzleTable,
  options: TableQueryOptions,
  columnMap: Record<string, DrizzleColumn>,
  searchColumns: DrizzleColumn[],
  defaultSort: DrizzleColumn
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
): Promise<{ rows: any[]; total: number; limit: number; offset: number }> {
  const { limit = DEFAULT_PAGE_SIZE, offset = 0, sort, filters, search } = options;

  const whereClause = buildWhereClause(filters, search, columnMap, searchColumns);
  const orderByClause = buildOrderBy(sort, columnMap, defaultSort);

  const dataQuery = db.select().from(table);
  const countQuery = db.select({ value: count() }).from(table);

  const [rows, [{ value: total }]] = await Promise.all([
    (whereClause ? dataQuery.where(whereClause) : dataQuery).orderBy(orderByClause).limit(limit).offset(offset),
    whereClause ? countQuery.where(whereClause) : countQuery,
  ]);

  return { rows, total, limit, offset };
}

// ─── Column configs per entity type ─────────────────────────────────────────

const TASK_COLUMNS: Record<string, DrizzleColumn> = {
  name: tasks.name,
  type: tasks.type,
  experiment_name: tasks.experimentName,
  status: tasks.status,
  created_at: tasks.createdAt,
};
const TASK_SEARCH_COLUMNS = [tasks.name, tasks.type, tasks.experimentName];

const EXPERIMENT_COLUMNS: Record<string, DrizzleColumn> = {
  name: experiments.name,
  type: experiments.type,
  campaign: experiments.campaign,
  owner: experiments.owner,
  status: experiments.status,
  created_at: experiments.createdAt,
};
const EXPERIMENT_SEARCH_COLUMNS = [experiments.name, experiments.type, experiments.campaign, experiments.owner];

const CAMPAIGN_COLUMNS: Record<string, DrizzleColumn> = {
  name: campaigns.name,
  experiment_type: campaigns.experimentType,
  owner: campaigns.owner,
  status: campaigns.status,
  created_at: campaigns.createdAt,
};
const CAMPAIGN_SEARCH_COLUMNS = [campaigns.name, campaigns.experimentType, campaigns.owner];

// ─── Database row types ─────────────────────────────────────────────────────

export interface TaskRow {
  name: string;
  type: string;
  priority: number;
  status: string;
  errorMessage: string | null;
  devices: Record<string, unknown>;
  inputParameters: Record<string, unknown> | null;
  inputResources: Record<string, unknown> | null;
  outputParameters: Record<string, unknown> | null;
  outputResources: Record<string, unknown> | null;
  outputFileNames: string[] | null;
  allocationTimeout: number;
  meta: Record<string, unknown>;
  experimentName: string | null;
  createdAt: Date;
  startTime: Date | null;
  endTime: Date | null;
}

export interface ExperimentRow {
  name: string;
  type: string;
  campaign: string | null;
  owner: string;
  priority: number;
  parameters: Record<string, Record<string, unknown>>;
  inputResources?: Record<string, unknown>;
  outputParameters?: Record<string, unknown>;
  outputResources?: Record<string, unknown>;
  meta: Record<string, unknown> | null;
  resume: boolean;
  status: string;
  errorMessage: string | null;
  createdAt: Date;
  startTime: Date | null;
  endTime: Date | null;
}

export interface CampaignRow {
  name: string;
  experimentType: string;
  owner: string;
  priority: number;
  maxExperiments: number;
  maxConcurrentExperiments: number;
  optimize: boolean;
  optimizerIp: string | null;
  globalParameters: Record<string, Record<string, unknown>> | null;
  experimentParameters: Array<Record<string, Record<string, unknown>>> | null;
  meta: Record<string, unknown> | null;
  resume: boolean;
  status: string;
  errorMessage: string | null;
  experimentsCompleted: number;
  paretoSolutions: Array<Record<string, unknown>> | null;
  createdAt: Date;
  startTime: Date | null;
  endTime: Date | null;
}

// ─── Paginated list queries ─────────────────────────────────────────────────

function mapTaskRow(row: typeof tasks.$inferSelect): TaskRow {
  return {
    name: row.name,
    type: row.type,
    priority: row.priority,
    status: row.status,
    errorMessage: row.errorMessage ?? null,
    devices: (row.devices as Record<string, unknown>) || {},
    inputParameters: row.inputParameters as Record<string, unknown> | null,
    inputResources: row.inputResources as Record<string, unknown> | null,
    outputParameters: row.outputParameters as Record<string, unknown> | null,
    outputResources: row.outputResources as Record<string, unknown> | null,
    outputFileNames: row.outputFileNames as string[] | null,
    allocationTimeout: row.allocationTimeout,
    meta: (row.meta as Record<string, unknown>) || {},
    experimentName: row.experimentName,
    createdAt: row.createdAt,
    startTime: row.startTime,
    endTime: row.endTime,
  };
}

function mapExperimentRow(row: typeof experiments.$inferSelect): ExperimentRow {
  return {
    name: row.name,
    type: row.type,
    campaign: row.campaign,
    owner: row.owner,
    priority: row.priority,
    parameters: (row.parameters as Record<string, Record<string, unknown>>) || {},
    meta: row.meta as Record<string, unknown> | null,
    resume: row.resume,
    status: row.status,
    errorMessage: row.errorMessage ?? null,
    createdAt: row.createdAt,
    startTime: row.startTime,
    endTime: row.endTime,
  };
}

function mapCampaignRow(row: typeof campaigns.$inferSelect): CampaignRow {
  return {
    name: row.name,
    experimentType: row.experimentType,
    owner: row.owner,
    priority: row.priority,
    maxExperiments: row.maxExperiments,
    maxConcurrentExperiments: row.maxConcurrentExperiments,
    optimize: row.optimize,
    optimizerIp: row.optimizerIp,
    globalParameters: row.globalParameters as Record<string, Record<string, unknown>> | null,
    experimentParameters: row.experimentParameters as Array<Record<string, Record<string, unknown>>> | null,
    meta: row.meta as Record<string, unknown> | null,
    resume: row.resume,
    status: row.status,
    errorMessage: row.errorMessage ?? null,
    experimentsCompleted: row.experimentsCompleted,
    paretoSolutions: row.paretoSolutions as Array<Record<string, unknown>> | null,
    createdAt: row.createdAt,
    startTime: row.startTime,
    endTime: row.endTime,
  };
}

export async function getAllTasks(options: TableQueryOptions = {}): Promise<PaginatedResult<TaskRow>> {
  const { rows, total, limit, offset } = await queryPaginated(
    tasks,
    options,
    TASK_COLUMNS,
    TASK_SEARCH_COLUMNS,
    tasks.createdAt
  );
  return { data: rows.map(mapTaskRow), total, limit, offset };
}

export async function getAllExperiments(options: TableQueryOptions = {}): Promise<PaginatedResult<ExperimentRow>> {
  const { rows, total, limit, offset } = await queryPaginated(
    experiments,
    options,
    EXPERIMENT_COLUMNS,
    EXPERIMENT_SEARCH_COLUMNS,
    experiments.createdAt
  );
  return { data: rows.map(mapExperimentRow), total, limit, offset };
}

export async function getAllCampaigns(options: TableQueryOptions = {}): Promise<PaginatedResult<CampaignRow>> {
  const { rows, total, limit, offset } = await queryPaginated(
    campaigns,
    options,
    CAMPAIGN_COLUMNS,
    CAMPAIGN_SEARCH_COLUMNS,
    campaigns.createdAt
  );
  return { data: rows.map(mapCampaignRow), total, limit, offset };
}

// ─── Name prefix query (for clone name generation) ──────────────────────────

const TABLE_REFS = { campaigns, experiments, tasks } as const;

export async function getNamesByPrefix(
  table: 'campaigns' | 'experiments' | 'tasks',
  prefix: string
): Promise<string[]> {
  const tableRef = TABLE_REFS[table];
  const results = await db
    .select({ name: tableRef.name })
    .from(tableRef)
    .where(ilike(tableRef.name, `${prefix}%`));
  return results.map((r) => r.name);
}

// ─── Single-entity and relationship queries ─────────────────────────────────

export async function getExperimentByName(name: string): Promise<ExperimentRow | null> {
  const result = await db.select().from(experiments).where(eq(experiments.name, name)).limit(1);
  return result.length === 0 ? null : mapExperimentRow(result[0]);
}

export async function getTasksByExperiment(experimentName: string): Promise<TaskRow[]> {
  const results = await db
    .select()
    .from(tasks)
    .where(eq(tasks.experimentName, experimentName))
    .orderBy(desc(tasks.createdAt));
  return results.map(mapTaskRow);
}

export interface TaskStatusRow {
  name: string;
  type: string;
  status: string;
}

export async function getTaskStatusesByExperiment(experimentName: string): Promise<TaskStatusRow[]> {
  return db
    .select({ name: tasks.name, type: tasks.type, status: tasks.status })
    .from(tasks)
    .where(eq(tasks.experimentName, experimentName));
}

export async function getTaskByName(taskName: string, experimentName: string): Promise<TaskRow | null> {
  const result = await db
    .select()
    .from(tasks)
    .where(and(eq(tasks.name, taskName), eq(tasks.experimentName, experimentName)))
    .limit(1);
  return result.length === 0 ? null : mapTaskRow(result[0]);
}

export interface CampaignSampleRow {
  campaignName: string;
  experimentName: string;
  inputs: Record<string, number>;
  outputs: Record<string, number>;
  meta: Record<string, unknown>;
  createdAt: Date;
}

export async function getCampaignByName(name: string): Promise<CampaignRow | null> {
  const result = await db.select().from(campaigns).where(eq(campaigns.name, name)).limit(1);
  return result.length === 0 ? null : mapCampaignRow(result[0]);
}

export async function getCampaignSamples(campaignName: string): Promise<CampaignSampleRow[]> {
  const results = await db
    .select()
    .from(campaignSamples)
    .where(eq(campaignSamples.campaignName, campaignName))
    .orderBy(asc(campaignSamples.createdAt));

  return results.map((row) => ({
    campaignName: row.campaignName,
    experimentName: row.experimentName,
    inputs: row.inputs as Record<string, number>,
    outputs: row.outputs as Record<string, number>,
    meta: (row.meta as Record<string, unknown>) || {},
    createdAt: row.createdAt,
  }));
}

export async function getExperimentsByOwner(owner: string): Promise<ExperimentRow[]> {
  const results = await db
    .select()
    .from(experiments)
    .where(eq(experiments.owner, owner))
    .orderBy(desc(experiments.createdAt));
  return results.map(mapExperimentRow);
}

export async function getExperimentsByCampaign(campaignName: string): Promise<ExperimentRow[]> {
  const results = await db
    .select()
    .from(experiments)
    .where(eq(experiments.campaign, campaignName))
    .orderBy(desc(experiments.createdAt));
  return results.map(mapExperimentRow);
}
