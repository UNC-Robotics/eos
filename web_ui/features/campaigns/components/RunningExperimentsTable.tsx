'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { ExternalLink, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { Badge, getStatusBadgeVariant } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import type { Experiment } from '@/lib/types/api';

const PAGE_SIZE = 10;

interface RunningExperimentsTableProps {
  experiments: Experiment[];
  campaignName: string;
}

export function RunningExperimentsTable({ experiments, campaignName }: RunningExperimentsTableProps) {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = React.useState('');
  const [currentPage, setCurrentPage] = React.useState(0);

  // Filter and sort experiments
  const filteredExperiments = React.useMemo(() => {
    let filtered = experiments;

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (exp) => exp.name.toLowerCase().includes(query) || exp.status.toLowerCase().includes(query)
      );
    }

    // Sort: active (RUNNING/CREATED) first, then by start time descending
    const isActive = (s: string) => s === 'RUNNING' || s === 'CREATED';
    return [...filtered].sort((a, b) => {
      const aActive = isActive(a.status);
      const bActive = isActive(b.status);
      if (aActive && !bActive) return -1;
      if (!aActive && bActive) return 1;
      if (a.status === 'RUNNING' && b.status === 'CREATED') return -1;
      if (a.status === 'CREATED' && b.status === 'RUNNING') return 1;
      const aTime = a.start_time ? new Date(a.start_time).getTime() : 0;
      const bTime = b.start_time ? new Date(b.start_time).getTime() : 0;
      return bTime - aTime;
    });
  }, [experiments, searchQuery]);

  // Pagination
  const totalPages = Math.ceil(filteredExperiments.length / PAGE_SIZE);
  const paginatedExperiments = React.useMemo(() => {
    const start = currentPage * PAGE_SIZE;
    return filteredExperiments.slice(start, start + PAGE_SIZE);
  }, [filteredExperiments, currentPage]);

  // Reset page when search changes
  React.useEffect(() => {
    setCurrentPage(0);
  }, [searchQuery]);

  const handleRowClick = (experimentName: string) => {
    router.push(
      `/experiments/${encodeURIComponent(experimentName)}?from=campaign&campaign=${encodeURIComponent(campaignName)}`
    );
  };

  if (experiments.length === 0) {
    return <p className="text-gray-500 dark:text-gray-400 text-center py-4">No experiments yet.</p>;
  }

  return (
    <div className="space-y-3">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <Input
          type="text"
          placeholder="Search experiments..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-slate-700">
              <th className="text-left py-2 px-3 font-medium text-gray-500 dark:text-gray-400">Name</th>
              <th className="text-left py-2 px-3 font-medium text-gray-500 dark:text-gray-400">Status</th>
              <th className="text-left py-2 px-3 font-medium text-gray-500 dark:text-gray-400">Started</th>
              <th className="text-left py-2 px-3 font-medium text-gray-500 dark:text-gray-400">Ended</th>
              <th className="text-right py-2 px-3 font-medium text-gray-500 dark:text-gray-400"></th>
            </tr>
          </thead>
          <tbody>
            {paginatedExperiments.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-4 text-center text-gray-500 dark:text-gray-400">
                  No experiments match your search.
                </td>
              </tr>
            ) : (
              paginatedExperiments.map((experiment) => (
                <tr
                  key={experiment.name}
                  className="border-b border-gray-100 dark:border-slate-800 hover:bg-gray-50 dark:hover:bg-slate-800/50 cursor-pointer transition-colors"
                  onClick={() => handleRowClick(experiment.name)}
                >
                  <td className="py-2 px-3 font-medium text-gray-900 dark:text-white">{experiment.name}</td>
                  <td className="py-2 px-3">
                    <Badge variant={getStatusBadgeVariant(experiment.status)}>{experiment.status}</Badge>
                  </td>
                  <td className="py-2 px-3 text-gray-600 dark:text-gray-400">
                    {experiment.start_time ? new Date(experiment.start_time).toLocaleString() : '-'}
                  </td>
                  <td className="py-2 px-3 text-gray-600 dark:text-gray-400">
                    {experiment.end_time ? new Date(experiment.end_time).toLocaleString() : '-'}
                  </td>
                  <td className="py-2 px-3 text-right">
                    <ExternalLink className="h-4 w-4 text-gray-400 dark:text-gray-500 inline-block" />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            Showing {currentPage * PAGE_SIZE + 1}-{Math.min((currentPage + 1) * PAGE_SIZE, filteredExperiments.length)}{' '}
            of {filteredExperiments.length}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
              disabled={currentPage === 0}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="px-2 text-sm text-gray-600 dark:text-gray-300">
              {currentPage + 1} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={currentPage >= totalPages - 1}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
