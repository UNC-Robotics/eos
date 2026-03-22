'use server';

/**
 * Server Actions for Campaigns
 *
 * Note: GET operations read from database, POST operations go to orchestrator API
 */

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import type { Campaign, CampaignDefinition, ActionResult } from '@/lib/types/api';
import { getAllCampaigns } from '@/lib/db/queries';

/**
 * Get campaigns from database with server-side pagination
 * Default limit: 100 campaigns
 */
export async function getCampaigns(): Promise<Campaign[]> {
  try {
    // Fetch with reasonable limit
    const result = await getAllCampaigns({ limit: 100, offset: 0 });

    return result.data.map((campaign) => ({
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
    }));
  } catch (error) {
    console.error('Failed to fetch campaigns:', error);
    throw new Error('Failed to fetch campaigns from database');
  }
}

/**
 * Submit a new campaign
 */
export async function submitCampaign(definition: CampaignDefinition): Promise<ActionResult> {
  try {
    await orchestratorPost('/campaigns/', definition);

    // Revalidate the campaigns page to show the new campaign
    revalidatePath('/campaigns');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to submit campaign:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to submit campaign',
    };
  }
}

/**
 * Cancel a running campaign
 */
export async function cancelCampaign(campaignName: string): Promise<ActionResult> {
  try {
    await orchestratorPost(`/campaigns/${campaignName}/cancel`);

    // Revalidate the campaigns page to show updated status
    revalidatePath('/campaigns');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to cancel campaign:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to cancel campaign',
    };
  }
}
