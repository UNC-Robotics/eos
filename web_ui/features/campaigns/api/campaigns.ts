'use server';

/**
 * Server Actions for Campaigns
 *
 * Note: GET operations read from database, POST operations go to orchestrator API
 */

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import type { Campaign, CampaignDefinition, ActionResult } from '@/lib/types/api';
import { DEFAULT_PAGE_SIZE, type TableQueryOptions } from '@/lib/types/table';
import { getAllCampaigns, type PaginatedResult } from '@/lib/db/queries';

export async function getCampaigns(options: TableQueryOptions = {}): Promise<PaginatedResult<Campaign>> {
  try {
    const result = await getAllCampaigns({ limit: DEFAULT_PAGE_SIZE, offset: 0, ...options });

    return {
      data: result.data.map((campaign) => ({
        name: campaign.name,
        experiment_type: campaign.experimentType,
        owner: campaign.owner,
        priority: campaign.priority,
        max_experiments: campaign.maxExperiments,
        max_concurrent_experiments: campaign.maxConcurrentExperiments,
        optimize: campaign.optimize,
        optimizer_ip: campaign.optimizerIp ?? undefined,
        global_parameters: campaign.globalParameters,
        experiment_parameters: campaign.experimentParameters,
        meta: campaign.meta || {},
        resume: campaign.resume,
        status: campaign.status as Campaign['status'],
        experiments_completed: campaign.experimentsCompleted,
        pareto_solutions: campaign.paretoSolutions,
        created_at: campaign.createdAt.toISOString(),
        start_time: campaign.startTime?.toISOString() ?? null,
        end_time: campaign.endTime?.toISOString() ?? null,
      })),
      total: result.total,
      limit: result.limit,
      offset: result.offset,
    };
  } catch (error) {
    console.error('Failed to fetch campaigns:', error);
    throw new Error('Failed to fetch campaigns from database');
  }
}

export async function submitCampaign(definition: CampaignDefinition): Promise<ActionResult> {
  try {
    await orchestratorPost('/campaigns/', definition);
    revalidatePath('/campaigns');
    return { success: true };
  } catch (error) {
    console.error('Failed to submit campaign:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to submit campaign',
    };
  }
}

export async function cancelCampaign(campaignName: string): Promise<ActionResult> {
  try {
    await orchestratorPost(`/campaigns/${campaignName}/cancel`);
    revalidatePath('/campaigns');
    return { success: true };
  } catch (error) {
    console.error('Failed to cancel campaign:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to cancel campaign',
    };
  }
}
