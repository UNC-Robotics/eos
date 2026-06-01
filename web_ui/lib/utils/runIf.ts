/**
 * Helpers for the `task.output` references embedded inside `run_if` expressions.
 * String literals are treated as opaque so dotted text inside quotes never matches.
 */
export interface RunIfRef {
  task: string;
  output: string;
}

const REF_RE = /\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b/g;
const STRING_LITERAL_RE = /'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"/g;

interface Segment {
  code: boolean;
  text: string;
}

/** Single linear pass that tags each character as code or string-literal content. */
function splitByStringLiterals(expression: string): Segment[] {
  const segments: Segment[] = [];
  let cursor = 0;
  for (const m of expression.matchAll(STRING_LITERAL_RE)) {
    if (m.index! > cursor) {
      segments.push({ code: true, text: expression.slice(cursor, m.index) });
    }
    segments.push({ code: false, text: m[0] });
    cursor = m.index! + m[0].length;
  }
  if (cursor < expression.length) {
    segments.push({ code: true, text: expression.slice(cursor) });
  }
  return segments;
}

export function extractRunIfRefs(expression: string | null | undefined): RunIfRef[] {
  if (!expression) return [];
  const seen = new Set<string>();
  const refs: RunIfRef[] = [];
  for (const segment of splitByStringLiterals(expression)) {
    if (!segment.code) continue;
    for (const m of segment.text.matchAll(REF_RE)) {
      const key = `${m[1]}.${m[2]}`;
      if (seen.has(key)) continue;
      seen.add(key);
      refs.push({ task: m[1], output: m[2] });
    }
  }
  return refs;
}

const REGEX_ESCAPE_RE = /[\\^$.*+?()[\]{}|]/g;
const escapeRegExp = (s: string): string => s.replace(REGEX_ESCAPE_RE, '\\$&');

/** Rewrite every `oldName.output` reference (outside string literals) to `newName.output`. */
export function rewriteRunIfExpression(
  expression: string | null | undefined,
  oldName: string,
  newName: string
): string | null {
  if (!expression) return expression ?? null;
  if (oldName === newName) return expression;
  const pattern = new RegExp(`\\b${escapeRegExp(oldName)}(\\.[A-Za-z_][A-Za-z0-9_]*)\\b`, 'g');
  const replacement = `${newName}$1`;
  return splitByStringLiterals(expression)
    .map((segment) => (segment.code ? segment.text.replace(pattern, replacement) : segment.text))
    .join('');
}

export const runIfHandleId = (consumer: string, ref: RunIfRef): string =>
  `${consumer}-input-runif-${ref.task}-${ref.output}`;
