import type { ActionResult } from '@/lib/types/api';
import type { InputParameterEntry, ParameterSpec, ParameterValue, TaskSpec } from '@/lib/types/protocol';
import type { ProtocolSpec } from '@/lib/api/specs';
import { flattenInputParameters } from '@/lib/utils/paramGroups';

/**
 * Detects if a value is a reference string (e.g., "task_name.output_param")
 */
export function isReferenceValue(value: unknown): boolean {
  if (typeof value !== 'string') return false;
  return /^[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*(\..*)?$/.test(value);
}

/**
 * Creates a success ActionResult
 */
export function createSuccessResult(): ActionResult {
  return { success: true };
}

/**
 * Creates an error ActionResult
 */
export function createErrorResult(error: unknown, defaultMessage: string): ActionResult {
  return {
    success: false,
    error: error instanceof Error ? error.message : defaultMessage,
  };
}

/**
 * Checks if an object has non-empty contents
 */
export function hasNonEmptyObject(obj: unknown): boolean {
  return !!obj && typeof obj === 'object' && Object.keys(obj).length > 0;
}

/**
 * Formats a value for display in an input field
 */
export function formatInputValue(value: unknown): string {
  return value !== undefined && value !== null ? String(value) : '';
}

/**
 * Coerce raw form text to the spec type. Non-coercible input (e.g. "eos_dynamic",
 * partial "-") passes through so validation can flag it and dynamic markers survive.
 */
export function coerceForSpec(value: unknown, spec: Pick<ParameterSpec, 'type'>): unknown {
  if (value === undefined || value === null || value === '') return undefined;
  if (typeof value !== 'string') return value;
  const type = spec.type.toLowerCase();
  if (type === 'int') {
    const n = parseInt(value, 10);
    return Number.isFinite(n) && String(n) === value.trim() ? n : value;
  }
  if (type === 'float' || type === 'number' || type === 'double') {
    const n = parseFloat(value);
    return Number.isFinite(n) ? n : value;
  }
  if (type === 'bool' || type === 'boolean') {
    const v = value.trim().toLowerCase();
    if (v === 'true') return true;
    if (v === 'false') return false;
    return value;
  }
  if (type === 'list' || type === 'dict' || type === 'dictionary') {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }
  return value;
}

/**
 * Converts a raw parameter value to ParameterValue format
 */
export function convertToParameterValue(value: unknown): ParameterValue {
  return {
    mode: isReferenceValue(value) ? 'reference' : 'static',
    value,
  };
}

/**
 * Wraps each inner value in ParameterValue form. Used for both protocol-run and campaign structures.
 */
export function convertParameters(
  params: Record<string, Record<string, unknown>>
): Record<string, Record<string, ParameterValue>> {
  const converted: Record<string, Record<string, ParameterValue>> = {};
  Object.entries(params).forEach(([taskName, taskParams]) => {
    converted[taskName] = {};
    Object.entries(taskParams).forEach(([paramName, value]) => {
      converted[taskName][paramName] = convertToParameterValue(value);
    });
  });
  return converted;
}

/**
 * Unwrap ParameterValue → raw value for submission; drops empty/null/undefined entries.
 * When `taskTypeMap` + `taskSpecs` are provided, values are coerced per spec type.
 */
export function extractParameterValues(
  taskParameters: Record<string, Record<string, ParameterValue>>,
  taskTypeMap?: Record<string, string>,
  taskSpecs?: Record<string, { input_parameters?: Record<string, InputParameterEntry> }>
): Record<string, Record<string, unknown>> {
  const parameters: Record<string, Record<string, unknown>> = {};
  Object.entries(taskParameters).forEach(([taskName, params]) => {
    const flatSpecParams =
      taskTypeMap && taskSpecs ? flattenInputParameters(taskSpecs[taskTypeMap[taskName]]?.input_parameters) : {};
    const filteredParams: Record<string, unknown> = {};
    for (const [paramName, paramValue] of Object.entries(params)) {
      const spec = flatSpecParams[paramName];
      // References pass through as strings; other types coerce per spec (string input -> number/bool/list/dict).
      const coerced =
        paramValue.mode === 'reference' || !spec ? paramValue.value : coerceForSpec(paramValue.value, spec);
      if (coerced === undefined || coerced === null || coerced === '') continue;
      filteredParams[paramName] = coerced;
    }
    if (Object.keys(filteredParams).length > 0) {
      parameters[taskName] = filteredParams;
    }
  });
  return parameters;
}

/**
 * Map of taskType → set of float/double leaf param names.
 */
export function buildFloatParamsMap(taskSpecs: TaskSpec[]): Map<string, Set<string>> {
  const floatParamsMap = new Map<string, Set<string>>();

  for (const spec of taskSpecs) {
    const floatParams = new Set<string>();

    for (const [paramName, paramSpec] of Object.entries(flattenInputParameters(spec.input_parameters))) {
      const paramType = paramSpec.type?.toLowerCase();
      if (paramType === 'float' || paramType === 'double') {
        floatParams.add(paramName);
      }
    }

    if (floatParams.size > 0) {
      floatParamsMap.set(spec.type, floatParams);
    }
  }

  return floatParamsMap;
}

/**
 * Rewrites `paramName: 300` → `paramName: 300.0` in the serialized YAML for params
 * declared as float/double, so integral values round-trip as floats.
 */
export function ensureFloatNotationInYaml(
  yaml: string,
  tasks: Array<{ name: string; type: string }>,
  floatParamsMap: Map<string, Set<string>>
): string {
  if (floatParamsMap.size === 0) {
    return yaml;
  }

  // Collect all float parameter names across all tasks in this protocol
  const allFloatParams = new Set<string>();
  for (const task of tasks) {
    const floatParams = floatParamsMap.get(task.type);
    if (floatParams) {
      for (const param of floatParams) {
        allFloatParams.add(param);
      }
    }
  }

  if (allFloatParams.size === 0) {
    return yaml;
  }

  // Process each line - look for patterns like "paramName: 123" or "paramName: '123.0'"
  const lines = yaml.split('\n');
  const processedLines = lines.map((line) => {
    // Match parameter lines with integer values: "  paramName: 123"
    // We need to capture the indentation, param name, and value
    const integerMatch = line.match(/^(\s*)(\w+):\s+(-?\d+)$/);
    if (integerMatch) {
      const [, indent, paramName, intValue] = integerMatch;
      if (allFloatParams.has(paramName)) {
        // Convert integer to float notation
        return `${indent}${paramName}: ${intValue}.0`;
      }
    }

    // Match parameter lines with quoted float strings: "  paramName: '123.0'" or '  paramName: "123.0"'
    const quotedFloatMatch = line.match(/^(\s*)(\w+):\s+['"](-?\d+\.?\d*)['"]$/);
    if (quotedFloatMatch) {
      const [, indent, paramName, floatValue] = quotedFloatMatch;
      if (allFloatParams.has(paramName)) {
        // Remove quotes and ensure float notation
        const numValue = parseFloat(floatValue);
        if (!isNaN(numValue)) {
          const formattedValue = Number.isInteger(numValue) ? numValue.toFixed(1) : floatValue;
          return `${indent}${paramName}: ${formattedValue}`;
        }
      }
    }

    return line;
  });

  return processedLines.join('\n');
}

/** Deep equality for YAML-safe values (primitives, arrays, plain objects). */
export function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || b === null || a === undefined || b === undefined) return false;
  if (typeof a !== typeof b || typeof a !== 'object') return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, i) => deepEqual(item, b[i]));
  }
  const ao = a as Record<string, unknown>;
  const bo = b as Record<string, unknown>;
  const aKeys = Object.keys(ao);
  if (aKeys.length !== Object.keys(bo).length) return false;
  return aKeys.every((k) => deepEqual(ao[k], bo[k]));
}

/** True when a value should be treated as cleared. */
export function isEmptyParamValue(value: unknown): boolean {
  return value === undefined || value === null || value === '';
}

/** True when a value deep-equals the task.yml default for this param. */
export function matchesSpecDefault(value: unknown, spec: Pick<ParameterSpec, 'value'>): boolean {
  if (spec.value === undefined) return false;
  return deepEqual(value, spec.value);
}

/** onBlur helper: if the field is empty and a default exists, restore it. */
export function restoreDefaultIfEmpty(
  currentValue: unknown,
  spec: Pick<ParameterSpec, 'value'>,
  onChange: (value: unknown) => void
): void {
  if (!isEmptyParamValue(currentValue) || spec.value === undefined) return;
  onChange(spec.value);
}

/** Seed a parameters object with task.yml defaults; booleans without `value:` default to false. */
export function buildDefaultParameters(spec: Pick<TaskSpec, 'input_parameters'>): Record<string, unknown> {
  const defaults: Record<string, unknown> = {};
  for (const [name, paramSpec] of Object.entries(flattenInputParameters(spec.input_parameters))) {
    if (paramSpec.value !== undefined) {
      defaults[name] = paramSpec.value;
    } else if (paramSpec.type.toLowerCase() === 'bool' || paramSpec.type.toLowerCase() === 'boolean') {
      defaults[name] = false;
    }
  }
  return defaults;
}

/**
 * Check if a parameter value equals its spec default
 */
function valuesEqual(value: unknown, specDefault: unknown): boolean {
  // Handle eos_dynamic and undefined defaults - treat empty values as matching
  if (specDefault === 'eos_dynamic' || specDefault === undefined) {
    return value === undefined || value === null || value === '';
  }

  // Direct equality (handles primitives and reference strings)
  if (value === specDefault) return true;

  // Deep equality for objects/arrays
  if (typeof value === 'object' && typeof specDefault === 'object' && value !== null && specDefault !== null) {
    return JSON.stringify(value) === JSON.stringify(specDefault);
  }

  return false;
}

/**
 * Drops entries equal to their spec default. Used on clone so defaults aren't flagged as overrides.
 */
export function filterNonDefaultParameters(
  params: Record<string, Record<string, unknown>>,
  protocolSpec: ProtocolSpec
): Record<string, Record<string, unknown>> {
  const filtered: Record<string, Record<string, unknown>> = {};

  for (const [taskName, taskParams] of Object.entries(params)) {
    const taskConfig = protocolSpec.tasks.find((t) => t.name === taskName);
    if (!taskConfig) continue;

    const filteredTaskParams: Record<string, unknown> = {};

    for (const [paramName, value] of Object.entries(taskParams)) {
      const specDefault = taskConfig.parameters?.[paramName];

      // Include parameter only if it differs from spec default
      if (!valuesEqual(value, specDefault)) {
        filteredTaskParams[paramName] = value;
      }
    }

    if (Object.keys(filteredTaskParams).length > 0) {
      filtered[taskName] = filteredTaskParams;
    }
  }

  return filtered;
}
