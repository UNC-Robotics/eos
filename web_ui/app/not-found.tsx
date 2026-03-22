import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50">
      <div className="text-center">
        <h1 className="text-9xl font-bold text-gray-300">404</h1>
        <h2 className="mt-4 text-2xl font-semibold text-gray-900">Page not found</h2>
        <p className="mt-2 text-gray-600">Sorry, we couldn&apos;t find the page you&apos;re looking for.</p>
        <div className="mt-8">
          <Link
            href="/"
            className="rounded-md bg-blue-600 px-6 py-3 text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Go back home
          </Link>
        </div>
      </div>
    </div>
  );
}
