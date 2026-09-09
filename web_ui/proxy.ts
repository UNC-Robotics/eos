import { NextResponse } from 'next/server';
import { auth } from '@/auth';
import { env } from '@/lib/env';

// MCP endpoints authenticate with their own bearer-token check
const PUBLIC_PATHS = ['/signin', '/api/auth', '/api/mcp', '/api/sse', '/api/message'];

// The OAuth issuer is a single host, so the whole sign-in flow must stay on one host. Visitors arriving
// on the other loopback alias are sent to the canonical one (from NEXT_PUBLIC_APP_URL) before anything
// stateful happens, so opening either http://localhost:3000 or http://127.0.0.1:3000 works.
const LOOPBACK_ALIASES = ['localhost', '127.0.0.1'];
const CANONICAL_HOST = new URL(env.NEXT_PUBLIC_APP_URL ?? 'http://localhost').hostname;

export default auth((req) => {
  if (!env.AUTH_ENABLED) return NextResponse.next();

  const host = req.nextUrl.hostname;
  if (host !== CANONICAL_HOST && LOOPBACK_ALIASES.includes(host) && LOOPBACK_ALIASES.includes(CANONICAL_HOST)) {
    const url = req.nextUrl.clone();
    url.hostname = CANONICAL_HOST;
    return NextResponse.redirect(url);
  }

  const { pathname } = req.nextUrl;
  if (PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`))) {
    return NextResponse.next();
  }

  const authenticated = req.auth && req.auth.error !== 'RefreshTokenError';
  if (authenticated) return NextResponse.next();

  if (pathname.startsWith('/api/')) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const signInUrl = new URL('/signin/start', req.nextUrl.origin);
  signInUrl.searchParams.set('callbackUrl', pathname);
  return NextResponse.redirect(signInUrl);
});

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)'],
};
