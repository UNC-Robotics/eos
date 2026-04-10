export interface ProtocolRunConfig {
  type: string;
  iterations: number;
  max_concurrent: number;
}

export interface SimConfig {
  packages: string[];
  protocols: ProtocolRunConfig[];
  scheduler: string;
  jitter: number;
  seed: number | null;
}

export interface TaskDevice {
  slot: string;
  lab: string;
  name: string;
}

export interface TaskRecord {
  protocol_run: string;
  task: string;
  start: number;
  duration: number;
  end: number;
  devices: TaskDevice[];
  resources: Record<string, string>;
}

export interface DeviceUtil {
  name: string;
  time_fmt: string;
  pct: number;
}

export interface ResourceUtil {
  name: string;
  time_fmt: string;
  pct: number;
}

export interface SimStats {
  makespan: number;
  makespan_fmt: string;
  scheduler_type: string;
  total_tasks: number;
  run_completions: [string, string][];
  device_util: DeviceUtil[];
  resource_util: ResourceUtil[];
  max_parallel: number;
  avg_parallel: number;
  total_task_time_fmt: string;
  theoretical_min_fmt: string;
  efficiency: number;
}

export interface SimResults {
  timeline: TaskRecord[];
  stats: SimStats;
}
