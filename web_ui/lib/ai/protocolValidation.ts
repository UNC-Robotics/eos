import * as yaml from 'js-yaml';

export function validateYaml(yamlString: string): { valid: boolean; error?: string; parsed?: Record<string, unknown> } {
  try {
    const parsed = yaml.load(yamlString);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { valid: false, error: 'YAML must be a mapping (object), not a scalar or array' };
    }
    return { valid: true, parsed: parsed as Record<string, unknown> };
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    return { valid: false, error: errorMessage };
  }
}
