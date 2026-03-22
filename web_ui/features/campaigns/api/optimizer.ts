'use server';

import { orchestratorGet, orchestratorPost, orchestratorPut } from '@/lib/api/orchestrator';
import type { OptimizerDefaults, OptimizerInfo, ActionResult } from '@/lib/types/api';

/**
 * Get default optimizer parameters for an experiment type.
 * Returns null if no optimizer is configured.
 */
export async function getOptimizerDefaults(experimentType: string): Promise<OptimizerDefaults | null> {
  try {
    const result = await orchestratorGet(`/campaigns/optimizer/defaults/${experimentType}`);
    return result as OptimizerDefaults;
  } catch {
    return null;
  }
}

/**
 * Get current optimizer info for a running campaign.
 * Returns null if campaign is not running or has no optimizer.
 */
export async function getOptimizerInfo(campaignName: string): Promise<OptimizerInfo | null> {
  try {
    const result = (await orchestratorGet(`/campaigns/${campaignName}/optimizer/info`)) as Record<string, unknown>;
    if (result.status === 'initializing') return null;
    return result as unknown as OptimizerInfo;
  } catch {
    return null;
  }
}

/**
 * Update runtime-safe optimizer parameters for a running campaign.
 */
export async function updateOptimizerParams(
  campaignName: string,
  params: { p_bayesian?: number; ai_history_size?: number; ai_additional_context?: string }
): Promise<ActionResult> {
  try {
    await orchestratorPut(`/campaigns/${campaignName}/optimizer/params`, params);
    return { success: true };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to update optimizer parameters',
    };
  }
}

/**
 * Add an expert insight to a campaign's optimizer.
 */
export async function addOptimizerInsight(campaignName: string, insight: string): Promise<ActionResult> {
  try {
    await orchestratorPost(`/campaigns/${campaignName}/optimizer/insight`, { insight });
    return { success: true };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to add insight',
    };
  }
}
