import Papa from 'papaparse';

type ProtocolRunParams = Array<Record<string, Record<string, unknown>>>;

/**
 * Coerce a string value to its most likely JS type.
 * Empty/whitespace → undefined (omitted), numeric strings → number,
 * "true"/"false" → boolean, otherwise kept as string.
 */
function coerceValue(raw: string): unknown | undefined {
  const trimmed = raw.trim();
  if (trimmed === '') return undefined;

  // Boolean
  if (trimmed.toLowerCase() === 'true') return true;
  if (trimmed.toLowerCase() === 'false') return false;

  // Number (reject things like "0x10", empty after trim already handled)
  const num = Number(trimmed);
  if (!Number.isNaN(num) && trimmed !== '') return num;

  return trimmed;
}

/**
 * Parse CSV text into the protocol run parameters format expected by the backend.
 *
 * Column headers use dot notation: `task_name.param_name`.
 * Each row is one protocol run. Empty cells are omitted (supports optional params).
 *
 * Example CSV:
 *   task1.temp,task1.pressure,task2.speed
 *   80,100,50
 *   90,110,
 *
 * Result:
 *   [
 *     {"task1": {"temp": 80, "pressure": 100}, "task2": {"speed": 50}},
 *     {"task1": {"temp": 90, "pressure": 110}}
 *   ]
 */
export function parseProtocolRunParametersCsv(csv: string): ProtocolRunParams {
  const result = Papa.parse<Record<string, string>>(csv.trim(), {
    header: true,
    skipEmptyLines: true,
  });

  if (result.errors.length > 0) {
    const firstError = result.errors[0];
    throw new Error(`CSV parse error (row ${(firstError.row ?? 0) + 1}): ${firstError.message}`);
  }

  const headers = result.meta.fields ?? [];
  if (headers.length === 0) {
    throw new Error('CSV has no columns');
  }

  // Validate dot notation headers
  for (const header of headers) {
    if (!header.includes('.')) {
      throw new Error(`Invalid column header "${header}": expected dot notation "task_name.param_name"`);
    }
    const parts = header.split('.');
    if (parts.length !== 2 || !parts[0] || !parts[1]) {
      throw new Error(`Invalid column header "${header}": expected exactly "task_name.param_name"`);
    }
  }

  if (result.data.length === 0) {
    throw new Error('CSV has headers but no data rows');
  }

  return result.data.map((row) => {
    const protocolRun: Record<string, Record<string, unknown>> = {};

    for (const header of headers) {
      const rawValue = row[header];
      if (rawValue === undefined || rawValue === null) continue;

      const value = coerceValue(rawValue);
      if (value === undefined) continue; // empty cell → omit

      const [taskName, paramName] = header.split('.');
      if (!protocolRun[taskName]) {
        protocolRun[taskName] = {};
      }
      protocolRun[taskName][paramName] = value;
    }

    return protocolRun;
  });
}

/**
 * Detect whether a string is JSON or CSV.
 */
export function detectFormat(text: string): 'json' | 'csv' | 'unknown' {
  const trimmed = text.trim();
  if (trimmed.startsWith('[') || trimmed.startsWith('{')) return 'json';
  // CSV heuristic: has newlines and dot-notation headers in the first line
  const firstLine = trimmed.split('\n')[0];
  if (firstLine && firstLine.includes('.') && firstLine.includes(',')) return 'csv';
  // Single-column CSV (rare but valid)
  if (firstLine && firstLine.includes('.') && trimmed.includes('\n')) return 'csv';
  return 'unknown';
}

/**
 * Parse protocol run parameters from either JSON or CSV text.
 * Auto-detects the format. Throws descriptive errors on invalid input.
 */
export function parseProtocolRunParameters(text: string): ProtocolRunParams {
  const format = detectFormat(text);

  if (format === 'json') {
    try {
      return JSON.parse(text);
    } catch {
      throw new Error('Invalid JSON in protocol run parameters');
    }
  }

  if (format === 'csv') {
    return parseProtocolRunParametersCsv(text);
  }

  // Unknown format — try JSON first, then CSV
  try {
    return JSON.parse(text);
  } catch {
    try {
      return parseProtocolRunParametersCsv(text);
    } catch {
      throw new Error(
        'Could not parse protocol run parameters as JSON or CSV. ' +
          'JSON should be an array like [{"task": {"param": value}}]. ' +
          'CSV should have dot-notation headers like "task.param".'
      );
    }
  }
}
