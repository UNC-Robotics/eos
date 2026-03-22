import type { DomainValue } from '../components/DomainEditor';
import type { OptimizerInfo } from '@/lib/types/api';

/** Dig into campaign.meta.beacon.optimizer_config.constructor_args to extract the domain. */
export function extractBeaconDomain(meta: unknown): DomainValue | null {
  const beacon = (meta as Record<string, unknown> | undefined)?.beacon as Record<string, unknown> | undefined;
  const config = beacon?.optimizer_config as Record<string, unknown> | undefined;
  const args = config?.constructor_args as Record<string, unknown> | undefined;
  if (!args) return null;
  return {
    inputs: (args.inputs ?? []) as DomainValue['inputs'],
    outputs: (args.outputs ?? []) as DomainValue['outputs'],
    constraints: (args.constraints ?? []) as DomainValue['constraints'],
  };
}

/** Build an OptimizerInfo from persisted campaign.meta.beacon for non-running campaigns. */
export function extractBeaconInfo(meta: unknown): OptimizerInfo | null {
  const beacon = (meta as Record<string, unknown> | undefined)?.beacon as Record<string, unknown> | undefined;
  if (!beacon) return null;

  const config = beacon.optimizer_config as Record<string, unknown> | undefined;
  const optimizerType = config?.optimizer_type as string | undefined;
  if (!optimizerType) return null;

  const args = config?.constructor_args as Record<string, unknown> | undefined;
  // Prefer persisted runtime_params (updated on every save) over constructor_args (initial values)
  const runtimeParams = beacon?.runtime_params as Record<string, unknown> | undefined;
  return {
    optimizer_type: optimizerType,
    runtime_params: {
      p_bayesian: ((runtimeParams?.p_bayesian ?? args?.p_bayesian) as number) ?? 0.5,
      p_ai: ((runtimeParams?.p_ai ?? args?.p_ai) as number) ?? 0.5,
      ai_history_size: ((runtimeParams?.ai_history_size ?? args?.ai_history_size) as number) ?? 50,
      ai_additional_context: ((runtimeParams?.ai_additional_context ?? args?.ai_additional_context) as string) ?? null,
    },
    insights: (beacon.insights as string[]) ?? [],
    journal: (beacon.journal as string[]) ?? [],
  };
}
