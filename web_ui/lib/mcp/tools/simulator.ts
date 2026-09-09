import { z } from 'zod/v3';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { orchestratorGet, orchestratorPost } from '@/lib/api/orchestrator';
import { textResult, errorResult } from '../helpers/format';

interface SimDeviceUtil {
  name: string;
  time_fmt: string;
  pct: number;
}

interface SimResourceUtil {
  name: string;
  time_fmt: string;
  pct: number;
}

interface SimStats {
  makespan: number;
  makespan_fmt: string;
  scheduler_type: string;
  total_tasks: number;
  run_completions: [string, string][];
  device_util: SimDeviceUtil[];
  resource_util: SimResourceUtil[];
  max_parallel: number;
  avg_parallel: number;
  total_task_time_fmt: string;
  theoretical_min_fmt: string;
  efficiency: number;
}

interface DeadlockTask {
  name: string;
  blocked_on: string;
}

interface DeadlockRun {
  protocol_run_name: string;
  pending_tasks: DeadlockTask[];
}

interface DeadlockLock {
  name: string;
  owner: string;
  held: boolean;
}

interface DeadlockInfo {
  queued_count: number;
  pending_runs: DeadlockRun[];
  device_locks: DeadlockLock[];
  resource_locks: DeadlockLock[];
}

interface SimResponse {
  timeline: unknown[];
  stats: SimStats;
  deadlock?: DeadlockInfo;
}

function formatStats(stats: SimStats): string {
  const lines: string[] = [];
  lines.push(
    `Simulation complete (scheduler=${stats.scheduler_type}, makespan=${stats.makespan_fmt}, ${stats.total_tasks} tasks)`
  );

  if (stats.run_completions.length > 0) {
    lines.push('');
    lines.push('Run completions:');
    for (const [name, time] of stats.run_completions) {
      lines.push(`  ${name}  ${time}`);
    }
  }

  lines.push('');
  lines.push(
    `Parallelism: max=${stats.max_parallel} avg=${stats.avg_parallel.toFixed(2)} efficiency=${stats.efficiency.toFixed(1)}% (theoretical min ${stats.theoretical_min_fmt}, total task-time ${stats.total_task_time_fmt})`
  );

  if (stats.device_util.length > 0) {
    lines.push('');
    lines.push('Device utilization:');
    for (const d of stats.device_util) {
      lines.push(`  ${d.name}  ${d.pct.toFixed(1)}% (${d.time_fmt})`);
    }
  }

  if (stats.resource_util.length > 0) {
    lines.push('');
    lines.push('Resource utilization:');
    for (const r of stats.resource_util) {
      lines.push(`  ${r.name}  ${r.pct.toFixed(1)}% (${r.time_fmt})`);
    }
  }

  return lines.join('\n');
}

function formatDeadlock(deadlock: DeadlockInfo, scheduler: string): string {
  const lines: string[] = [];
  lines.push(`DEADLOCK: simulation stopped early under scheduler=${scheduler}.`);
  if (deadlock.queued_count > 0) {
    lines.push(
      `${deadlock.queued_count} protocol run(s) never started. The active runs are mutually waiting on locks held by each other.`
    );
  } else {
    lines.push('The active runs are mutually waiting on locks held by each other.');
  }

  const stuck = deadlock.pending_runs.filter((r) => r.pending_tasks.some((t) => t.blocked_on === 'resources/devices'));
  if (stuck.length > 0) {
    lines.push('');
    lines.push('Stuck protocol runs:');
    for (const run of stuck) {
      lines.push(`  ${run.protocol_run_name}`);
      for (const task of run.pending_tasks.filter((t) => t.blocked_on === 'resources/devices')) {
        lines.push(`    ${task.name}: blocked on resources/devices`);
      }
    }
  }

  const heldLocks = [
    ...deadlock.device_locks.filter((l) => l.held).map((l) => ({ kind: 'device', ...l })),
    ...deadlock.resource_locks.filter((l) => l.held).map((l) => ({ kind: 'resource', ...l })),
  ];
  if (heldLocks.length > 0) {
    lines.push('');
    lines.push('Held locks:');
    for (const lock of heldLocks) {
      lines.push(`  [${lock.kind}] ${lock.name} held by ${lock.owner}`);
    }
  }

  lines.push('');
  lines.push(
    'Suggestion: try scheduler=cpsat, lower max_concurrent, or remove unnecessary hold:true flags on resources/devices that no successor task reuses.'
  );

  return lines.join('\n');
}

export function registerSimulatorTools(server: McpServer) {
  server.registerTool(
    'run_simulator',
    {
      title: 'Run Protocol Simulator',
      description:
        'Simulate one or more protocols to verify they schedule cleanly before running for real. Returns stats (makespan, run completions, device/resource utilization, parallelism) and a deadlock report if the scheduler gets stuck. Run after creating or significantly editing a protocol.',
      inputSchema: {
        protocols: z
          .array(
            z.object({
              type: z.string().describe('Protocol type name'),
              iterations: z.number().int().min(1).max(50).describe('Number of protocol runs'),
              max_concurrent: z.number().int().min(0).default(0).describe('Max concurrent runs (0 = unlimited)'),
              priority: z.number().int().default(1),
            })
          )
          .min(1)
          .describe('Protocol(s) to simulate'),
        packages: z
          .array(z.string())
          .optional()
          .describe('Packages to load. Omit to use all currently active packages.'),
        scheduler: z
          .enum(['greedy', 'cpsat'])
          .default('greedy')
          .describe(
            'greedy is the production default; cpsat is a planning scheduler that avoids deadlocks but is slower'
          ),
        jitter: z.number().min(0).max(1).default(0).describe('Duration jitter fraction (0.1 = ±10%)'),
        seed: z.number().int().optional().describe('Random seed for reproducibility'),
      },
    },
    async ({ protocols, packages, scheduler, jitter, seed }) => {
      try {
        let pkgList = packages;
        if (!pkgList || pkgList.length === 0) {
          const pkgs = (await orchestratorGet('/packages/')) as Record<string, boolean>;
          pkgList = Object.entries(pkgs)
            .filter(([, active]) => active)
            .map(([name]) => name);
          if (pkgList.length === 0) {
            return errorResult('No active packages found. Specify packages explicitly or load some first.');
          }
        }

        const body = {
          packages: pkgList,
          protocols,
          scheduler,
          jitter,
          seed: seed ?? null,
        };

        const result = (await orchestratorPost('/simulator/run', body)) as SimResponse;

        if (result.deadlock) {
          return errorResult(formatDeadlock(result.deadlock, result.stats.scheduler_type));
        }
        return textResult(formatStats(result.stats));
      } catch (e) {
        return errorResult(`Simulation failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );
}
