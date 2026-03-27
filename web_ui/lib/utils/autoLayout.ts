import { EDITOR_LAYOUT } from '@/lib/constants/theme';
import type { TaskNode } from '@/lib/types/protocol';

/**
 * Auto-layout tasks using hierarchical layering (left to right).
 * Returns a map of task name → position.
 */
export function autoLayoutTasks(tasks: TaskNode[]): Record<string, { x: number; y: number }> {
  const layout: Record<string, { x: number; y: number }> = {};

  // Build dependency map
  const dependencyMap = new Map<string, Set<string>>();

  tasks.forEach((task) => {
    const deps = new Set<string>();
    if (task.dependencies) {
      task.dependencies.forEach((dep: string) => deps.add(dep));
    }
    dependencyMap.set(task.name, deps);
  });

  // Calculate layer for each task (topological sort by dependency depth)
  const layers: string[][] = [];
  const taskLayers = new Map<string, number>();
  const processed = new Set<string>();

  // Helper to get max layer of dependencies
  const getMaxDepLayer = (taskName: string): number => {
    const deps = dependencyMap.get(taskName);
    if (!deps || deps.size === 0) return 0;

    let maxLayer = -1;
    for (const dep of deps) {
      const depLayer = taskLayers.get(dep);
      if (depLayer !== undefined) {
        maxLayer = Math.max(maxLayer, depLayer);
      }
    }
    return maxLayer + 1;
  };

  // Process tasks in waves until all are placed
  const remainingTasks = new Set(tasks.map((t) => t.name));
  const maxIterations = tasks.length * 2;
  let iteration = 0;

  while (remainingTasks.size > 0 && iteration < maxIterations) {
    iteration++;
    const tasksToProcess: string[] = [];

    for (const taskName of remainingTasks) {
      const deps = dependencyMap.get(taskName)!;
      const allDepsProcessed = Array.from(deps).every((d) => processed.has(d));

      if (allDepsProcessed) {
        tasksToProcess.push(taskName);
      }
    }

    if (tasksToProcess.length === 0) {
      tasksToProcess.push(...Array.from(remainingTasks));
    }

    for (const taskName of tasksToProcess) {
      const layer = getMaxDepLayer(taskName);
      taskLayers.set(taskName, layer);
      processed.add(taskName);
      remainingTasks.delete(taskName);

      while (layers.length <= layer) {
        layers.push([]);
      }
      layers[layer].push(taskName);
    }
  }

  const { horizontalSpacing, verticalSpacing, startX, startY } = EDITOR_LAYOUT;

  layers.forEach((layerTasks, layerIndex) => {
    const x = startX + layerIndex * horizontalSpacing;
    const layerHeight = (layerTasks.length - 1) * verticalSpacing;
    const layerStartY = startY - layerHeight / 2;

    layerTasks.forEach((taskName, indexInLayer) => {
      layout[taskName] = {
        x,
        y: layerStartY + indexInLayer * verticalSpacing,
      };
    });
  });

  return layout;
}
