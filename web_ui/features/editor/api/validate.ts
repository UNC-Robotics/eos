'use server';

/**
 * Server Action for protocol validation.
 */

import { orchestratorPost } from '@/lib/api/orchestrator';
import { requireRole } from '@/lib/auth/authz';

export interface ValidationResponse {
  valid: boolean;
  errors: Array<{ task: string | null; message: string }>;
}

/** Validate a serialized protocol via the orchestrator's /protocols/validate endpoint. */
export async function validateProtocol(protocolYaml: string): Promise<ValidationResponse> {
  await requireRole('EDITOR');
  const result = (await orchestratorPost('/protocols/validate', { protocol_yaml: protocolYaml })) as ValidationResponse;
  return { valid: result.valid, errors: result.errors ?? [] };
}
