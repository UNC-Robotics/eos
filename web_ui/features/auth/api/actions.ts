'use server';

import { redirect } from 'next/navigation';
import { auth, signOut } from '@/auth';
import { env } from '@/lib/env';

export async function signOutUser(): Promise<void> {
  const session = await auth();
  await signOut({ redirect: false });

  // End the Zitadel SSO session too (RP-initiated logout)
  if (session?.idToken) {
    const endSession = new URL(`${env.AUTH_ISSUER}/oidc/v1/end_session`);
    endSession.searchParams.set('id_token_hint', session.idToken);
    if (env.NEXT_PUBLIC_APP_URL) {
      endSession.searchParams.set('post_logout_redirect_uri', `${env.NEXT_PUBLIC_APP_URL}/signin`);
    }
    redirect(endSession.toString());
  }
  redirect('/signin');
}
