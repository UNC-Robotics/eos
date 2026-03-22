import type { NextRequest } from 'next/server';
import { getFileStream } from '@/lib/s3/client';

export async function GET(_request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  try {
    const { path } = await params;
    const key = path.join('/');

    const { stream, size, contentType } = await getFileStream(key);

    const fileName = key.split('/').pop() || 'download';

    // Convert Node.js Readable to a web ReadableStream
    const webStream = new ReadableStream({
      start(controller) {
        stream.on('data', (chunk: Buffer) => {
          controller.enqueue(new Uint8Array(chunk));
        });
        stream.on('end', () => {
          controller.close();
        });
        stream.on('error', (err: Error) => {
          controller.error(err);
        });
      },
    });

    return new Response(webStream, {
      headers: {
        'Content-Type': contentType,
        'Content-Length': String(size),
        'Content-Disposition': `attachment; filename="${encodeURIComponent(fileName)}"`,
      },
    });
  } catch (error) {
    console.error('Download error:', error);
    return Response.json({ error: error instanceof Error ? error.message : 'Download failed' }, { status: 500 });
  }
}
