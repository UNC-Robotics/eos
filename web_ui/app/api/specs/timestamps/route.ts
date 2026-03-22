import { NextResponse } from 'next/server';
import { db } from '@/lib/db/client';
import { definitions } from '@/lib/db/schema';
import { inArray } from 'drizzle-orm';

/**
 * GET /api/specs/timestamps
 * Returns updatedAt timestamps for task and lab definitions.
 * Lightweight check so the client can detect changes without fetching full specs.
 */
export async function GET() {
  const rows = await db
    .select({
      type: definitions.type,
      name: definitions.name,
      updatedAt: definitions.updatedAt,
    })
    .from(definitions)
    .where(inArray(definitions.type, ['task', 'lab']));

  const timestamps: Record<string, string> = {};
  for (const row of rows) {
    timestamps[`${row.type}:${row.name}`] = row.updatedAt.toISOString();
  }

  return NextResponse.json(timestamps);
}
