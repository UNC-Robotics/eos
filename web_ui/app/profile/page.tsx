import { redirect } from 'next/navigation';
import { Fingerprint, KeyRound, ShieldCheck, UserRound } from 'lucide-react';
import { ChangePasswordForm } from '@/features/profile/components/ChangePasswordForm';
import { ApiTokensSection } from '@/features/profile/components/ApiTokensSection';
import { listApiTokens } from '@/features/profile/api/tokens';
import { Badge } from '@/components/ui/Badge';
import { getSessionUser } from '@/lib/auth/session';
import { partitionSuperuser } from '@/lib/auth/roles';
import { getUserRoles } from '@/lib/db/queries';
import { env } from '@/lib/env';

export const dynamic = 'force-dynamic';

export const metadata = { title: 'Profile' };

export default async function ProfilePage() {
  if (!env.AUTH_ENABLED) redirect('/');
  const user = await getSessionUser();
  if (!user) redirect('/signin');
  const { superuser, roles } = partitionSuperuser(await getUserRoles(user.sub));
  const apiTokens = await listApiTokens();

  return (
    <div className="container mx-auto px-6 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-8">Profile</h1>

      {/* Identity */}
      <section className="mb-6 rounded-lg border border-gray-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-900">
        <h2 className="truncate text-xl font-semibold text-gray-900 dark:text-white">{user.name ?? 'Unnamed user'}</h2>
        <p className="mt-1 truncate text-sm text-gray-500 dark:text-gray-400">{user.email ?? 'No email on file'}</p>
      </section>

      {/* Account details */}
      <section className="mb-6 rounded-lg border border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-center gap-2 border-b border-gray-200 px-6 py-4 dark:border-slate-700">
          <UserRound className="h-4 w-4 text-gray-400 dark:text-gray-500" />
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Account details</h2>
        </div>
        <dl className="divide-y divide-gray-100 dark:divide-slate-800">
          <div className="flex flex-col gap-1 px-6 py-4 sm:flex-row sm:items-center sm:gap-4">
            <dt className="flex w-36 flex-shrink-0 items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              <Fingerprint className="h-3.5 w-3.5" />
              User ID
            </dt>
            <dd className="break-all font-mono text-sm text-gray-900 dark:text-gray-100">{user.sub}</dd>
          </div>
          <div className="flex flex-col gap-1 px-6 py-4 sm:flex-row sm:gap-4">
            <dt className="flex w-36 flex-shrink-0 items-center gap-1.5 pt-0.5 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              <ShieldCheck className="h-3.5 w-3.5" />
              Roles
            </dt>
            <dd className="flex flex-wrap items-center gap-2">
              {superuser && (
                <Badge variant="warning">
                  <ShieldCheck className="mr-1 h-3 w-3" />
                  superuser
                </Badge>
              )}
              {roles.map((role) => (
                <Badge key={role.id} variant="info">
                  {role.role.toLowerCase()}
                  {role.labName ? `: ${role.labName}` : ''}
                </Badge>
              ))}
              {!superuser && roles.length === 0 && (
                <span className="text-sm text-gray-400 dark:text-gray-500">No access granted</span>
              )}
            </dd>
          </div>
        </dl>
      </section>

      {/* Change password */}
      <section className="rounded-lg border border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-center gap-2 border-b border-gray-200 px-6 py-4 dark:border-slate-700">
          <KeyRound className="h-4 w-4 text-gray-400 dark:text-gray-500" />
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Change password</h2>
        </div>
        <div className="px-6 py-5">
          <ChangePasswordForm />
        </div>
      </section>

      {/* API tokens */}
      <div className="mt-6">
        <ApiTokensSection tokens={apiTokens} />
      </div>
    </div>
  );
}
