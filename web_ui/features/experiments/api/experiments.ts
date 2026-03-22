'use server';

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import type { Experiment, ExperimentDefinition, ActionResult } from '@/lib/types/api';
import { getAllExperiments } from '@/lib/db/queries';
import { createSuccessResult, createErrorResult } from '@/lib/utils/experimentHelpers';

function transformDbExperiment(exp: unknown): Experiment {
  const e = exp as {
    name: string;
    type: string;
    campaign?: string | null;
    owner: string;
    priority: number;
    parameters?: Record<string, unknown>;
    meta: unknown;
    resume: boolean;
    status: string;
    createdAt: Date;
    startTime?: Date;
    endTime?: Date;
    progress?: number;
  };
  return {
    name: e.name,
    type: e.type,
    campaign: e.campaign ?? null,
    owner: e.owner,
    priority: e.priority,
    parameters: (e.parameters as Record<string, Record<string, unknown>>) || {},
    meta: (e.meta as Record<string, unknown> | null | undefined) ?? null,
    resume: e.resume,
    status: e.status as Experiment['status'],
    created_at: e.createdAt.toISOString(),
    start_time: e.startTime?.toISOString() ?? null,
    end_time: e.endTime?.toISOString() ?? null,
  };
}

export async function getExperiments(): Promise<Experiment[]> {
  try {
    const result = await getAllExperiments({ limit: 100, offset: 0 });
    return result.data.map(transformDbExperiment);
  } catch (error) {
    console.error('Failed to fetch experiments:', error);
    throw new Error('Failed to fetch experiments from database');
  }
}

export async function submitExperiment(definition: ExperimentDefinition): Promise<ActionResult> {
  try {
    await orchestratorPost('/experiments/', definition);
    revalidatePath('/experiments');
    return createSuccessResult();
  } catch (error) {
    console.error('Failed to submit experiment:', error);
    return createErrorResult(error, 'Failed to submit experiment');
  }
}

export async function cancelExperiment(experimentName: string): Promise<ActionResult> {
  try {
    await orchestratorPost(`/experiments/${experimentName}/cancel`);
    revalidatePath('/experiments');
    return createSuccessResult();
  } catch (error) {
    console.error('Failed to cancel experiment:', error);
    return createErrorResult(error, 'Failed to cancel experiment');
  }
}
