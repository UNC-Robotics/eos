import { redirect } from 'next/navigation';
import { env } from '@/lib/env';

const ERROR_MESSAGES: Record<string, string> = {
  OAuthCallbackError: 'Sign-in was cancelled or failed. Please try again.',
  AccessDenied: 'Access denied. Contact an administrator.',
  Configuration: 'Authentication is misconfigured. Contact an administrator.',
};

export const metadata = { title: 'Sign in' };

function startUrl(callbackUrl?: string): string {
  return callbackUrl ? `/signin/start?callbackUrl=${encodeURIComponent(callbackUrl)}` : '/signin/start';
}

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string; error?: string }>;
}) {
  if (!env.AUTH_ENABLED) redirect('/');
  const { callbackUrl, error } = await searchParams;
  // Normal entry goes straight to the provider; only a sign-in error renders a page.
  if (!error) redirect(startUrl(callbackUrl));

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-slate-950">
      <div className="w-full max-w-sm p-8 bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 shadow-sm text-center">
        <p className="mb-4 text-sm text-red-600 dark:text-red-400">
          {ERROR_MESSAGES[error] ?? 'Sign-in failed. Please try again.'}
        </p>
        <a
          href={startUrl(callbackUrl)}
          className="inline-flex w-full items-center justify-center px-4 py-2.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white font-medium transition-colors"
        >
          Try again
        </a>
      </div>
    </div>
  );
}
