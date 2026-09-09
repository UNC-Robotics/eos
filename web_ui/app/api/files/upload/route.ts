import type { NextRequest } from 'next/server';
import { uploadFile } from '@/lib/s3/client';
import { requireRoleResponse } from '@/lib/auth/authz';

export async function POST(request: NextRequest) {
  const denied = await requireRoleResponse('SUBMITTER');
  if (denied) return denied;
  try {
    const formData = await request.formData();
    const file = formData.get('file') as File | null;
    const key = formData.get('key') as string | null;

    if (!file || !key) {
      return Response.json({ error: 'Missing file or key' }, { status: 400 });
    }

    const buffer = Buffer.from(await file.arrayBuffer());
    await uploadFile(key, buffer, file.type || 'application/octet-stream');

    return Response.json({ success: true, key });
  } catch (error) {
    console.error('Upload error:', error);
    return Response.json({ error: error instanceof Error ? error.message : 'Upload failed' }, { status: 500 });
  }
}
