import { NextResponse, type NextRequest } from 'next/server';
import { signIn } from '@/auth';
import { env } from '@/lib/env';

// Initiates Zitadel sign-in server-side so users go straight to the provider, with no intermediate page.
export async function GET(req: NextRequest) {
  if (!env.AUTH_ENABLED) return NextResponse.redirect(new URL('/', req.nextUrl.origin));
  const requested = req.nextUrl.searchParams.get('callbackUrl') || '/';
  // Only allow same-origin relative paths to avoid an open redirect
  const callbackUrl = requested.startsWith('/') && !requested.startsWith('//') ? requested : '/';
  await signIn('zitadel', { redirectTo: callbackUrl });
  // signIn issues the redirect to Zitadel; reached only if it somehow does not.
  return NextResponse.redirect(new URL(callbackUrl, req.nextUrl.origin));
}
