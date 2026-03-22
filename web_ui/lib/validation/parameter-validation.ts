import { ParameterSpec } from '../types/experiment';

export interface ValidationResult {
  valid: boolean;
  error?: string;
}

/**
 * Validates a numeric parameter value against its spec
 */
export function validateNumeric(value: unknown, spec: ParameterSpec): ValidationResult {
  if (value === null || value === undefined || value === '') {
    return { valid: false, error: 'Value is required' };
  }

  const numValue = typeof value === 'string' ? parseFloat(value) : Number(value);

  if (isNaN(numValue)) {
    return { valid: false, error: 'Value must be a valid number' };
  }

  // Check min/max bounds (only for single numbers, not arrays)
  if (typeof spec.min === 'number' && numValue < spec.min) {
    return { valid: false, error: `Value must be at least ${spec.min}` };
  }

  if (typeof spec.max === 'number' && numValue > spec.max) {
    return { valid: false, error: `Value must be at most ${spec.max}` };
  }

  // For int type, check if it's an integer
  if (spec.type === 'int' && !Number.isInteger(numValue)) {
    return { valid: false, error: 'Value must be an integer' };
  }

  return { valid: true };
}

/**
 * Validates a string parameter value against its spec
 */
export function validateString(value: unknown, _spec: ParameterSpec): ValidationResult {
  if (value === null || value === undefined) {
    return { valid: false, error: 'Value is required' };
  }

  const strValue = String(value);

  if (!strValue.trim()) {
    return { valid: false, error: 'Value cannot be empty or whitespace only' };
  }

  return { valid: true };
}

/**
 * Validates a boolean parameter value
 */
export function validateBoolean(value: unknown, _spec: ParameterSpec): ValidationResult {
  if (value === null || value === undefined) {
    return { valid: false, error: 'Value is required' };
  }

  if (typeof value !== 'boolean') {
    return { valid: false, error: 'Value must be true or false' };
  }

  return { valid: true };
}

/**
 * Validates a choice parameter value against its spec
 */
export function validateChoice(value: unknown, spec: ParameterSpec): ValidationResult {
  if (value === null || value === undefined || value === '') {
    return { valid: false, error: 'Value is required' };
  }

  if (!spec.choices || spec.choices.length === 0) {
    return { valid: false, error: 'No choices defined for this parameter' };
  }

  const strValue = String(value);

  if (!spec.choices.includes(strValue)) {
    return {
      valid: false,
      error: `Value must be one of: ${spec.choices.join(', ')}`,
    };
  }

  return { valid: true };
}

/**
 * Validates a list parameter value against its spec
 */
export function validateList(value: unknown, spec: ParameterSpec): ValidationResult {
  if (value === null || value === undefined || value === '') {
    return { valid: false, error: 'Value is required' };
  }

  let arrayValue: unknown[];

  // Parse JSON if it's a string
  if (typeof value === 'string') {
    try {
      arrayValue = JSON.parse(value);
    } catch {
      return { valid: false, error: 'Value must be valid JSON array' };
    }
  } else {
    arrayValue = value as unknown[];
  }

  if (!Array.isArray(arrayValue)) {
    return { valid: false, error: 'Value must be an array' };
  }

  // Check length constraint
  if (spec.length !== undefined && arrayValue.length !== spec.length) {
    return {
      valid: false,
      error: `Array must have exactly ${spec.length} elements`,
    };
  }

  // Validate element types
  if (spec.element_type) {
    for (let i = 0; i < arrayValue.length; i++) {
      const element = arrayValue[i];
      const elementValidation = validateListElement(element, spec.element_type, i, spec);

      if (!elementValidation.valid) {
        return elementValidation;
      }
    }
  }

  return { valid: true };
}

/**
 * Validates a single element of a list
 */
function validateListElement(
  element: unknown,
  elementType: string,
  index: number,
  spec: ParameterSpec
): ValidationResult {
  const normalizedType = elementType.toLowerCase();

  // Check element type
  switch (normalizedType) {
    case 'int':
    case 'integer':
      if (!Number.isInteger(element)) {
        return {
          valid: false,
          error: `Element ${index} must be an integer`,
        };
      }
      break;

    case 'float':
    case 'number':
    case 'double':
      if (typeof element !== 'number' || isNaN(element)) {
        return {
          valid: false,
          error: `Element ${index} must be a number`,
        };
      }
      break;

    case 'str':
    case 'string':
      if (typeof element !== 'string') {
        return {
          valid: false,
          error: `Element ${index} must be a string`,
        };
      }
      break;

    case 'bool':
    case 'boolean':
      if (typeof element !== 'boolean') {
        return {
          valid: false,
          error: `Element ${index} must be a boolean`,
        };
      }
      break;

    default:
      // Unknown element type, skip validation
      break;
  }

  // Check per-element bounds for numeric types
  if (
    (normalizedType === 'int' ||
      normalizedType === 'integer' ||
      normalizedType === 'float' ||
      normalizedType === 'number' ||
      normalizedType === 'double') &&
    typeof element === 'number'
  ) {
    // Check min bounds (array of per-element minimums)
    if (Array.isArray(spec.min) && spec.min[index] !== undefined) {
      if (element < spec.min[index]) {
        return {
          valid: false,
          error: `Element ${index} must be at least ${spec.min[index]}`,
        };
      }
    }

    // Check max bounds (array of per-element maximums)
    if (Array.isArray(spec.max) && spec.max[index] !== undefined) {
      if (element > spec.max[index]) {
        return {
          valid: false,
          error: `Element ${index} must be at most ${spec.max[index]}`,
        };
      }
    }
  }

  return { valid: true };
}

/**
 * Validates a dict parameter value
 */
export function validateDict(value: unknown, _spec: ParameterSpec): ValidationResult {
  if (value === null || value === undefined || value === '') {
    return { valid: false, error: 'Value is required' };
  }

  let objValue: unknown;

  // Parse JSON if it's a string
  if (typeof value === 'string') {
    try {
      objValue = JSON.parse(value);
    } catch {
      return { valid: false, error: 'Value must be valid JSON object' };
    }
  } else {
    objValue = value;
  }

  if (typeof objValue !== 'object' || objValue === null || Array.isArray(objValue)) {
    return { valid: false, error: 'Value must be an object' };
  }

  return { valid: true };
}

/**
 * Main validation function that routes to the appropriate validator
 */
export function validateParameter(value: unknown, spec: ParameterSpec): ValidationResult {
  const normalizedType = spec.type.toLowerCase();

  switch (normalizedType) {
    case 'int':
    case 'integer':
    case 'float':
    case 'number':
    case 'double':
      return validateNumeric(value, spec);

    case 'str':
    case 'string':
      return validateString(value, spec);

    case 'bool':
    case 'boolean':
      return validateBoolean(value, spec);

    case 'choice':
      return validateChoice(value, spec);

    case 'list':
      return validateList(value, spec);

    case 'dict':
    case 'dictionary':
      return validateDict(value, spec);

    default:
      // Unknown type, skip validation
      return { valid: true };
  }
}
