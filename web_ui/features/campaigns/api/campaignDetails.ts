'use server';

import {
  getCampaignByName,
  getCampaignSamples,
  getProtocolRunsByCampaign,
  CampaignRow,
  CampaignSampleRow,
  ProtocolRunRow,
} from '@/lib/db/queries';
import type { Campaign, ProtocolRun } from '@/lib/types/api';

export interface CampaignSample {
  campaignName: string;
  protocolRunName: string;
  inputs: Record<string, number>;
  outputs: Record<string, number>;
  meta: Record<string, unknown>;
  createdAt: string;
}

function transformDbCampaign(row: CampaignRow): Campaign {
  return {
    name: row.name,
    protocol: row.protocol,
    owner: row.owner,
    priority: row.priority,
    max_protocol_runs: row.maxProtocolRuns,
    max_concurrent_protocol_runs: row.maxConcurrentProtocolRuns,
    optimize: row.optimize,
    optimizer_ip: row.optimizerIp ?? undefined,
    global_parameters: row.globalParameters,
    protocol_run_parameters: row.protocolRunParameters,
    meta: row.meta || {},
    resume: row.resume,
    status: row.status as Campaign['status'],
    error_message: row.errorMessage ?? null,
    protocol_runs_completed: row.protocolRunsCompleted,
    pareto_solutions: row.paretoSolutions,
    created_at: row.createdAt.toISOString(),
    start_time: row.startTime?.toISOString() ?? null,
    end_time: row.endTime?.toISOString() ?? null,
  };
}

function transformDbSample(row: CampaignSampleRow): CampaignSample {
  return {
    campaignName: row.campaignName,
    protocolRunName: row.protocolRunName,
    inputs: row.inputs,
    outputs: row.outputs,
    meta: row.meta,
    createdAt: row.createdAt.toISOString(),
  };
}

function transformDbProtocolRun(exp: ProtocolRunRow): ProtocolRun {
  return {
    name: exp.name,
    type: exp.type,
    campaign: exp.campaign,
    owner: exp.owner,
    priority: exp.priority,
    parameters: exp.parameters || {},
    meta: exp.meta ?? null,
    resume: exp.resume,
    status: exp.status as ProtocolRun['status'],
    error_message: exp.errorMessage ?? null,
    created_at: exp.createdAt.toISOString(),
    start_time: exp.startTime?.toISOString() ?? null,
    end_time: exp.endTime?.toISOString() ?? null,
  };
}

export async function getCampaignDetails(campaignName: string): Promise<Campaign | null> {
  try {
    const campaignRow = await getCampaignByName(campaignName);
    if (!campaignRow) return null;
    return transformDbCampaign(campaignRow);
  } catch (error) {
    console.error('Failed to fetch campaign details:', error);
    throw new Error('Failed to fetch campaign details');
  }
}

export async function getCampaignOptimizationSamples(campaignName: string): Promise<CampaignSample[]> {
  try {
    const sampleRows = await getCampaignSamples(campaignName);
    return sampleRows.map(transformDbSample);
  } catch (error) {
    console.error('Failed to fetch campaign samples:', error);
    throw new Error('Failed to fetch campaign samples');
  }
}

export async function getCampaignProtocolRuns(campaignName: string): Promise<ProtocolRun[]> {
  try {
    const protocolRunRows = await getProtocolRunsByCampaign(campaignName);
    return protocolRunRows.map(transformDbProtocolRun);
  } catch (error) {
    console.error('Failed to fetch campaign protocol runs:', error);
    throw new Error('Failed to fetch campaign protocol runs');
  }
}

export async function getCampaignWithDetails(campaignName: string): Promise<{
  campaign: Campaign | null;
  samples: CampaignSample[];
  protocolRuns: ProtocolRun[];
}> {
  try {
    const [campaignRow, sampleRows, protocolRunRows] = await Promise.all([
      getCampaignByName(campaignName),
      getCampaignSamples(campaignName),
      getProtocolRunsByCampaign(campaignName),
    ]);

    if (!campaignRow) {
      return { campaign: null, samples: [], protocolRuns: [] };
    }

    return {
      campaign: transformDbCampaign(campaignRow),
      samples: sampleRows.map(transformDbSample),
      protocolRuns: protocolRunRows.map(transformDbProtocolRun),
    };
  } catch (error) {
    console.error('Failed to fetch campaign with details:', error);
    throw new Error('Failed to fetch campaign with details');
  }
}
