'use server';

import {
  getCampaignByName,
  getCampaignSamples,
  getExperimentsByCampaign,
  CampaignRow,
  CampaignSampleRow,
  ExperimentRow,
} from '@/lib/db/queries';
import type { Campaign, Experiment } from '@/lib/types/api';

export interface CampaignSample {
  campaignName: string;
  experimentName: string;
  inputs: Record<string, number>;
  outputs: Record<string, number>;
  meta: Record<string, unknown>;
  createdAt: string;
}

function transformDbCampaign(row: CampaignRow): Campaign {
  return {
    name: row.name,
    experiment_type: row.experimentType,
    owner: row.owner,
    priority: row.priority,
    max_experiments: row.maxExperiments,
    max_concurrent_experiments: row.maxConcurrentExperiments,
    optimize: row.optimize,
    optimizer_ip: row.optimizerIp ?? undefined,
    global_parameters: row.globalParameters,
    experiment_parameters: row.experimentParameters,
    meta: row.meta || {},
    resume: row.resume,
    status: row.status as Campaign['status'],
    error_message: row.errorMessage ?? null,
    experiments_completed: row.experimentsCompleted,
    pareto_solutions: row.paretoSolutions,
    created_at: row.createdAt.toISOString(),
    start_time: row.startTime?.toISOString() ?? null,
    end_time: row.endTime?.toISOString() ?? null,
  };
}

function transformDbSample(row: CampaignSampleRow): CampaignSample {
  return {
    campaignName: row.campaignName,
    experimentName: row.experimentName,
    inputs: row.inputs,
    outputs: row.outputs,
    meta: row.meta,
    createdAt: row.createdAt.toISOString(),
  };
}

function transformDbExperiment(exp: ExperimentRow): Experiment {
  return {
    name: exp.name,
    type: exp.type,
    campaign: exp.campaign,
    owner: exp.owner,
    priority: exp.priority,
    parameters: exp.parameters || {},
    meta: exp.meta ?? null,
    resume: exp.resume,
    status: exp.status as Experiment['status'],
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

export async function getCampaignExperiments(campaignName: string): Promise<Experiment[]> {
  try {
    const experimentRows = await getExperimentsByCampaign(campaignName);
    return experimentRows.map(transformDbExperiment);
  } catch (error) {
    console.error('Failed to fetch campaign experiments:', error);
    throw new Error('Failed to fetch campaign experiments');
  }
}

export async function getCampaignWithDetails(campaignName: string): Promise<{
  campaign: Campaign | null;
  samples: CampaignSample[];
  experiments: Experiment[];
}> {
  try {
    const [campaignRow, sampleRows, experimentRows] = await Promise.all([
      getCampaignByName(campaignName),
      getCampaignSamples(campaignName),
      getExperimentsByCampaign(campaignName),
    ]);

    if (!campaignRow) {
      return { campaign: null, samples: [], experiments: [] };
    }

    return {
      campaign: transformDbCampaign(campaignRow),
      samples: sampleRows.map(transformDbSample),
      experiments: experimentRows.map(transformDbExperiment),
    };
  } catch (error) {
    console.error('Failed to fetch campaign with details:', error);
    throw new Error('Failed to fetch campaign with details');
  }
}
