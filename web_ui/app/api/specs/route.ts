import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db/client';
import { definitions } from '@/lib/db/schema';
import { eq, and, inArray } from 'drizzle-orm';
import type { TaskSpec as DbTaskSpec, LabSpec } from '@/lib/api/specs';
import type { TaskSpec } from '@/lib/types/protocol';
import { transformTaskSpec } from '@/lib/api/taskSpecTransform';

/**
 * GET /api/specs?tasks=TypeA,TypeB&labs=lab1,lab2
 * Returns full specs for the requested task types and lab names.
 * Task specs are transformed to match the editor's TaskSpec format.
 */
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const taskTypes = searchParams.get('tasks')?.split(',').filter(Boolean) ?? [];
  const labNames = searchParams.get('labs')?.split(',').filter(Boolean) ?? [];

  const result: {
    taskSpecs?: Record<string, TaskSpec>;
    labSpecs?: Record<string, LabSpec>;
  } = {};

  if (taskTypes.length > 0) {
    const rows = await db
      .select()
      .from(definitions)
      .where(and(eq(definitions.type, 'task'), inArray(definitions.name, taskTypes)));

    result.taskSpecs = {};
    for (const row of rows) {
      const spec = row.data as DbTaskSpec;
      const transformed = transformTaskSpec(spec.type, { ...spec, packageName: row.packageName });
      result.taskSpecs[transformed.type] = transformed;
    }
  }

  if (labNames.length > 0) {
    const rows = await db
      .select()
      .from(definitions)
      .where(and(eq(definitions.type, 'lab'), inArray(definitions.name, labNames)));

    result.labSpecs = {};
    for (const row of rows) {
      result.labSpecs[row.name] = row.data as LabSpec;
    }
  }

  return NextResponse.json(result);
}
