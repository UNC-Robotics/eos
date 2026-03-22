/**
 * Shared formatting helpers for MCP tool responses.
 * Tools return human-readable text rather than raw JSON.
 */

export function formatDate(date: Date | string | null | undefined): string {
  if (!date) return 'N/A';
  const d = typeof date === 'string' ? new Date(date) : date;
  return d
    .toISOString()
    .replace('T', ' ')
    .replace(/\.\d{3}Z$/, ' UTC');
}

export function formatDuration(start: Date | string | null | undefined, end: Date | string | null | undefined): string {
  if (!start || !end) return 'N/A';
  const s = typeof start === 'string' ? new Date(start) : start;
  const e = typeof end === 'string' ? new Date(end) : end;
  const ms = e.getTime() - s.getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 3_600_000) return `${(ms / 60_000).toFixed(1)}m`;
  return `${(ms / 3_600_000).toFixed(1)}h`;
}

export function formatPagination(total: number, limit: number, offset: number): string {
  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  return `Showing ${from}-${to} of ${total}`;
}

/** Format an array of objects as an ASCII table */
export function formatTable(rows: Record<string, unknown>[], columns?: string[]): string {
  if (rows.length === 0) return '(no rows)';

  const maxColWidth = 60;
  const cols = columns ?? Object.keys(rows[0]);

  const truncate = (s: string) => (s.length > maxColWidth ? s.slice(0, maxColWidth - 1) + '…' : s);

  // Compute column widths (capped)
  const widths = cols.map((col) => {
    const values = rows.map((r) => truncate(String(r[col] ?? '')));
    return Math.max(col.length, ...values.map((v) => v.length));
  });

  const header = cols.map((c, i) => c.padEnd(widths[i])).join(' | ');
  const separator = widths.map((w) => '-'.repeat(w)).join('-+-');
  const body = rows
    .map((row) => cols.map((c, i) => truncate(String(row[c] ?? '')).padEnd(widths[i])).join(' | '))
    .join('\n');

  return `${header}\n${separator}\n${body}`;
}

/** Wrap text content for MCP tool response */
export function textResult(text: string): { content: [{ type: 'text'; text: string }] } {
  return { content: [{ type: 'text' as const, text }] };
}

/** Wrap error content for MCP tool response */
export function errorResult(message: string): { content: [{ type: 'text'; text: string }]; isError: true } {
  return { content: [{ type: 'text' as const, text: `Error: ${message}` }], isError: true };
}
