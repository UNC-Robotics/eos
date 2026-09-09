import { NextRequest, NextResponse } from 'next/server';
import yaml from 'js-yaml';
import { requireRoleResponse } from '@/lib/auth/authz';
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

// Reject path traversal, leading/trailing slash, empty segments, '.' / '..'.
function isSafeRelPath(p: string): boolean {
  if (!p || p.startsWith('/') || p.endsWith('/')) return false;
  return p.split('/').every((seg) => seg.length > 0 && seg !== '.' && seg !== '..');
}

// Parse `[ 'packages', pkg, type, ...entityName ]`. entityName may span multiple segments.
function parseEntityPath(
  segments: string[]
): { packageName: string; entityType: EntityType; entityName: string } | null {
  if (segments.length < 4 || segments[0] !== 'packages') return null;
  const entityName = segments.slice(3).join('/');
  if (!isSafeRelPath(entityName)) return null;
  return { packageName: segments[1], entityType: segments[2] as EntityType, entityName };
}

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
  const denied = await requireRoleResponse('VIEWER');
  if (denied) return denied;
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

    // GET /api/filesystem/packages/[packageName]/[entityType]/[...entityName] - Read entity files
    const entity = parseEntityPath(pathSegments);
    if (entity) {
      const { packageName, entityType, entityName } = entity;

      // Lightweight mtime-only check (no file reads)
      const url = new URL(_request.url);
      if (url.searchParams.has('mtimes')) {
        const mtime = await getEntityMtimeOnly(packageName, entityType, entityName);
        if (mtime === null) {
          return NextResponse.json({ error: 'Entity not found' }, { status: 404 });
        }
        return NextResponse.json({ mtime });
      }

      const files = await readEntityFiles(packageName, entityType, entityName);
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
  const denied = await requireRoleResponse('EDITOR');
  if (denied) return denied;
  try {
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path || [];

    // PUT /api/filesystem/packages/[packageName]/[entityType]/[...entityName] - Write entity files
    const entity = parseEntityPath(pathSegments);
    if (entity) {
      const body: WriteFilesRequest = await request.json();
      const result = await writeEntityFiles(entity.packageName, entity.entityType, entity.entityName, body);

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
  const denied = await requireRoleResponse('EDITOR');
  if (denied) return denied;
  try {
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path || [];

    // POST /api/filesystem/packages/[packageName]/[entityType] - Create new entity
    if (pathSegments.length === 3 && pathSegments[0] === 'packages') {
      const [, packageName, entityType] = pathSegments;
      const body: { entityName: string } = await request.json();
      if (!isSafeRelPath(body.entityName)) {
        return NextResponse.json({ error: 'Invalid entity name' }, { status: 400 });
      }
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
  const denied = await requireRoleResponse('EDITOR');
  if (denied) return denied;
  try {
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path || [];

    // DELETE /api/filesystem/packages/[packageName]/[entityType]/[...entityName] - Delete entity
    const entity = parseEntityPath(pathSegments);
    if (entity) {
      await deleteEntity(entity.packageName, entity.entityType, entity.entityName);
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
  const denied = await requireRoleResponse('EDITOR');
  if (denied) return denied;
  try {
    const resolvedParams = await params;
    const pathSegments = resolvedParams.path || [];

    // PATCH /api/filesystem/packages/[packageName]/[entityType]/[...entityName] - Rename entity
    const entity = parseEntityPath(pathSegments);
    if (entity) {
      const body: { newName: string } = await request.json();
      if (!isSafeRelPath(body.newName)) {
        return NextResponse.json({ error: 'Invalid new name' }, { status: 400 });
      }
      await renameEntity(entity.packageName, entity.entityType, entity.entityName, body.newName);
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
