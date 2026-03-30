/**
 * API Types for EOS Orchestrator
 *
 * These types mirror the Python Pydantic models from the orchestrator API.
 */

// ============================================================================
// Task Types
// ============================================================================

export type TaskStatus = 'CREATED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export interface TaskDeviceConfig {
  lab: string;
  type: string;
}

export interface TaskDefinition {
  name: string;
  type: string;
  protocol_run_name?: string | null;
  devices?: Record<string, TaskDeviceConfig>;
  input_parameters?: Record<string, unknown> | null;
  input_resources?: Record<string, unknown> | null;
  priority?: number;
  allocation_timeout?: number;
  meta?: Record<string, unknown>;
}

export interface Task extends TaskDefinition {
  status: TaskStatus;
  error_message?: string | null;
  output_parameters?: Record<string, unknown> | null;
  output_resources?: Record<string, unknown> | null;
  output_file_names?: string[] | null;
  start_time?: string | null;
  end_time?: string | null;
  created_at: string;
}

// ============================================================================
// ProtocolRun Types
// ============================================================================

export type ProtocolRunStatus = 'CREATED' | 'RUNNING' | 'COMPLETED' | 'SUSPENDED' | 'CANCELLED' | 'FAILED';

export interface ProtocolRunDefinition {
  name: string;
  type: string;
  owner: string;
  priority?: number;
  parameters?: Record<string, Record<string, unknown>>;
  meta?: Record<string, unknown> | null;
  resume?: boolean;
}

export interface ProtocolRun extends ProtocolRunDefinition {
  campaign?: string | null;
  status: ProtocolRunStatus;
  error_message?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  created_at: string;
}

// ============================================================================
// Campaign Types
// ============================================================================

export type CampaignStatus = 'CREATED' | 'RUNNING' | 'COMPLETED' | 'SUSPENDED' | 'CANCELLED' | 'FAILED';

export interface CampaignDefinition {
  name: string;
  protocol: string;
  owner: string;
  priority?: number;
  max_protocol_runs?: number;
  max_concurrent_protocol_runs?: number;
  optimize: boolean;
  optimizer_ip?: string;
  global_parameters?: Record<string, Record<string, unknown>> | null;
  protocol_run_parameters?: Array<Record<string, Record<string, unknown>>> | null;
  meta?: Record<string, unknown>;
  resume?: boolean;
}

export interface Campaign extends CampaignDefinition {
  status: CampaignStatus;
  error_message?: string | null;
  protocol_runs_completed: number;
  pareto_solutions?: Array<Record<string, unknown>> | null;
  start_time?: string | null;
  end_time?: string | null;
  created_at: string;
}

// ============================================================================
// Optimizer Types
// ============================================================================

export interface OptimizerDefaults {
  optimizer_type: string;
  inputs: Record<string, unknown>[];
  outputs: Record<string, unknown>[];
  constraints: Record<string, unknown>[];
  params: {
    p_bayesian: number;
    p_ai: number;
    ai_model: string;
    ai_retries: number;
    ai_history_size: number;
    ai_additional_context: string | null;
    num_initial_samples: number;
    initial_sampling_method: string;
    ai_model_settings: Record<string, unknown> | null;
    ai_additional_parameters: string[] | null;
    acquisition_function: Record<string, unknown> | null;
    surrogate_specs: Record<string, unknown> | null;
  };
}

export interface OptimizerInfo {
  optimizer_type: string;
  runtime_params: {
    p_bayesian: number;
    p_ai: number;
    ai_history_size: number;
    ai_additional_context: string | null;
  };
  insights: string[];
  journal: string[];
}

// ============================================================================
// API Response Types
// ============================================================================

export interface TaskTypesResponse {
  task_types: string[];
}

export interface ProtocolTypesResponse {
  [key: string]: boolean;
}

// ============================================================================
// Error Types
// ============================================================================

export interface ApiError {
  detail: string;
  status_code: number;
}

// ============================================================================
// Action Response Types
// ============================================================================

export interface ActionResult<T = void> {
  success: boolean;
  data?: T;
  error?: string;
}
