'use client';

import * as React from 'react';
import * as Tabs from '@radix-ui/react-tabs';
import { Server, FlaskConical, ListChecks, Boxes, Package } from 'lucide-react';
import { DevicesTab } from './DevicesTab';
import { LabsTab } from './LabsTab';
import { TaskPluginsTab } from './TaskPluginsTab';
import { ProtocolTypesTab } from './ProtocolTypesTab';
import { PackagesTab } from './PackagesTab';
import type { Device, Lab, TaskPluginInfo, ProtocolType, PackageInfo } from '@/lib/types/management';

interface ManagementTabsProps {
  packages: PackageInfo[];
  devices: Device[];
  labs: Lab[];
  taskPlugins: TaskPluginInfo[];
  protocolTypes: ProtocolType[];
}

export function ManagementTabs({ packages, devices, labs, taskPlugins, protocolTypes }: ManagementTabsProps) {
  const [activeTab, setActiveTab] = React.useState('packages');

  return (
    <Tabs.Root value={activeTab} onValueChange={setActiveTab} className="w-full">
      <Tabs.List className="flex gap-1 border-b border-gray-200 dark:border-slate-700 mb-6">
        <Tabs.Trigger
          value="packages"
          className="flex items-center gap-2 px-6 py-4 text-base font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 border-b-2 border-transparent data-[state=active]:border-blue-600 dark:data-[state=active]:border-yellow-500 data-[state=active]:text-blue-600 dark:data-[state=active]:text-yellow-500 transition-colors"
        >
          <Package className="h-5 w-5" />
          Packages
          <span className="ml-1 rounded-full bg-gray-100 dark:bg-slate-700 px-2.5 py-1 text-xs font-medium text-gray-600 dark:text-gray-300">
            {packages.filter((p) => p.active).length}/{packages.length}
          </span>
        </Tabs.Trigger>

        <Tabs.Trigger
          value="labs"
          className="flex items-center gap-2 px-6 py-4 text-base font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 border-b-2 border-transparent data-[state=active]:border-blue-600 dark:data-[state=active]:border-yellow-500 data-[state=active]:text-blue-600 dark:data-[state=active]:text-yellow-500 transition-colors"
        >
          <Boxes className="h-5 w-5" />
          Labs
          <span className="ml-1 rounded-full bg-gray-100 dark:bg-slate-700 px-2.5 py-1 text-xs font-medium text-gray-600 dark:text-gray-300">
            {labs.filter((l) => l.loaded).length}/{labs.length}
          </span>
        </Tabs.Trigger>

        <Tabs.Trigger
          value="devices"
          className="flex items-center gap-2 px-6 py-4 text-base font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 border-b-2 border-transparent data-[state=active]:border-blue-600 dark:data-[state=active]:border-yellow-500 data-[state=active]:text-blue-600 dark:data-[state=active]:text-yellow-500 transition-colors"
        >
          <Server className="h-5 w-5" />
          Devices
          <span className="ml-1 rounded-full bg-gray-100 dark:bg-slate-700 px-2.5 py-1 text-xs font-medium text-gray-600 dark:text-gray-300">
            {devices.length}
          </span>
        </Tabs.Trigger>

        <Tabs.Trigger
          value="tasks"
          className="flex items-center gap-2 px-6 py-4 text-base font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 border-b-2 border-transparent data-[state=active]:border-blue-600 dark:data-[state=active]:border-yellow-500 data-[state=active]:text-blue-600 dark:data-[state=active]:text-yellow-500 transition-colors"
        >
          <ListChecks className="h-5 w-5" />
          Task Plugins
          <span className="ml-1 rounded-full bg-gray-100 dark:bg-slate-700 px-2.5 py-1 text-xs font-medium text-gray-600 dark:text-gray-300">
            {taskPlugins.length}
          </span>
        </Tabs.Trigger>

        <Tabs.Trigger
          value="protocols"
          className="flex items-center gap-2 px-6 py-4 text-base font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 border-b-2 border-transparent data-[state=active]:border-blue-600 dark:data-[state=active]:border-yellow-500 data-[state=active]:text-blue-600 dark:data-[state=active]:text-yellow-500 transition-colors"
        >
          <FlaskConical className="h-5 w-5" />
          Protocols
          <span className="ml-1 rounded-full bg-gray-100 dark:bg-slate-700 px-2.5 py-1 text-xs font-medium text-gray-600 dark:text-gray-300">
            {protocolTypes.filter((e) => e.loaded).length}/{protocolTypes.length}
          </span>
        </Tabs.Trigger>
      </Tabs.List>

      <Tabs.Content value="packages" className="focus:outline-none">
        <PackagesTab initialPackages={packages} />
      </Tabs.Content>

      <Tabs.Content value="labs" className="focus:outline-none">
        <LabsTab initialLabs={labs} />
      </Tabs.Content>

      <Tabs.Content value="devices" className="focus:outline-none">
        <DevicesTab initialDevices={devices} />
      </Tabs.Content>

      <Tabs.Content value="tasks" className="focus:outline-none">
        <TaskPluginsTab initialTaskPlugins={taskPlugins} />
      </Tabs.Content>

      <Tabs.Content value="protocols" className="focus:outline-none">
        <ProtocolTypesTab initialProtocolTypes={protocolTypes} />
      </Tabs.Content>
    </Tabs.Root>
  );
}
