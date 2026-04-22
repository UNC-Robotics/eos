import { useEditorStore } from '@/lib/stores/editorStore';
import { serializeYaml } from '@/lib/utils/editor-utils';
import { serializeDeviceAssignment, serializeResourceAssignment } from '@/lib/utils/assignment-utils';
import { buildFloatParamsMap, coerceForSpec, deepEqual, ensureFloatNotationInYaml } from '@/lib/utils/protocolHelpers';
import { flattenInputParameters } from '@/lib/utils/paramGroups';
import type { TaskNode, TaskSpec } from '@/lib/types/protocol';

interface SerializedProtocol {
  yaml: string;
  layoutJson: string;
}

function serializeTaskForYaml(task: TaskNode, specMap: Map<string, TaskSpec>): Record<string, unknown> {
  const { position: _position, device_holds, resource_holds, devices, resources, ...rest } = task;
  const result: Record<string, unknown> = { ...rest };

  const spec = specMap.get(task.type);

  // Strip values equal to the task.yml default so protocol.yml tracks task.yml; form text is coerced once here.
  if (result.parameters && spec) {
    const flatSpecParams = flattenInputParameters(spec.input_parameters);
    if (Object.keys(flatSpecParams).length === 0) {
      delete result.parameters;
    } else {
      const params = result.parameters as Record<string, unknown>;
      const filtered: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(params)) {
        const paramSpec = flatSpecParams[key];
        if (!paramSpec) continue;
        const coerced = coerceForSpec(value, paramSpec);
        if (paramSpec.value !== undefined && deepEqual(coerced, paramSpec.value)) continue;
        filtered[key] = coerced;
      }
      if (Object.keys(filtered).length > 0) {
        result.parameters = filtered;
      } else {
        delete result.parameters;
      }
    }
  }

  if (devices) {
    const serializedDevices: Record<string, unknown> = {};
    for (const [slot, assignment] of Object.entries(devices)) {
      if (!spec?.input_devices || slot in spec.input_devices) {
        serializedDevices[slot] = serializeDeviceAssignment(assignment, device_holds?.[slot]);
      }
    }
    result.devices = serializedDevices;
  }

  if (resources) {
    const serializedResources: Record<string, unknown> = {};
    for (const [slot, assignment] of Object.entries(resources)) {
      if (!spec?.input_resources || slot in spec.input_resources) {
        serializedResources[slot] = serializeResourceAssignment(assignment, resource_holds?.[slot]);
      }
    }
    result.resources = serializedResources;
  }

  return result;
}

/**
 * Synchronous YAML + layout-JSON snapshot of the current editor store. Shared by the sync effect and save handler.
 */
export function serializeCurrentProtocol(): SerializedProtocol {
  const { tasks, taskTemplates, protocolType, protocolDesc, labs } = useEditorStore.getState();

  const specMap = new Map(taskTemplates.map((t) => [t.type, t]));
  const tasksForYaml = tasks.map((task) => serializeTaskForYaml(task, specMap));
  let yaml = serializeYaml({ type: protocolType, desc: protocolDesc, labs, tasks: tasksForYaml });

  if (taskTemplates.length > 0) {
    const floatParamsMap = buildFloatParamsMap(taskTemplates);
    const tasksWithTypes = tasks.map((task) => ({ name: task.name, type: task.type }));
    yaml = ensureFloatNotationInYaml(yaml, tasksWithTypes, floatParamsMap);
  }

  const layout: Record<string, { x: number; y: number }> = {};
  tasks.forEach((task) => {
    if (task.position) {
      layout[task.name] = task.position;
    }
  });

  return { yaml, layoutJson: Object.keys(layout).length > 0 ? JSON.stringify(layout, null, 2) : '' };
}
