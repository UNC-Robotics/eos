import type { DomainValue } from '../components/DomainEditor';
import type { OptimizerInfo, OptimizerParamSpec } from '@/lib/types/api';

/** Dig into campaign.meta.optimizer.optimizer_config.constructor_args to extract the domain. */
export function extractOptimizerDomain(meta: unknown): DomainValue | null {
  const optimizer = (meta as Record<string, unknown> | undefined)?.optimizer as Record<string, unknown> | undefined;
  const config = optimizer?.optimizer_config as Record<string, unknown> | undefined;
  const args = config?.constructor_args as Record<string, unknown> | undefined;
  if (!args) return null;
  return {
    inputs: (args.inputs ?? []) as DomainValue['inputs'],
    outputs: (args.outputs ?? []) as DomainValue['outputs'],
    constraints: (args.constraints ?? []) as DomainValue['constraints'],
  };
}

/** Build an OptimizerInfo from persisted campaign.meta.optimizer for non-running campaigns. */
export function extractOptimizerInfo(meta: unknown): OptimizerInfo | null {
  const optimizer = (meta as Record<string, unknown> | undefined)?.optimizer as Record<string, unknown> | undefined;
  if (!optimizer) return null;

  const config = optimizer.optimizer_config as Record<string, unknown> | undefined;
  const optimizerType = config?.optimizer_type as string | undefined;
  if (!optimizerType) return null;

  const args = config?.constructor_args as Record<string, unknown> | undefined;
  // Prefer persisted runtime_params (updated on every save) over constructor_args (initial values)
  const runtimeParams = optimizer?.runtime_params as Record<string, unknown> | undefined;
  return {
    optimizer_type: optimizerType,
    is_beacon: (config?.is_beacon as boolean) ?? false,
    param_schema: (config?.param_schema as OptimizerParamSpec[]) ?? [],
    runtime_params: {
      ...args,
      ...runtimeParams,
      p_bayesian: ((runtimeParams?.p_bayesian ?? args?.p_bayesian) as number) ?? 0.5,
      p_ai: ((runtimeParams?.p_ai ?? args?.p_ai) as number) ?? 0.5,
      ai_history_size: ((runtimeParams?.ai_history_size ?? args?.ai_history_size) as number) ?? 50,
      ai_additional_context: ((runtimeParams?.ai_additional_context ?? args?.ai_additional_context) as string) ?? null,
    },
    insights: (optimizer.insights as string[]) ?? [],
    journal: (optimizer.journal as string[]) ?? [],
  };
}
