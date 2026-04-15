'use client';

import { useEffect } from 'react';
import Link from 'next/link';

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error('Application error:', error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 dark:bg-gray-950">
      <div className="w-full max-w-md space-y-8 rounded-lg bg-white dark:bg-slate-900 p-8 shadow-lg dark:shadow-slate-800/20">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Something went wrong!</h2>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            {error.message || 'An unexpected error occurred. Please try again.'}
          </p>
          {error.digest && (
            <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
              Error ID: <code className="font-mono">{error.digest}</code>
            </p>
          )}
        </div>
        <div className="flex flex-col gap-3">
          <button
            onClick={reset}
            className="w-full rounded-md bg-blue-600 dark:bg-yellow-500 px-4 py-2 text-white dark:text-gray-900 hover:bg-blue-700 dark:hover:bg-yellow-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-yellow-500 focus:ring-offset-2 dark:focus:ring-offset-slate-900"
          >
            Try again
          </button>
          <Link
            href="/"
            className="w-full rounded-md border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2 text-center text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-400 focus:ring-offset-2 dark:focus:ring-offset-slate-900"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}
