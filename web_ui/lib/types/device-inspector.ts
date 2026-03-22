/**
 * Type definitions for Device Inspector feature
 */

/**
 * Parameter definition for a device function
 */
export interface FunctionParameter {
  name: string;
  type: string;
  required: boolean;
  default: string | null;
}

/**
 * Device function metadata
 */
export interface DeviceFunction {
  name: string;
  parameters: FunctionParameter[];
  return_type: string;
  docstring: string;
  is_async: boolean;
}

/**
 * Device introspection result - maps function names to their metadata
 */
export interface DeviceIntrospection {
  [functionName: string]: DeviceFunction;
}

/**
 * Result of calling a device function
 */
export interface FunctionCallResult {
  success: boolean;
  result?: unknown;
  error?: string;
}

/**
 * Record of a function call for history tracking
 */
export interface FunctionCall {
  id: string;
  timestamp: number;
  functionName: string;
  parameters: Record<string, unknown>;
  result: FunctionCallResult;
  duration?: number;
}

/**
 * Device selection state
 */
export interface SelectedDevice {
  labName: string;
  deviceName: string;
}

/**
 * Parameter type classification for UI rendering
 */
export type ParameterUIType = 'string' | 'number' | 'boolean' | 'json';

/**
 * Parsed parameter for form rendering
 */
export interface ParsedParameter extends FunctionParameter {
  uiType: ParameterUIType;
}
