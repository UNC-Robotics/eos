import { getTasks } from '@/features/tasks/api/tasks';
import { TasksTable } from '@/features/tasks/components/TasksTable';
import { getTaskSpecs, getLabSpecs } from '@/lib/api/specs';
import { transformTaskSpec } from '@/lib/api/taskSpecTransform';
import type { TaskSpec } from '@/lib/types/protocol';

export const dynamic = 'force-dynamic';

export default async function TasksPage() {
  const [initialData, rawTaskSpecs, labSpecs] = await Promise.all([
    getTasks(),
    getTaskSpecs(),
    getLabSpecs(true), // Only loaded labs
  ]);

  const taskSpecs: Record<string, TaskSpec> = Object.fromEntries(
    Object.entries(rawTaskSpecs).map(([type, spec]) => [type, transformTaskSpec(type, spec)])
  );

  return (
    <div className="container mx-auto p-6">
      <TasksTable initialData={initialData} taskSpecs={taskSpecs} labSpecs={labSpecs} />
    </div>
  );
}
