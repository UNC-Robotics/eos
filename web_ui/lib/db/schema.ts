/**
 * Drizzle ORM Schema for EOS Database
 */

import { pgTable, text, integer, json, timestamp, index, boolean, serial, primaryKey } from 'drizzle-orm/pg-core';

// ============================================================================
// Tasks Table
// ============================================================================
export const tasks = pgTable(
  'tasks',
  {
    id: serial('id').primaryKey(),
    name: text('name').notNull(),
    experimentName: text('experiment_name'),
    type: text('type').notNull(),
    devices: json('devices').notNull().default({}),
    inputParameters: json('input_parameters'),
    inputResources: json('input_resources'),
    outputParameters: json('output_parameters'),
    outputResources: json('output_resources'),
    outputFileNames: json('output_file_names'),
    priority: integer('priority').notNull().default(0),
    allocationTimeout: integer('allocation_timeout').notNull().default(600),
    meta: json('meta').notNull().default({}),
    status: text('status').notNull().default('CREATED'),
    errorMessage: text('error_message'),
    startTime: timestamp('start_time', { withTimezone: true }),
    endTime: timestamp('end_time', { withTimezone: true }),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    experimentNameTaskNameIdx: index('idx_experiment_name_task_name').on(table.experimentName, table.name),
    createdAtIdx: index('ix_tasks_created_at').on(table.createdAt),
  })
);

// ============================================================================
// Experiments Table
// ============================================================================
export const experiments = pgTable(
  'experiments',
  {
    id: serial('id').primaryKey(),
    name: text('name').notNull().unique(),
    type: text('type').notNull(),
    campaign: text('campaign').references(() => campaigns.name, { onDelete: 'cascade' }),
    owner: text('owner').notNull(),
    priority: integer('priority').notNull().default(0),
    parameters: json('parameters').notNull().default({}),
    meta: json('meta'),
    resume: boolean('resume').notNull().default(false),
    status: text('status').notNull().default('CREATED'),
    errorMessage: text('error_message'),
    startTime: timestamp('start_time', { withTimezone: true }),
    endTime: timestamp('end_time', { withTimezone: true }),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    ownerIdx: index('ix_experiments_owner').on(table.owner),
    createdAtIdx: index('ix_experiments_created_at').on(table.createdAt),
  })
);

// ============================================================================
// Campaigns Table
// ============================================================================
export const campaigns = pgTable(
  'campaigns',
  {
    id: serial('id').primaryKey(),
    name: text('name').notNull().unique(),
    experimentType: text('experiment_type').notNull(),
    owner: text('owner').notNull(),
    priority: integer('priority').notNull().default(0),
    maxExperiments: integer('max_experiments').notNull().default(0),
    maxConcurrentExperiments: integer('max_concurrent_experiments').notNull().default(1),
    optimize: boolean('optimize').notNull(),
    optimizerIp: text('optimizer_ip').notNull().default('127.0.0.1'),
    globalParameters: json('global_parameters'),
    experimentParameters: json('experiment_parameters'),
    meta: json('meta').notNull().default({}),
    resume: boolean('resume').notNull().default(false),
    status: text('status').notNull().default('CREATED'),
    errorMessage: text('error_message'),
    experimentsCompleted: integer('experiments_completed').notNull().default(0),
    paretoSolutions: json('pareto_solutions'),
    startTime: timestamp('start_time', { withTimezone: true }),
    endTime: timestamp('end_time', { withTimezone: true }),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    ownerIdx: index('ix_campaigns_owner').on(table.owner),
    createdAtIdx: index('ix_campaigns_created_at').on(table.createdAt),
  })
);

// ============================================================================
// Campaign Samples Table
// ============================================================================
export const campaignSamples = pgTable(
  'campaign_samples',
  {
    campaignName: text('campaign_name')
      .notNull()
      .references(() => campaigns.name, { onDelete: 'cascade' }),
    experimentName: text('experiment_name')
      .notNull()
      .references(() => experiments.name, { onDelete: 'cascade' }),
    inputs: json('inputs').notNull(),
    outputs: json('outputs').notNull(),
    meta: json('meta').notNull().default({}),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.campaignName, table.experimentName] }),
  })
);

// ============================================================================
// Resources Table
// ============================================================================
export const resources = pgTable(
  'resources',
  {
    name: text('name').notNull().primaryKey(),
    type: text('type').notNull(),
    lab: text('lab'),
    meta: json('meta').notNull().default({}),
  },
  (table) => ({
    labIdx: index('ix_resources_lab').on(table.lab),
  })
);

// ============================================================================
// Devices Table
// ============================================================================
export const devices = pgTable(
  'devices',
  {
    labName: text('lab_name').notNull(),
    name: text('name').notNull(),
    type: text('type').notNull(),
    computer: text('computer').notNull(),
    status: text('status').notNull().default('ACTIVE'),
    meta: json('meta').notNull().default({}),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.labName, table.name] }),
  })
);

// ============================================================================
// Allocation Requests Table
// ============================================================================
export const allocationRequests = pgTable(
  'allocation_requests',
  {
    id: serial('id').primaryKey(),
    requester: text('requester').notNull(),
    experimentName: text('experiment_name').references(() => experiments.name, { onDelete: 'cascade' }),
    priority: integer('priority').notNull().default(0),
    timeout: integer('timeout').notNull().default(600),
    reason: text('reason'),
    status: text('status').notNull().default('PENDING'),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    allocatedAt: timestamp('allocated_at', { withTimezone: true }),
  },
  (table) => ({
    requesterIdx: index('idx_allocation_requests_requester').on(table.requester),
    experimentNameIdx: index('idx_allocation_requests_experiment_name').on(table.experimentName),
    statusIdx: index('idx_allocation_requests_status').on(table.status),
  })
);

// ============================================================================
// Device Allocations Table
// ============================================================================
export const deviceAllocations = pgTable(
  'device_allocations',
  {
    labName: text('lab_name').notNull(),
    name: text('name').notNull(),
    owner: text('owner').notNull(),
    experimentName: text('experiment_name').references(() => experiments.name, { onDelete: 'cascade' }),
    held: boolean('held').notNull().default(false),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.labName, table.name] }),
    experimentNameIdx: index('ix_device_allocations_experiment_name').on(table.experimentName),
  })
);

// ============================================================================
// Resource Allocations Table
// ============================================================================
export const resourceAllocations = pgTable(
  'resource_allocations',
  {
    name: text('name')
      .notNull()
      .primaryKey()
      .references(() => resources.name),
    owner: text('owner').notNull(),
    experimentName: text('experiment_name').references(() => experiments.name, { onDelete: 'cascade' }),
    held: boolean('held').notNull().default(false),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    experimentNameIdx: index('ix_resource_allocations_experiment_name').on(table.experimentName),
  })
);

// ============================================================================
// Definitions Table
// ============================================================================
export const definitions = pgTable(
  'definitions',
  {
    type: text('type').notNull(),
    name: text('name').notNull(),
    data: json('data').notNull(),
    isLoaded: boolean('is_loaded').notNull().default(false),
    packageName: text('package_name').notNull(),
    sourcePath: text('source_path').notNull(),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.type, table.name] }),
    typeIdx: index('idx_definitions_type').on(table.type),
  })
);

// ============================================================================
// Allocation Request Devices Table
// ============================================================================
export const allocationRequestDevices = pgTable(
  'allocation_request_devices',
  {
    requestId: integer('request_id')
      .notNull()
      .references(() => allocationRequests.id, { onDelete: 'cascade' }),
    labName: text('lab_name').notNull(),
    name: text('name').notNull(),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.requestId, table.labName, table.name] }),
    labNameIdx: index('idx_alloc_req_devices_lab_name').on(table.labName),
  })
);

// ============================================================================
// Allocation Request Resources Table
// ============================================================================
export const allocationRequestResources = pgTable(
  'allocation_request_resources',
  {
    requestId: integer('request_id')
      .notNull()
      .references(() => allocationRequests.id, { onDelete: 'cascade' }),
    labName: text('lab_name').notNull(),
    name: text('name').notNull(),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.requestId, table.labName, table.name] }),
    labNameIdx: index('idx_alloc_req_resources_lab_name').on(table.labName),
  })
);
