import type { InputParameterEntry, ParameterGroupSpec, ParameterSpec } from '@/lib/types/protocol';

export type InputParameterStructureItem =
  | { kind: 'param'; name: string; spec: ParameterSpec }
  | { kind: 'group'; name: string; params: ParameterGroupSpec };

export function isParameterGroup(entry: InputParameterEntry | undefined): entry is ParameterGroupSpec {
  return !!entry && typeof entry === 'object' && !('type' in entry);
}

export function iterateInputParameters(
  params: Record<string, InputParameterEntry> | undefined
): InputParameterStructureItem[] {
  if (!params) return [];
  const result: InputParameterStructureItem[] = [];
  for (const [name, entry] of Object.entries(params)) {
    if (isParameterGroup(entry)) {
      result.push({ kind: 'group', name, params: entry });
    } else {
      result.push({ kind: 'param', name, spec: entry });
    }
  }
  return result;
}

export function flattenInputParameters(
  params: Record<string, InputParameterEntry> | undefined
): Record<string, ParameterSpec> {
  if (!params) return {};
  const flat: Record<string, ParameterSpec> = {};
  for (const [name, entry] of Object.entries(params)) {
    if (isParameterGroup(entry)) {
      for (const [leafName, leafSpec] of Object.entries(entry)) {
        flat[leafName] = leafSpec;
      }
    } else {
      flat[name] = entry;
    }
  }
  return flat;
}
