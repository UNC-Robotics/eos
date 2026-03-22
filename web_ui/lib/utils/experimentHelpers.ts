import type { ActionResult } from '@/lib/types/api';
import type { ParameterValue, TaskSpec } from '@/lib/types/experiment';
import type { ExperimentSpec } from '@/lib/api/specs';

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
 * Parses number input, handling empty strings and invalid input.
 * Returns the parsed number without adding .0 suffix - the float notation
 * is added at serialization time by ensureFloatNotationInYaml.
 */
export function parseNumberInput(rawValue: string, type: 'int' | 'float'): number | string | undefined {
  if (rawValue === '') return undefined;

  if (type === 'int') {
    const intValue = parseInt(rawValue, 10);
    return isNaN(intValue) ? rawValue : intValue;
  }

  // For floats, just parse the number - don't add .0 suffix during input
  // The .0 suffix is added at YAML serialization time by ensureFloatNotationInYaml
  const floatValue = parseFloat(rawValue);
  if (isNaN(floatValue)) return rawValue;

  return floatValue;
}

/**
 * Formats a value for display in an input field
 */
export function formatInputValue(value: unknown): string {
  return value !== undefined && value !== null ? String(value) : '';
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
 * Converts a parameter structure to ParameterValue format
 * Supports both experiment and campaign parameter structures
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
 * Extracts raw parameter values from ParameterValue structure
 * Filters out undefined, null, and empty string values
 *
 * If taskTypeMap and taskSpecs are provided, ensures proper type conversion (e.g., int vs float)
 * taskTypeMap should map task names to their task types: { taskName: taskType }
 */
export function extractParameterValues(
  taskParameters: Record<string, Record<string, ParameterValue>>,
  taskTypeMap?: Record<string, string>,
  taskSpecs?: Record<string, { input_parameters?: Record<string, { type: string }> }>
): Record<string, Record<string, unknown>> {
  const parameters: Record<string, Record<string, unknown>> = {};
  Object.entries(taskParameters).forEach(([taskName, params]) => {
    const filteredParams = Object.entries(params)
      .filter(([, paramValue]) => {
        const value = paramValue.value;
        return value !== undefined && value !== null && value !== '';
      })
      .reduce(
        (acc, [paramName, paramValue]) => {
          let value = paramValue.value;

          // If we have task specs, check if this parameter should be a float
          if (taskTypeMap && taskSpecs) {
            const taskType = taskTypeMap[taskName];
            const taskSpec = taskType ? taskSpecs[taskType] : undefined;
            const paramSpec = taskSpec?.input_parameters?.[paramName];
            const paramType = paramSpec?.type?.toLowerCase();

            // For float parameters, ensure proper representation
            if (paramType === 'float' || paramType === 'double') {
              // If it's a number and a whole number, convert to string with decimal
              if (typeof value === 'number' && Number.isInteger(value)) {
                value = value.toFixed(1);
              }
              // Keep string values as-is (they should already have decimal point from parseNumberInput)
            }
          }

          acc[paramName] = value;
          return acc;
        },
        {} as Record<string, unknown>
      );

    if (Object.keys(filteredParams).length > 0) {
      parameters[taskName] = filteredParams;
    }
  });
  return parameters;
}

/**
 * Build a set of float parameter names for each task type from task specs.
 * Returns a Map: taskType -> Set of float parameter names
 */
export function buildFloatParamsMap(taskSpecs: TaskSpec[]): Map<string, Set<string>> {
  const floatParamsMap = new Map<string, Set<string>>();

  for (const spec of taskSpecs) {
    const floatParams = new Set<string>();

    if (spec.input_parameters) {
      for (const [paramName, paramSpec] of Object.entries(spec.input_parameters)) {
        const paramType = paramSpec.type?.toLowerCase();
        if (paramType === 'float' || paramType === 'double') {
          floatParams.add(paramName);
        }
      }
    }

    if (floatParams.size > 0) {
      floatParamsMap.set(spec.type, floatParams);
    }
  }

  return floatParamsMap;
}

/**
 * Post-process YAML string to ensure float parameters have decimal point notation.
 * This converts integer values to float notation (e.g., "300" to "300.0") for parameters
 * that should be floats based on the task spec.
 *
 * @param yaml The serialized YAML string
 * @param tasks Array of tasks with their types
 * @param floatParamsMap Map of task types to their float parameter names
 * @returns The processed YAML string with proper float notation
 */
export function ensureFloatNotationInYaml(
  yaml: string,
  tasks: Array<{ name: string; type: string }>,
  floatParamsMap: Map<string, Set<string>>
): string {
  if (floatParamsMap.size === 0) {
    return yaml;
  }

  // Collect all float parameter names across all tasks in this experiment
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
 * Filters parameters to only include those that differ from spec defaults.
 * Used when cloning to avoid marking default values as overrides.
 */
export function filterNonDefaultParameters(
  params: Record<string, Record<string, unknown>>,
  experimentSpec: ExperimentSpec
): Record<string, Record<string, unknown>> {
  const filtered: Record<string, Record<string, unknown>> = {};

  for (const [taskName, taskParams] of Object.entries(params)) {
    const taskConfig = experimentSpec.tasks.find((t) => t.name === taskName);
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
