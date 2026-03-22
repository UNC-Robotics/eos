import { z } from 'zod/v3';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { readonlyClient } from '@/lib/db/client';
import { formatTable, textResult, errorResult } from '../helpers/format';

const FORBIDDEN_KEYWORDS = [
  'INSERT',
  'UPDATE',
  'DELETE',
  'DROP',
  'ALTER',
  'TRUNCATE',
  'CREATE',
  'GRANT',
  'REVOKE',
  'COPY',
  'EXECUTE',
  'EXEC',
  'SET',
  'LOCK',
  'VACUUM',
  'REINDEX',
  'CLUSTER',
  'COMMENT',
  'PREPARE',
  'DEALLOCATE',
  'LISTEN',
  'NOTIFY',
  'LOAD',
];

const FORBIDDEN_FUNCTIONS = [
  'pg_terminate_backend',
  'pg_cancel_backend',
  'pg_reload_conf',
  'pg_rotate_logfile',
  'lo_export',
  'lo_import',
  'lo_unlink',
  'pg_read_file',
  'pg_read_binary_file',
  'pg_ls_dir',
  'pg_stat_file',
  'set_config',
  'pg_advisory_lock',
  'pg_sleep',
];

const MAX_ROWS = 100;
const TIMEOUT_MS = 10_000;

function validateQuery(sql: string): string | null {
  const trimmed = sql.trim().replace(/;+$/, '').trim();
  const upper = trimmed.toUpperCase();

  // Must start with SELECT or WITH
  if (!upper.startsWith('SELECT') && !upper.startsWith('WITH')) {
    return 'Only SELECT and WITH (CTE) queries are allowed.';
  }

  // Check for forbidden keywords (word boundary detection)
  for (const keyword of FORBIDDEN_KEYWORDS) {
    const pattern = new RegExp(`\\b${keyword}\\b`, 'i');
    if (pattern.test(trimmed)) {
      return `Forbidden keyword detected: ${keyword}. Only read-only queries are allowed.`;
    }
  }

  // Check for dangerous built-in functions
  for (const func of FORBIDDEN_FUNCTIONS) {
    const pattern = new RegExp(`\\b${func}\\s*\\(`, 'i');
    if (pattern.test(trimmed)) {
      return `Forbidden function detected: ${func}. This function is not allowed.`;
    }
  }

  return null;
}

export function registerSqlTools(server: McpServer) {
  server.registerTool(
    'query_database',
    {
      title: 'Query Database',
      description: `Execute a read-only SQL query against the EOS database. Only SELECT/WITH queries allowed. Results limited to ${MAX_ROWS} rows with ${TIMEOUT_MS / 1000}s timeout. Available tables: tasks, experiments, campaigns, campaign_samples, definitions.`,
      inputSchema: {
        sql: z.string().describe('SQL query (SELECT or WITH only)'),
      },
    },
    async ({ sql }) => {
      const validationError = validateQuery(sql);
      if (validationError) return errorResult(validationError);

      const limited = sql.trim().replace(/;+$/, '');
      const query = `SELECT * FROM (${limited}) AS _mcp_q LIMIT ${MAX_ROWS}`;

      try {
        const result = await Promise.race([
          readonlyClient.unsafe(query),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error('Query timed out after 10 seconds')), TIMEOUT_MS)
          ),
        ]);

        const rows = result as Record<string, unknown>[];
        if (rows.length === 0) return textResult('Query returned no rows.');

        const table = formatTable(rows);
        const suffix = rows.length === MAX_ROWS ? `\n\n(Results limited to ${MAX_ROWS} rows)` : '';
        return textResult(`${rows.length} row(s) returned:\n\n${table}${suffix}`);
      } catch (e) {
        return errorResult(`Query failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  );
}
