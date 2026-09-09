import { type NextRequest } from 'next/server';
import { ORCHESTRATOR_BASE_URL } from '@/lib/api/orchestrator';
import { getAccessToken } from '@/lib/auth/session';

export const dynamic = 'force-dynamic';

// Proxies the orchestrator's SSE log stream, injecting the caller's bearer token server-side. The
// browser's EventSource cannot set an Authorization header, so it connects here (same-origin, cookie
// auth) and this route forwards with the bearer.
export async function GET(req: NextRequest) {
  const level = req.nextUrl.searchParams.get('level') ?? 'INFO';
  const token = await getAccessToken();

  const headers: Record<string, string> = { Accept: 'text/event-stream' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let upstream: Response;
  try {
    upstream = await fetch(`${ORCHESTRATOR_BASE_URL}/logs/stream?level=${encodeURIComponent(level)}`, {
      headers,
      signal: req.signal,
    });
  } catch {
    return new Response('Failed to connect to log stream', { status: 502 });
  }

  if (!upstream.ok || !upstream.body) {
    return new Response('Failed to connect to log stream', { status: upstream.status || 502 });
  }

  return new Response(upstream.body, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  });
}
