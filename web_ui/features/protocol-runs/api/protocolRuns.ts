'use server';

import { revalidatePath } from 'next/cache';
import { orchestratorPost } from '@/lib/api/orchestrator';
import type { ProtocolRun, ProtocolRunDefinition, ActionResult } from '@/lib/types/api';
import { DEFAULT_PAGE_SIZE, type TableQueryOptions } from '@/lib/types/table';
import { getAllProtocolRuns, type PaginatedResult } from '@/lib/db/queries';
import { createSuccessResult, createErrorResult } from '@/lib/utils/protocolHelpers';

function transformDbProtocolRun(exp: unknown): ProtocolRun {
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
    status: e.status as ProtocolRun['status'],
    created_at: e.createdAt.toISOString(),
    start_time: e.startTime?.toISOString() ?? null,
    end_time: e.endTime?.toISOString() ?? null,
  };
}

export async function getProtocolRuns(options: TableQueryOptions = {}): Promise<PaginatedResult<ProtocolRun>> {
  try {
    const result = await getAllProtocolRuns({ limit: DEFAULT_PAGE_SIZE, offset: 0, ...options });
    return {
      data: result.data.map(transformDbProtocolRun),
      total: result.total,
      limit: result.limit,
      offset: result.offset,
    };
  } catch (error) {
    console.error('Failed to fetch protocol runs:', error);
    throw new Error('Failed to fetch protocol runs from database');
  }
}

export async function submitProtocolRun(definition: ProtocolRunDefinition): Promise<ActionResult> {
  try {
    await orchestratorPost('/protocols/', definition);
    revalidatePath('/protocol-runs');
    return createSuccessResult();
  } catch (error) {
    console.error('Failed to submit protocol run:', error);
    return createErrorResult(error, 'Failed to submit protocol run');
  }
}

export async function cancelProtocolRun(protocolRunName: string): Promise<ActionResult> {
  try {
    await orchestratorPost(`/protocols/${protocolRunName}/cancel`);
    revalidatePath('/protocol-runs');
    return createSuccessResult();
  } catch (error) {
    console.error('Failed to cancel protocol run:', error);
    return createErrorResult(error, 'Failed to cancel protocol run');
  }
}
