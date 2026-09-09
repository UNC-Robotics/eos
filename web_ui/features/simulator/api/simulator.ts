'use server';

import { orchestratorGet, orchestratorPost } from '@/lib/api/orchestrator';
import { requireRole } from '@/lib/auth/authz';
import type { SimConfig, SimResults } from '../types';

export async function runSimulation(config: SimConfig): Promise<SimResults> {
  await requireRole('LAB_ADMIN');
  return (await orchestratorPost('/simulator/run', config)) as SimResults;
}

export async function fetchPackages(): Promise<Record<string, boolean>> {
  return (await orchestratorGet('/packages/')) as Record<string, boolean>;
}

export async function fetchProtocolTypes(): Promise<Record<string, boolean>> {
  return (await orchestratorGet('/protocols/types')) as Record<string, boolean>;
}
