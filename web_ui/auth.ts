import NextAuth from 'next-auth';
import type { JWT } from 'next-auth/jwt';
import Zitadel from 'next-auth/providers/zitadel';
import { env } from '@/lib/env';

const REFRESH_MARGIN_MS = 60_000;

declare module 'next-auth' {
  interface Session {
    user: {
      sub: string;
      name?: string | null;
      email?: string | null;
    };
    accessToken: string;
    idToken?: string;
    error?: 'RefreshTokenError';
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    sub: string;
    accessToken: string;
    refreshToken?: string;
    idToken?: string;
    expiresAt: number;
    error?: 'RefreshTokenError';
  }
}

async function refreshAccessToken(token: JWT): Promise<JWT> {
  try {
    const response = await fetch(`${env.AUTH_ISSUER}/oauth/v2/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'refresh_token',
        client_id: env.AUTH_CLIENT_ID!,
        refresh_token: token.refreshToken!,
      }),
    });
    if (!response.ok) throw new Error(`Token refresh failed with status ${response.status}`);

    const refreshed = await response.json();
    if (typeof refreshed.expires_in !== 'number') throw new Error('Token refresh response missing expires_in');
    return {
      ...token,
      accessToken: refreshed.access_token,
      refreshToken: refreshed.refresh_token ?? token.refreshToken,
      expiresAt: Date.now() + refreshed.expires_in * 1000,
      error: undefined,
    };
  } catch {
    return { ...token, error: 'RefreshTokenError' };
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  // Dummy secret keeps imports safe when auth is disabled (no auth route is ever hit)
  secret: env.AUTH_SECRET ?? 'auth-disabled',
  session: { strategy: 'jwt' },
  pages: { signIn: '/signin' },
  providers: env.AUTH_ENABLED
    ? [
        Zitadel({
          issuer: env.AUTH_ISSUER,
          clientId: env.AUTH_CLIENT_ID,
          // Public client with PKCE; no client secret
          client: { token_endpoint_auth_method: 'none' },
          checks: ['pkce', 'state'],
          authorization: {
            params: {
              scope: 'openid profile email offline_access',
            },
          },
        }),
      ]
    : [],
  callbacks: {
    jwt: async ({ token, account, profile }) => {
      // Initial sign-in: persist tokens and identity from the profile claims
      if (account && profile) {
        return {
          ...token,
          sub: profile.sub!,
          name: profile.name ?? token.name ?? null,
          email: profile.email ?? token.email ?? null,
          accessToken: account.access_token!,
          refreshToken: account.refresh_token,
          idToken: account.id_token,
          expiresAt: (account.expires_at ?? 0) * 1000,
        };
      }

      if (Date.now() < token.expiresAt - REFRESH_MARGIN_MS) return token;
      if (!token.refreshToken) return { ...token, error: 'RefreshTokenError' as const };
      return refreshAccessToken(token);
    },
    session: async ({ session, token }) => {
      session.user.sub = token.sub;
      session.accessToken = token.accessToken;
      session.idToken = token.idToken;
      session.error = token.error;
      return session;
    },
  },
});
