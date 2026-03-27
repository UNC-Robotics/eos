import type {
  DomainInput,
  DomainOutput,
  DomainConstraint,
  DomainValue,
} from '@/features/campaigns/components/DomainEditor';
import type { OptimizerDefaults } from '@/lib/types/api';

// ============================================================================
// Types
// ============================================================================

export interface OptimizerConfig {
  // Domain
  inputs: DomainInput[];
  outputs: DomainOutput[];
  constraints: DomainConstraint[];
  // Bayesian
  acquisition_function: Record<string, unknown> | null;
  surrogate_specs: Record<string, unknown> | null;
  num_initial_samples: number;
  initial_sampling_method: string;
  // Strategy mix
  p_bayesian: number;
  p_ai: number;
  // AI
  ai_model: string;
  ai_api_key?: string;
  ai_retries: number;
  ai_history_size: number;
  ai_model_settings: Record<string, unknown> | null;
  ai_additional_parameters: string[] | null;
  ai_additional_context: string | null;
}

// ============================================================================
// Standard pattern detection
// ============================================================================

/**
 * Check if optimizer.py follows the standard pattern (no custom code).
 * Standard pattern: imports + eos_create_campaign_optimizer() + constructor_args + return.
 */
export function isStandardOptimizerPy(code: string): boolean {
  if (!code.trim()) return false;

  // Must contain the main function
  if (!code.includes('def eos_create_campaign_optimizer')) return false;

  // Must have a return statement
  if (!/return\s+constructor_args/.test(code)) return false;

  // Count function definitions — should only have one (eos_create_campaign_optimizer)
  const funcDefs = code.match(/^(?!#).*\bdef\s+\w+/gm) || [];
  if (funcDefs.length > 1) return false;

  // No class definitions
  if (/^(?!#).*\bclass\s+\w+/m.test(code)) return false;

  return true;
}

// ============================================================================
// Code generation
// ============================================================================

/** Group a set of type names by their module using a type→import-line map, returning grouped import lines. */
function groupImportsByModule(types: Iterable<string>, moduleMap: Record<string, string>): string[] {
  const grouped = new Map<string, string[]>();
  for (const t of types) {
    const importLine = moduleMap[t];
    if (!importLine) continue;
    const module = importLine.split(' import ')[0];
    const existing = grouped.get(module) || [];
    existing.push(t);
    grouped.set(module, existing);
  }
  return Array.from(grouped, ([module, names]) => `${module} import ${names.join(', ')}`);
}

/** Collect all unique import types needed from the config */
function collectImports(config: OptimizerConfig): {
  bofireImports: string[];
  eosImports: string[];
} {
  const bofireImports: string[] = [];

  // Acquisition function
  if (config.acquisition_function) {
    const acqType = (config.acquisition_function.type as string) ?? 'qLogNEI';
    bofireImports.push(`from bofire.data_models.acquisition_functions.acquisition_function import ${acqType}`);
  }

  // SamplingMethodEnum
  bofireImports.push('from bofire.data_models.enum import SamplingMethodEnum');

  // Feature types (inputs + outputs)
  const featureTypes = new Set([...config.inputs.map((i) => i.type), ...config.outputs.map((o) => o.type)]);
  bofireImports.push(
    ...groupImportsByModule(featureTypes, {
      ContinuousInput: 'from bofire.data_models.features.continuous import ContinuousInput',
      ContinuousOutput: 'from bofire.data_models.features.continuous import ContinuousOutput',
      DiscreteInput: 'from bofire.data_models.features.discrete import DiscreteInput',
      CategoricalInput: 'from bofire.data_models.features.categorical import CategoricalInput',
      CategoricalOutput: 'from bofire.data_models.features.categorical import CategoricalOutput',
    })
  );

  // Objectives
  const objectives = new Set(config.outputs.map((o) => o.objective.type));
  bofireImports.push(
    ...groupImportsByModule(objectives, {
      MinimizeObjective: 'from bofire.data_models.objectives.identity import MinimizeObjective',
      MaximizeObjective: 'from bofire.data_models.objectives.identity import MaximizeObjective',
      CloseToTargetObjective: 'from bofire.data_models.objectives.close_to_target import CloseToTargetObjective',
    })
  );

  // Constraints
  const constraintTypes = new Set(config.constraints.map((c) => c.type));
  bofireImports.push(
    ...groupImportsByModule(constraintTypes, {
      LinearEqualityConstraint: 'from bofire.data_models.constraints.linear import LinearEqualityConstraint',
      LinearInequalityConstraint: 'from bofire.data_models.constraints.linear import LinearInequalityConstraint',
    })
  );

  // Surrogate specs
  if (config.surrogate_specs) {
    bofireImports.push('from bofire.data_models.surrogates.api import BotorchSurrogates');
  }

  const eosImports = [
    'from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer',
    'from eos.optimization.beacon_optimizer import BeaconOptimizer',
  ];

  return { bofireImports, eosImports };
}

/** Generate a Python constructor call for a domain input */
function genInput(inp: DomainInput): string {
  switch (inp.type) {
    case 'ContinuousInput': {
      const parts = [`key=${JSON.stringify(inp.key)}`];
      if (inp.bounds) parts.push(`bounds=(${inp.bounds[0]}, ${inp.bounds[1]})`);
      if (inp.stepsize != null) parts.push(`stepsize=${inp.stepsize}`);
      return `ContinuousInput(${parts.join(', ')})`;
    }
    case 'DiscreteInput': {
      const vals = (inp.values ?? []).join(', ');
      return `DiscreteInput(key=${JSON.stringify(inp.key)}, values=[${vals}])`;
    }
    case 'CategoricalInput': {
      const cats = (inp.categories ?? []).map((c) => JSON.stringify(c)).join(', ');
      const parts = [`key=${JSON.stringify(inp.key)}`, `categories=[${cats}]`];
      if (inp.allowed) parts.push(`allowed=[${inp.allowed.map((b) => (b ? 'True' : 'False')).join(', ')}]`);
      return `CategoricalInput(${parts.join(', ')})`;
    }
  }
}

/** Generate a Python constructor call for a domain output */
function genOutput(out: DomainOutput): string {
  const objParts = [`w=${formatFloat(out.objective.w)}`];
  if (out.objective.type === 'CloseToTargetObjective') {
    if (out.objective.target_value != null) objParts.push(`target_value=${formatFloat(out.objective.target_value)}`);
    if (out.objective.exponent != null) objParts.push(`exponent=${formatFloat(out.objective.exponent)}`);
  }
  const objStr = `${out.objective.type}(${objParts.join(', ')})`;

  const parts = [`key=${JSON.stringify(out.key)}`, `objective=${objStr}`];
  if (out.type === 'CategoricalOutput' && out.categories) {
    parts.push(`categories=[${out.categories.map((c) => JSON.stringify(c)).join(', ')}]`);
  }
  return `${out.type}(${parts.join(', ')})`;
}

/** Generate a Python constructor call for a constraint */
function genConstraint(c: DomainConstraint): string {
  const feats = c.features.map((f) => JSON.stringify(f)).join(', ');
  const coeffs = c.coefficients.map((v) => formatFloat(v)).join(', ');
  return `${c.type}(features=[${feats}], coefficients=[${coeffs}], rhs=${formatFloat(c.rhs)})`;
}

/** Ensure a number is formatted as a Python float (e.g., 1.0 not 1) */
function formatFloat(n: number): string {
  const s = String(n);
  return s.includes('.') ? s : `${s}.0`;
}

/** Format a dict literal from a JS object */
function formatPythonDict(obj: Record<string, unknown>, indent: number): string {
  const entries = Object.entries(obj);
  if (entries.length === 0) return '{}';

  const pad = ' '.repeat(indent);
  const innerPad = ' '.repeat(indent + 4);
  const lines = entries.map(([key, value]) => {
    const pyValue = typeof value === 'string' ? `"${value}"` : String(value);
    return `${innerPad}"${key}": ${pyValue},`;
  });
  return `{\n${lines.join('\n')}\n${pad}}`;
}

/** Map frontend sampling method strings to Python enum values */
function samplingMethodEnum(method: string): string {
  const map: Record<string, string> = {
    SOBOL: 'SamplingMethodEnum.SOBOL',
    UNIFORM: 'SamplingMethodEnum.UNIFORM',
    LHS: 'SamplingMethodEnum.LHS',
  };
  return map[method] || 'SamplingMethodEnum.SOBOL';
}

/**
 * Generate a complete optimizer.py from structured config.
 */
export function generateOptimizerPython(config: OptimizerConfig): string {
  const { bofireImports, eosImports } = collectImports(config);

  const lines: string[] = [];

  // Imports
  for (const imp of bofireImports) {
    lines.push(imp);
  }
  lines.push('');
  for (const imp of eosImports) {
    lines.push(imp);
  }

  lines.push('');
  lines.push('');
  lines.push('def eos_create_campaign_optimizer() -> tuple[dict, type[AbstractSequentialOptimizer]]:');

  // constructor_args
  lines.push('    constructor_args = {');

  // Inputs
  lines.push('        "inputs": [');
  for (const inp of config.inputs) {
    lines.push(`            ${genInput(inp)},`);
  }
  lines.push('        ],');

  // Outputs
  lines.push('        "outputs": [');
  for (const out of config.outputs) {
    lines.push(`            ${genOutput(out)},`);
  }
  lines.push('        ],');

  // Constraints
  lines.push('        "constraints": [');
  for (const c of config.constraints) {
    lines.push(`            ${genConstraint(c)},`);
  }
  lines.push('        ],');

  // Acquisition function
  if (config.acquisition_function) {
    const acqType = (config.acquisition_function.type as string) ?? 'qLogNEI';
    lines.push(`        "acquisition_function": ${acqType}(),`);
  }

  // Surrogate specs
  if (config.surrogate_specs) {
    lines.push(`        "surrogate_specs": ${formatPythonDict(config.surrogate_specs as Record<string, unknown>, 8)},`);
  }

  // Bayesian params
  lines.push(`        "num_initial_samples": ${config.num_initial_samples},`);
  lines.push(`        "initial_sampling_method": ${samplingMethodEnum(config.initial_sampling_method)},`);

  // Strategy mix
  lines.push(`        "p_bayesian": ${formatFloat(config.p_bayesian)},`);
  lines.push(`        "p_ai": ${formatFloat(config.p_ai)},`);

  // AI params
  lines.push(`        "ai_model": ${JSON.stringify(config.ai_model)},`);

  // WARNING: API keys in generated code may be committed to version control.
  // Consider using environment variables instead.
  if (config.ai_api_key) {
    lines.push(`        "ai_api_key": ${JSON.stringify(config.ai_api_key)},`);
  }

  lines.push(`        "ai_retries": ${config.ai_retries},`);
  lines.push(`        "ai_history_size": ${config.ai_history_size},`);

  if (config.ai_model_settings && Object.keys(config.ai_model_settings).length > 0) {
    lines.push(`        "ai_model_settings": ${formatPythonDict(config.ai_model_settings, 8)},`);
  }

  if (config.ai_additional_parameters && config.ai_additional_parameters.length > 0) {
    const params = config.ai_additional_parameters.map((p) => `"${p}"`).join(', ');
    lines.push(`        "ai_additional_parameters": [${params}],`);
  }

  if (config.ai_additional_context) {
    lines.push(`        "ai_additional_context": ${JSON.stringify(config.ai_additional_context)},`);
  }

  lines.push('    }');
  lines.push('    return constructor_args, BeaconOptimizer');
  lines.push('');

  return lines.join('\n');
}

/**
 * Build an OptimizerConfig from the form values used in the editor panel.
 */
export function buildOptimizerConfig(overrides: Record<string, unknown>, domain: DomainValue): OptimizerConfig {
  return {
    inputs: domain.inputs,
    outputs: domain.outputs,
    constraints: domain.constraints,
    acquisition_function: (overrides.acquisition_function as Record<string, unknown> | null) ?? null,
    surrogate_specs: (overrides.surrogate_specs as Record<string, unknown> | null) ?? null,
    num_initial_samples: (overrides.num_initial_samples as number) ?? 5,
    initial_sampling_method: (overrides.initial_sampling_method as string) ?? 'SOBOL',
    p_bayesian: (overrides.p_bayesian as number) ?? 0.5,
    p_ai: (overrides.p_ai as number) ?? 0.5,
    ai_model: (overrides.ai_model as string) ?? 'claude-agent-sdk:sonnet',
    ai_api_key: (overrides.ai_api_key as string) || undefined,
    ai_retries: (overrides.ai_retries as number) ?? 3,
    ai_history_size: (overrides.ai_history_size as number) ?? 50,
    ai_model_settings: (overrides.ai_model_settings as Record<string, unknown> | null) ?? null,
    ai_additional_parameters: (overrides.ai_additional_parameters as string[] | null) ?? null,
    ai_additional_context: (overrides.ai_additional_context as string | null) ?? null,
  };
}

// ============================================================================
// Python parsing (reverse of generateOptimizerPython)
// ============================================================================

/** Extract a quoted string: key="value" → value */
function extractQuotedParam(call: string, param: string): string | undefined {
  const m = new RegExp(`${param}\\s*=\\s*"([^"]*)"`, 's').exec(call);
  return m?.[1];
}

/** Extract a numeric param: param=1.0 → 1.0 */
function extractNumericParam(call: string, param: string): number | undefined {
  const m = new RegExp(`${param}\\s*=\\s*([0-9.eE+-]+)`).exec(call);
  return m ? parseFloat(m[1]) : undefined;
}

/** Extract a tuple of two numbers: bounds=(0, 100) → [0, 100] */
function extractTuple(call: string, param: string): [number, number] | undefined {
  const m = new RegExp(`${param}\\s*=\\s*\\(\\s*([0-9.eE+-]+)\\s*,\\s*([0-9.eE+-]+)\\s*\\)`).exec(call);
  return m ? [parseFloat(m[1]), parseFloat(m[2])] : undefined;
}

/** Extract a list of numbers: values=[1, 2, 3] → [1, 2, 3] */
function extractNumberList(call: string, param: string): number[] | undefined {
  const m = new RegExp(`${param}\\s*=\\s*\\[([^\\]]*)\\]`).exec(call);
  if (!m) return undefined;
  return m[1]
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .map(Number);
}

/** Extract a list of strings: categories=["a", "b"] → ["a", "b"] */
function extractStringList(call: string, param: string): string[] | undefined {
  const m = new RegExp(`${param}\\s*=\\s*\\[([^\\]]*)\\]`).exec(call);
  if (!m) return undefined;
  const items: string[] = [];
  const strRegex = /"([^"]*)"/g;
  let sm;
  while ((sm = strRegex.exec(m[1])) !== null) {
    items.push(sm[1]);
  }
  return items.length > 0 ? items : undefined;
}

/** Extract a list of booleans: allowed=[True, False] → [true, false] */
function extractBoolList(call: string, param: string): boolean[] | undefined {
  const m = new RegExp(`${param}\\s*=\\s*\\[([^\\]]*)\\]`).exec(call);
  if (!m) return undefined;
  return m[1]
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => s === 'True');
}

/** Parse a single Python constructor call like ContinuousInput(key="x", bounds=(0, 1)) */
function parseInputCall(call: string): DomainInput | null {
  const typeMatch = /^(ContinuousInput|DiscreteInput|CategoricalInput)\(/.exec(call.trim());
  if (!typeMatch) return null;
  const type = typeMatch[1] as DomainInput['type'];
  const key = extractQuotedParam(call, 'key') ?? '';

  switch (type) {
    case 'ContinuousInput':
      return {
        type,
        key,
        bounds: extractTuple(call, 'bounds'),
        stepsize: extractNumericParam(call, 'stepsize') ?? null,
      };
    case 'DiscreteInput':
      return { type, key, values: extractNumberList(call, 'values') };
    case 'CategoricalInput':
      return {
        type,
        key,
        categories: extractStringList(call, 'categories'),
        allowed: extractBoolList(call, 'allowed'),
      };
  }
}

/** Parse a single output constructor call, handling nested objective */
function parseOutputCall(call: string): DomainOutput | null {
  const typeMatch = /^(ContinuousOutput|CategoricalOutput)\(/.exec(call.trim());
  if (!typeMatch) return null;
  const type = typeMatch[1] as DomainOutput['type'];
  const key = extractQuotedParam(call, 'key') ?? '';

  // Parse objective: objective=MaximizeObjective(w=1.0)
  const objMatch = /(MinimizeObjective|MaximizeObjective|CloseToTargetObjective)\(([^)]*)\)/.exec(call);
  const objType = (objMatch?.[1] ?? 'MinimizeObjective') as DomainOutput['objective']['type'];
  const objArgs = objMatch?.[2] ?? '';
  const w = extractNumericParam(`w=${objArgs.match(/w\s*=\s*([0-9.eE+-]+)/)?.[1] ?? '1.0'}`, 'w') ?? 1.0;

  const objective: DomainOutput['objective'] = { type: objType, w };
  if (objType === 'CloseToTargetObjective') {
    const tv = extractNumericParam(objArgs, 'target_value');
    const exp = extractNumericParam(objArgs, 'exponent');
    if (tv != null) (objective as { target_value?: number }).target_value = tv;
    if (exp != null) (objective as { exponent?: number }).exponent = exp;
  }

  const output: DomainOutput = { type, key, objective };
  if (type === 'CategoricalOutput') {
    output.categories = extractStringList(call, 'categories');
  }
  return output;
}

/** Parse a constraint constructor call */
function parseConstraintCall(call: string): DomainConstraint | null {
  const typeMatch = /^(LinearEqualityConstraint|LinearInequalityConstraint)\(/.exec(call.trim());
  if (!typeMatch) return null;
  return {
    type: typeMatch[1] as DomainConstraint['type'],
    features: extractStringList(call, 'features') ?? [],
    coefficients: extractNumberList(call, 'coefficients') ?? [],
    rhs: extractNumericParam(call, 'rhs') ?? 0,
  };
}

/** Match all top-level constructor calls within a list section like "inputs": [ ... ] */
function extractListItems(code: string, key: string): string[] {
  // Find the list content between "key": [ ... ],
  const listRegex = new RegExp(`"${key}"\\s*:\\s*\\[([\\s\\S]*?)\\]\\s*,`, 'm');
  const m = listRegex.exec(code);
  if (!m) return [];

  // Split by top-level constructor calls (TypeName(...))
  const items: string[] = [];
  const content = m[1];
  // Match constructor calls handling nested parentheses (one level deep for objectives)
  const callRegex = /(\w+)\(([^()]*(?:\([^()]*\)[^()]*)*)\)/g;
  let cm;
  while ((cm = callRegex.exec(content)) !== null) {
    items.push(cm[0]);
  }
  return items;
}

/**
 * Parse standard BeaconOptimizer Python code into OptimizerDefaults.
 * Returns null if the code can't be parsed (non-standard or malformed).
 * Only handles code generated by generateOptimizerPython or similar standard patterns.
 */
export function parseOptimizerPython(code: string): OptimizerDefaults | null {
  if (!isStandardOptimizerPy(code)) return null;

  try {
    // Extract the constructor_args block
    const argsMatch = /constructor_args\s*=\s*\{([\s\S]*)\}\s*\n\s*return\s+constructor_args/.exec(code);
    if (!argsMatch) return null;
    const argsBlock = argsMatch[1];

    // Parse domain lists
    const inputs = extractListItems(argsBlock, 'inputs')
      .map(parseInputCall)
      .filter((x): x is DomainInput => x !== null);
    const outputs = extractListItems(argsBlock, 'outputs')
      .map(parseOutputCall)
      .filter((x): x is DomainOutput => x !== null);
    const constraints = extractListItems(argsBlock, 'constraints')
      .map(parseConstraintCall)
      .filter((x): x is DomainConstraint => x !== null);

    // Parse acquisition function: "acquisition_function": qLogNEI(),
    const acqMatch = /"acquisition_function"\s*:\s*(\w+)\(\)/.exec(argsBlock);
    const acquisition_function = acqMatch ? { type: acqMatch[1] } : null;

    // Parse sampling method: SamplingMethodEnum.SOBOL
    const samplingMatch = /SamplingMethodEnum\.(\w+)/.exec(argsBlock);
    const initial_sampling_method = samplingMatch?.[1] ?? 'SOBOL';

    // Parse scalar values from "key": value patterns
    const parseScalar = (key: string, fallback: number): number => {
      const m = new RegExp(`"${key}"\\s*:\\s*([0-9.eE+-]+)`).exec(argsBlock);
      return m ? parseFloat(m[1]) : fallback;
    };

    // Parse string values from "key": "value" patterns
    const parseString = (key: string, fallback: string): string => {
      const m = new RegExp(`"${key}"\\s*:\\s*"([^"]*)"`, 's').exec(argsBlock);
      return m?.[1] ?? fallback;
    };

    // Parse nullable string
    const parseNullableString = (key: string): string | null => {
      const m = new RegExp(`"${key}"\\s*:\\s*"([^"]*)"`, 's').exec(argsBlock);
      return m?.[1] ?? null;
    };

    // Parse ai_additional_parameters: ["param1", "param2"]
    const additionalParamsMatch = new RegExp(`"ai_additional_parameters"\\s*:\\s*\\[([^\\]]*)\\]`).exec(argsBlock);
    let ai_additional_parameters: string[] | null = null;
    if (additionalParamsMatch) {
      const items: string[] = [];
      const strRegex = /"([^"]*)"/g;
      let sm;
      while ((sm = strRegex.exec(additionalParamsMatch[1])) !== null) {
        items.push(sm[1]);
      }
      if (items.length > 0) ai_additional_parameters = items;
    }

    return {
      optimizer_type: 'BeaconOptimizer',
      inputs: inputs.map((i) => ({ ...i }) as Record<string, unknown>),
      outputs: outputs.map((o) => ({ ...o }) as Record<string, unknown>),
      constraints: constraints.map((c) => ({ ...c }) as Record<string, unknown>),
      params: {
        p_bayesian: parseScalar('p_bayesian', 0.5),
        p_ai: parseScalar('p_ai', 0.5),
        ai_model: parseString('ai_model', 'claude-agent-sdk:sonnet'),
        ai_retries: parseScalar('ai_retries', 3),
        ai_history_size: parseScalar('ai_history_size', 50),
        ai_additional_context: parseNullableString('ai_additional_context'),
        num_initial_samples: parseScalar('num_initial_samples', 5),
        initial_sampling_method,
        ai_model_settings: null,
        ai_additional_parameters,
        acquisition_function,
        surrogate_specs: null,
      },
    };
  } catch {
    return null;
  }
}
