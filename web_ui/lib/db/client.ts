/**
 * Drizzle Database Client
 */

import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from './schema';
import { env } from '@/lib/env';

const connectionString = env.DATABASE_URL;

// Create postgres client with connection pooling
const client = postgres(connectionString, {
  max: process.env.NODE_ENV === 'production' ? 10 : 5,
  idle_timeout: 20,
  connect_timeout: 10,
});

// Read-only client for MCP SQL queries (defense-in-depth).
// Appends the default_transaction_read_only GUC so Postgres rejects writes at the session level.
const readonlyUrl = new URL(connectionString);
readonlyUrl.searchParams.set('options', '-c default_transaction_read_only=on');
const readonlyClient = postgres(readonlyUrl.toString(), {
  max: 2,
  idle_timeout: 20,
  connect_timeout: 10,
});

// Create drizzle instance with schema
export const db = drizzle(client, { schema });

// Export for cleanup/testing
export { client, readonlyClient };
