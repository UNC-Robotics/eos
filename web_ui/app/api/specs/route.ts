import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db/client';
import { definitions } from '@/lib/db/schema';
import { eq, and, inArray } from 'drizzle-orm';
import type { TaskSpec as DbTaskSpec, LabSpec } from '@/lib/api/specs';
import type { TaskSpec, ParameterSpec } from '@/lib/types/protocol';

/**
 * Transform a DB-layer TaskSpec into the editor-layer TaskSpec.
 * Must match the transformation in app/editor/page.tsx.
 */
function transformTaskSpec(type: string, spec: DbTaskSpec & { packageName: string }): TaskSpec {
  const deviceTypes = spec.devices ? Array.from(new Set(Object.values(spec.devices).map((d) => d.type))) : [];

  const inputDevices = spec.devices
    ? Object.fromEntries(Object.entries(spec.devices).map(([key, device]) => [key, { type: device.type, desc: '' }]))
    : undefined;

  const inputResources = spec.input_resources
    ? Object.fromEntries(
        Object.entries(spec.input_resources).map(([key, resource]) => [key, { type: resource.type, desc: '' }])
      )
    : {};

  const outputResources = spec.output_resources
    ? Object.fromEntries(
        Object.entries(spec.output_resources).map(([key, resource]) => [key, { type: resource.type, desc: '' }])
      )
    : {};

  return {
    type,
    desc: spec.desc || '',
    device_types: deviceTypes,
    packageName: spec.packageName,
    input_devices: inputDevices,
    output_devices: {},
    input_resources: inputResources,
    output_resources: outputResources,
    input_parameters: (spec.input_parameters as Record<string, ParameterSpec>) || {},
    output_parameters: (spec.output_parameters as Record<string, ParameterSpec>) || {},
  };
}

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
