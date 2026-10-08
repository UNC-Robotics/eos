'use client';

import { AlertTriangle } from 'lucide-react';
import type { DeadlockInfo } from '../types';

export function DeadlockBanner({ deadlock, scheduler }: { deadlock: DeadlockInfo; scheduler: string }) {
  const blockedRuns = deadlock.pending_runs.filter((r) =>
    r.pending_tasks.some((t) => t.blocked_on === 'resources/devices')
  );
  const heldLocks = [
    ...deadlock.device_locks.filter((l) => l.held).map((l) => ({ kind: 'device' as const, ...l })),
    ...deadlock.resource_locks.filter((l) => l.held).map((l) => ({ kind: 'resource' as const, ...l })),
  ];

  return (
    <div className="bg-red-50 dark:bg-red-950/40 border border-red-300 dark:border-red-800 rounded-lg p-4 space-y-3">
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-red-900 dark:text-red-200">
            Deadlock detected, simulation stopped early
          </h3>
          <p className="text-sm text-red-800 dark:text-red-300 mt-1">
            The {scheduler} scheduler couldn't make further progress: every active protocol run is waiting on a resource
            or device held by another run.{' '}
            {deadlock.queued_count > 0 && (
              <>
                {deadlock.queued_count} additional run{deadlock.queued_count === 1 ? '' : 's'} never got to start.{' '}
              </>
            )}
            Try the <span className="font-mono">heuristic</span> or <span className="font-mono">cpsat</span> scheduler,
            lower <span className="font-mono">max_concurrent</span>, or relax unnecessary{' '}
            <span className="font-mono">hold</span> flags.
          </p>
        </div>
      </div>

      {blockedRuns.length > 0 && (
        <Section title="Stuck protocol runs">
          {blockedRuns.map((run) => (
            <div key={run.protocol_run_name} className="text-sm">
              <div className="font-mono font-medium text-red-900 dark:text-red-200">{run.protocol_run_name}</div>
              <ul className="ml-4 mt-1 space-y-0.5 text-red-800 dark:text-red-300">
                {run.pending_tasks
                  .filter((t) => t.blocked_on === 'resources/devices')
                  .map((t) => (
                    <li key={t.name}>
                      <span className="font-mono">{t.name}</span>
                      <span className="text-red-700 dark:text-red-400">: blocked on resources/devices</span>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </Section>
      )}

      {heldLocks.length > 0 && (
        <Section title="Held locks blocking progress">
          <ul className="text-sm space-y-0.5 text-red-800 dark:text-red-300">
            {heldLocks.map((l) => (
              <li key={`${l.kind}:${l.name}`}>
                <span className="text-red-700 dark:text-red-400 mr-1">[{l.kind}]</span>
                <span className="font-mono">{l.name}</span>
                <span className="text-red-700 dark:text-red-400"> held by </span>
                <span className="font-mono">{l.owner}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="pl-8 space-y-1">
      <div className="text-xs uppercase tracking-wide text-red-700 dark:text-red-400">{title}</div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}
