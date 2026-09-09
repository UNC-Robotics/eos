import { ManagementTabs } from '@/features/management/components/ManagementTabs';
import { getDevices } from '@/features/management/api/devices';
import { getLabs } from '@/features/management/api/labs';
import { getPackages } from '@/features/management/api/packages';
import { getTaskPlugins } from '@/features/management/api/taskPlugins';
import { getProtocolTypes } from '@/features/management/api/protocolTypes';
import { getUsers } from '@/features/management/api/users';
import { currentUserIsAdmin, currentUserIsSuperuser } from '@/lib/auth/authz';
import { env } from '@/lib/env';
import { redirect } from 'next/navigation';

export const dynamic = 'force-dynamic';

export const metadata = {
  title: 'System Management - EOS',
  description: 'Manage packages, devices, labs, task plugins, protocols, and users',
};

export default async function ManagementPage() {
  // System management is for lab admins and superusers; other roles are redirected away.
  if (!(await currentUserIsAdmin())) redirect('/');

  // Loading labs and packages, and managing users, are superuser-only.
  const superuser = await currentUserIsSuperuser();
  const showUsers = env.AUTH_ENABLED && superuser;

  // Fetch all data in parallel
  const [packages, devices, labs, taskPlugins, protocolTypes, users] = await Promise.all([
    getPackages(),
    getDevices(),
    getLabs(),
    getTaskPlugins(),
    getProtocolTypes(),
    showUsers ? getUsers() : Promise.resolve(null),
  ]);

  return (
    <div className="container mx-auto px-6 py-8">
      <div className="mb-4">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">System Management</h1>
      </div>

      <ManagementTabs
        packages={packages}
        devices={devices}
        labs={labs}
        taskPlugins={taskPlugins}
        protocolTypes={protocolTypes}
        users={users}
        superuser={superuser}
      />
    </div>
  );
}
