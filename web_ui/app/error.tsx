'use client';

import { useEffect } from 'react';
import Link from 'next/link';

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error('Application error:', error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50">
      <div className="w-full max-w-md space-y-8 rounded-lg bg-white p-8 shadow-lg">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900">Something went wrong!</h2>
          <p className="mt-2 text-sm text-gray-600">
            {error.message || 'An unexpected error occurred. Please try again.'}
          </p>
          {error.digest && (
            <p className="mt-2 text-xs text-gray-400">
              Error ID: <code className="font-mono">{error.digest}</code>
            </p>
          )}
        </div>
        <div className="flex flex-col gap-3">
          <button
            onClick={reset}
            className="w-full rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Try again
          </button>
          <Link
            href="/"
            className="w-full rounded-md border border-gray-300 bg-white px-4 py-2 text-center text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}
