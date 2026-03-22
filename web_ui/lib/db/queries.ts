/**
 * Database Query Functions
 *
 * These functions query the EOS database for tasks, experiments, and campaigns.
 * Implements server-side pagination for efficient data fetching.
 */

import { desc, count, eq, and, asc } from 'drizzle-orm';
import { db } from './client';
import { tasks, experiments, campaigns, campaignSamples } from './schema';

// Pagination options
export interface PaginationOptions {
  limit?: number;
  offset?: number;
}

// Paginated result wrapper
export interface PaginatedResult<T> {
  data: T[];
  total: number;
  limit: number;
  offset: number;
}

// Database row types (matching database schema)
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

/**
 * Get tasks from the database with pagination
 */
export async function getAllTasks(options: PaginationOptions = {}): Promise<PaginatedResult<TaskRow>> {
  const { limit = 50, offset = 0 } = options;

  // Execute queries in parallel for better performance
  const [results, [{ value: total }]] = await Promise.all([
    db.select().from(tasks).orderBy(desc(tasks.createdAt)).limit(limit).offset(offset),
    db.select({ value: count() }).from(tasks),
  ]);

  return {
    data: results.map((row) => ({
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
    })),
    total,
    limit,
    offset,
  };
}

/**
 * Get experiments from the database with pagination
 */
export async function getAllExperiments(options: PaginationOptions = {}): Promise<PaginatedResult<ExperimentRow>> {
  const { limit = 50, offset = 0 } = options;

  // Execute queries in parallel for better performance
  const [results, [{ value: total }]] = await Promise.all([
    db.select().from(experiments).orderBy(desc(experiments.createdAt)).limit(limit).offset(offset),
    db.select({ value: count() }).from(experiments),
  ]);

  return {
    data: results.map((row) => ({
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
    })),
    total,
    limit,
    offset,
  };
}

/**
 * Get campaigns from the database with pagination
 */
export async function getAllCampaigns(options: PaginationOptions = {}): Promise<PaginatedResult<CampaignRow>> {
  const { limit = 50, offset = 0 } = options;

  // Execute queries in parallel for better performance
  const [results, [{ value: total }]] = await Promise.all([
    db.select().from(campaigns).orderBy(desc(campaigns.createdAt)).limit(limit).offset(offset),
    db.select({ value: count() }).from(campaigns),
  ]);

  return {
    data: results.map((row) => ({
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
    })),
    total,
    limit,
    offset,
  };
}

/**
 * Get a single experiment by name
 */
export async function getExperimentByName(name: string): Promise<ExperimentRow | null> {
  const result = await db.select().from(experiments).where(eq(experiments.name, name)).limit(1);

  if (result.length === 0) {
    return null;
  }

  const row = result[0];
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

/**
 * Get all tasks for a specific experiment
 */
export async function getTasksByExperiment(experimentName: string): Promise<TaskRow[]> {
  const results = await db
    .select()
    .from(tasks)
    .where(eq(tasks.experimentName, experimentName))
    .orderBy(desc(tasks.createdAt));

  return results.map((row) => ({
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
  }));
}

// Lightweight task status for canvas display
export interface TaskStatusRow {
  name: string;
  type: string;
  status: string;
}

/**
 * Get lightweight task statuses for an experiment (for canvas display)
 */
export async function getTaskStatusesByExperiment(experimentName: string): Promise<TaskStatusRow[]> {
  const results = await db
    .select({
      name: tasks.name,
      type: tasks.type,
      status: tasks.status,
    })
    .from(tasks)
    .where(eq(tasks.experimentName, experimentName));

  return results;
}

/**
 * Get a single task by name and experiment name
 */
export async function getTaskByName(taskName: string, experimentName: string): Promise<TaskRow | null> {
  const result = await db
    .select()
    .from(tasks)
    .where(and(eq(tasks.name, taskName), eq(tasks.experimentName, experimentName)))
    .limit(1);

  if (result.length === 0) {
    return null;
  }

  const row = result[0];
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

// Campaign sample row type
export interface CampaignSampleRow {
  campaignName: string;
  experimentName: string;
  inputs: Record<string, number>;
  outputs: Record<string, number>;
  meta: Record<string, unknown>;
  createdAt: Date;
}

/**
 * Get a single campaign by name
 */
export async function getCampaignByName(name: string): Promise<CampaignRow | null> {
  const result = await db.select().from(campaigns).where(eq(campaigns.name, name)).limit(1);

  if (result.length === 0) {
    return null;
  }

  const row = result[0];
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

/**
 * Get campaign samples for optimization tracking
 */
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

/**
 * Get experiments by owner
 */
export async function getExperimentsByOwner(owner: string): Promise<ExperimentRow[]> {
  const results = await db
    .select()
    .from(experiments)
    .where(eq(experiments.owner, owner))
    .orderBy(desc(experiments.createdAt));

  return results.map((row) => ({
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
  }));
}

/**
 * Get experiments by campaign name
 */
export async function getExperimentsByCampaign(campaignName: string): Promise<ExperimentRow[]> {
  const results = await db
    .select()
    .from(experiments)
    .where(eq(experiments.campaign, campaignName))
    .orderBy(desc(experiments.createdAt));

  return results.map((row) => ({
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
  }));
}
