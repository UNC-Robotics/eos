'use client';

import type { SimStats } from '../types';

export function SimulatorStats({ stats }: { stats: SimStats }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
      <div className="bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 p-4">
        <h3 className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-3">Device Utilization</h3>
        <div className="space-y-3">
          {stats.device_util.map((d) => (
            <div key={d.name}>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600 dark:text-gray-400 truncate mr-2" title={d.name}>
                  {d.name}
                </span>
                <span className="text-gray-900 dark:text-white font-medium tabular-nums whitespace-nowrap">
                  {d.pct.toFixed(1)}%
                </span>
              </div>
              <div className="h-1.5 bg-gray-200 dark:bg-slate-700 rounded-full">
                <div
                  className="h-1.5 bg-blue-600 dark:bg-yellow-500 rounded-full transition-all"
                  style={{ width: `${d.pct}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 p-4">
        <h3 className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-3">Resource Utilization</h3>
        <div className="space-y-3">
          {stats.resource_util.map((r) => (
            <div key={r.name}>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600 dark:text-gray-400 truncate mr-2" title={r.name}>
                  {r.name}
                </span>
                <span className="text-gray-900 dark:text-white font-medium tabular-nums whitespace-nowrap">
                  {r.pct.toFixed(1)}%
                </span>
              </div>
              <div className="h-1.5 bg-gray-200 dark:bg-slate-700 rounded-full">
                <div
                  className="h-1.5 bg-blue-600 dark:bg-yellow-500 rounded-full transition-all"
                  style={{ width: `${r.pct}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 p-4">
        <h3 className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-3">Parallelism</h3>
        <div className="space-y-2">
          <Row label="Max concurrent" value={String(stats.max_parallel)} />
          <Row label="Avg concurrent" value={stats.avg_parallel.toFixed(2)} />
          <Row label="Total task-seconds" value={stats.total_task_time_fmt} />
          <Row label="Theoretical min" value={stats.theoretical_min_fmt} />
          <Row label="Efficiency" value={`${stats.efficiency.toFixed(1)}%`} />
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 p-4 max-h-64 overflow-y-auto">
        <h3 className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-3">Run Completion</h3>
        <div className="space-y-1">
          {stats.run_completions.map(([name, time]) => (
            <Row key={name} label={name} value={time} />
          ))}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-gray-500 dark:text-gray-400 truncate mr-2">{label}</span>
      <span className="text-gray-900 dark:text-white font-medium tabular-nums whitespace-nowrap">{value}</span>
    </div>
  );
}
