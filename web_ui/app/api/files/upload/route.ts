import type { NextRequest } from 'next/server';
import { uploadFile } from '@/lib/s3/client';

export async function POST(request: NextRequest) {
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
