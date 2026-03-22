'use client';

import * as React from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { JsonDisplay } from '@/components/ui/JsonDisplay';
import type { Campaign } from '@/lib/types/api';

interface CampaignInfoPanelProps {
  campaign: Campaign;
  activeCount: number;
}

export function CampaignInfoPanel({ campaign, activeCount }: CampaignInfoPanelProps) {
  const [showParameters, setShowParameters] = React.useState(false);

  const maxExperiments = campaign.max_experiments ?? 0;
  const progress = maxExperiments > 0 ? (campaign.experiments_completed / maxExperiments) * 100 : null;
  const activeProgress = maxExperiments > 0 ? (activeCount / maxExperiments) * 100 : 0;

  return (
    <div className="bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 p-4">
      {/* Progress bar */}
      {progress !== null && (
        <div className="mb-4">
          <div className="w-full bg-gray-200 dark:bg-slate-700 rounded-full h-3 overflow-hidden">
            <div className="h-3 flex">
              {/* Completed progress */}
              <div
                className="bg-blue-600 dark:bg-yellow-500 h-3 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
              {/* Running experiments (animated shimmer) */}
              {activeCount > 0 && (
                <div
                  className="h-3 relative overflow-hidden bg-blue-400 dark:bg-orange-400"
                  style={{ width: `${activeProgress}%` }}
                >
                  <div
                    className="absolute inset-0 w-full h-full"
                    style={{
                      background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.4) 50%, transparent 100%)',
                      animation: 'shimmer 1s infinite linear',
                    }}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <div className={`grid grid-cols-2 gap-4 ${campaign.status === 'RUNNING' ? 'md:grid-cols-5' : 'md:grid-cols-4'}`}>
        {/* Progress stats */}
        <div>
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            Experiments
          </div>
          <div className="mt-1">
            <span className="text-2xl font-bold text-gray-900 dark:text-white">{campaign.experiments_completed}</span>
            <span className="text-gray-500 dark:text-gray-400"> / {maxExperiments || '∞'}</span>
          </div>
        </div>

        {/* Running count - only show when campaign is running */}
        {campaign.status === 'RUNNING' && (
          <div>
            <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Active</div>
            <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">{activeCount}</div>
          </div>
        )}

        {/* Max Concurrent */}
        <div>
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            Max Concurrent
          </div>
          <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
            {campaign.max_concurrent_experiments}
          </div>
        </div>

        {/* Optimizer */}
        <div>
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            Optimization
          </div>
          <div className="mt-1 text-sm text-gray-900 dark:text-white">
            {campaign.optimize ? (
              <>
                <span className="font-medium">Enabled</span>
                <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">{campaign.optimizer_ip}</div>
              </>
            ) : (
              <span className="text-gray-500 dark:text-gray-400">Disabled</span>
            )}
          </div>
        </div>

        {/* Timeline */}
        <div>
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Timeline</div>
          <div className="mt-1 text-xs space-y-0.5">
            {campaign.start_time && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Started: </span>
                <span className="text-gray-900 dark:text-white">{new Date(campaign.start_time).toLocaleString()}</span>
              </div>
            )}
            {campaign.end_time && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Ended: </span>
                <span className="text-gray-900 dark:text-white">{new Date(campaign.end_time).toLocaleString()}</span>
              </div>
            )}
            {!campaign.start_time && !campaign.end_time && (
              <div className="text-gray-500 dark:text-gray-400">Not started</div>
            )}
          </div>
        </div>
      </div>

      {/* Global Parameters (collapsible) */}
      {campaign.global_parameters && Object.keys(campaign.global_parameters).length > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-slate-700">
          <button
            onClick={() => setShowParameters(!showParameters)}
            className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
          >
            {showParameters ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            Global Parameters
          </button>
          {showParameters && (
            <div className="mt-2">
              <JsonDisplay data={campaign.global_parameters} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
