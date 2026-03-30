import { ManagementTabs } from '@/features/management/components/ManagementTabs';
import { getDevices } from '@/features/management/api/devices';
import { getLabs } from '@/features/management/api/labs';
import { getPackages } from '@/features/management/api/packages';
import { getTaskPlugins } from '@/features/management/api/taskPlugins';
import { getProtocolTypes } from '@/features/management/api/protocolTypes';

export const dynamic = 'force-dynamic';

export const metadata = {
  title: 'System Management - EOS',
  description: 'Manage packages, devices, labs, task plugins, and protocols',
};

export default async function ManagementPage() {
  // Fetch all data in parallel
  const [packages, devices, labs, taskPlugins, protocolTypes] = await Promise.all([
    getPackages(),
    getDevices(),
    getLabs(),
    getTaskPlugins(),
    getProtocolTypes(),
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
      />
    </div>
  );
}
