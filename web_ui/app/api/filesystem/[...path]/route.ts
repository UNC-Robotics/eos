import { NextRequest, NextResponse } from 'next/server';
import yaml from 'js-yaml';
import type { EntityType, ValidationResult, WriteFilesRequest } from '@/lib/types/filesystem';
import {
  scanPackages,
  getPackageTree,
  readEntityFiles,
  writeEntityFiles,
  getEntityMtimeOnly,
  createEntity,
  deleteEntity,
  renameEntity,
} from '@/lib/filesystem/operations';

// Validate YAML
function validateYaml(content: string): ValidationResult {
  const errors: Array<{ line?: number; column?: number; message: string; severity: 'error' | 'warning' }> = [];

  try {
    yaml.load(content);
  } catch (error: unknown) {
    const err = error as { mark?: { line?: number; column?: number }; message?: string };
    errors.push({
      line: err.mark?.line,
      column: err.mark?.column,
      message: err.message || 'YAML parsing error',
      severity: 'error' as const,
    });
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

// Main route handler
export async function GET(_request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  try {
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path || [];

    // GET /api/filesystem/packages - List all packages
    if (pathSegments.length === 1 && pathSegments[0] === 'packages') {
      const packages = await scanPackages();
      return NextResponse.json(packages);
    }

    // GET /api/filesystem/packages/[packageName] - Get package tree
    if (pathSegments.length === 2 && pathSegments[0] === 'packages') {
      const packageName = pathSegments[1];
      const tree = await getPackageTree(packageName);
      return NextResponse.json(tree);
    }

    // GET /api/filesystem/packages/[packageName]/[entityType]/[entityName] - Read entity files
    if (pathSegments.length === 4 && pathSegments[0] === 'packages') {
      const [, packageName, entityType, entityName] = pathSegments;

      // Lightweight mtime-only check (no file reads)
      const url = new URL(_request.url);
      if (url.searchParams.has('mtimes')) {
        const mtime = await getEntityMtimeOnly(packageName, entityType as EntityType, entityName);
        if (mtime === null) {
          return NextResponse.json({ error: 'Entity not found' }, { status: 404 });
        }
        return NextResponse.json({ mtime });
      }

      const files = await readEntityFiles(packageName, entityType as EntityType, entityName);
      if (!files) {
        return NextResponse.json({ error: 'Entity not found' }, { status: 404 });
      }
      return NextResponse.json(files);
    }

    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  } catch (error) {
    console.error('GET error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Internal server error' },
      { status: 500 }
    );
  }
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  try {
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path || [];

    // PUT /api/filesystem/packages/[packageName]/[entityType]/[entityName] - Write entity files
    if (pathSegments.length === 4 && pathSegments[0] === 'packages') {
      const [, packageName, entityType, entityName] = pathSegments;
      const body: WriteFilesRequest = await request.json();
      const result = await writeEntityFiles(packageName, entityType as EntityType, entityName, body);

      if (result.conflict) {
        return NextResponse.json({ error: 'File modified externally', mtime: result.mtime }, { status: 409 });
      }

      return NextResponse.json({ success: true, mtime: result.mtime });
    }

    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  } catch (error) {
    console.error('PUT error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Internal server error' },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  try {
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path || [];

    // POST /api/filesystem/packages/[packageName]/[entityType] - Create new entity
    if (pathSegments.length === 3 && pathSegments[0] === 'packages') {
      const [, packageName, entityType] = pathSegments;
      const body: { entityName: string } = await request.json();
      await createEntity(packageName, entityType as EntityType, body.entityName);
      return NextResponse.json({ success: true });
    }

    // POST /api/filesystem/validate - Validate YAML
    if (pathSegments.length === 1 && pathSegments[0] === 'validate') {
      const body: { content: string } = await request.json();
      const result = validateYaml(body.content);
      return NextResponse.json(result);
    }

    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  } catch (error) {
    console.error('POST error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Internal server error' },
      { status: 500 }
    );
  }
}

export async function DELETE(_request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  try {
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path || [];

    // DELETE /api/filesystem/packages/[packageName]/[entityType]/[entityName] - Delete entity
    if (pathSegments.length === 4 && pathSegments[0] === 'packages') {
      const [, packageName, entityType, entityName] = pathSegments;
      await deleteEntity(packageName, entityType as EntityType, entityName);
      return NextResponse.json({ success: true });
    }

    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  } catch (error) {
    console.error('DELETE error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Internal server error' },
      { status: 500 }
    );
  }
}

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  try {
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path || [];

    // PATCH /api/filesystem/packages/[packageName]/[entityType]/[entityName] - Rename entity
    if (pathSegments.length === 4 && pathSegments[0] === 'packages') {
      const [, packageName, entityType, entityName] = pathSegments;
      const body: { newName: string } = await request.json();
      await renameEntity(packageName, entityType as EntityType, entityName, body.newName);
      return NextResponse.json({ success: true });
    }

    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  } catch (error) {
    console.error('PATCH error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Internal server error' },
      { status: 500 }
    );
  }
}
