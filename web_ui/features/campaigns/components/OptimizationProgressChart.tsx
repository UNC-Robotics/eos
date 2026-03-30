'use client';

import * as React from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ChartOptions,
} from 'chart.js';
import { Line, getElementAtEvent } from 'react-chartjs-2';
import { useTheme } from 'next-themes';
import { useRouter } from 'next/navigation';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { ArrowUpDown } from 'lucide-react';
import type { CampaignSample } from '../api/campaignDetails';

// Register Chart.js components
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

// Color palette for multiple objectives (light mode / dark mode)
const COLORS_LIGHT = [
  { border: 'rgb(59, 130, 246)', background: 'rgba(59, 130, 246, 0.1)' }, // Blue
  { border: 'rgb(239, 68, 68)', background: 'rgba(239, 68, 68, 0.1)' }, // Red
  { border: 'rgb(34, 197, 94)', background: 'rgba(34, 197, 94, 0.1)' }, // Green
  { border: 'rgb(168, 85, 247)', background: 'rgba(168, 85, 247, 0.1)' }, // Purple
  { border: 'rgb(249, 115, 22)', background: 'rgba(249, 115, 22, 0.1)' }, // Orange
  { border: 'rgb(20, 184, 166)', background: 'rgba(20, 184, 166, 0.1)' }, // Teal
];

const COLORS_DARK = [
  { border: 'rgb(234, 179, 8)', background: 'rgba(234, 179, 8, 0.1)' }, // Yellow
  { border: 'rgb(239, 68, 68)', background: 'rgba(239, 68, 68, 0.1)' }, // Red
  { border: 'rgb(34, 197, 94)', background: 'rgba(34, 197, 94, 0.1)' }, // Green
  { border: 'rgb(168, 85, 247)', background: 'rgba(168, 85, 247, 0.1)' }, // Purple
  { border: 'rgb(249, 115, 22)', background: 'rgba(249, 115, 22, 0.1)' }, // Orange
  { border: 'rgb(20, 184, 166)', background: 'rgba(20, 184, 166, 0.1)' }, // Teal
];

interface OptimizationProgressChartProps {
  samples: CampaignSample[];
  outputNames: string[];
  campaignName: string;
}

type SortOrder = 'completion' | 'index';

const SORT_OPTIONS: { label: string; value: SortOrder }[] = [
  { label: 'Completion Order', value: 'completion' },
  { label: 'Protocol Run Index', value: 'index' },
];

function getRunNumber(name: string): number {
  const match = name.match(/_(\d+)$/);
  return match ? parseInt(match[1]) : 0;
}

export function OptimizationProgressChart({ samples, outputNames, campaignName }: OptimizationProgressChartProps) {
  const router = useRouter();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const [sortOrder, setSortOrder] = React.useState<SortOrder>('completion');

  const textColor = isDark ? 'rgb(209, 213, 219)' : 'rgb(107, 114, 128)';
  const gridColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.05)';

  const orderedSamples = React.useMemo(() => {
    if (sortOrder === 'completion') return samples;
    return [...samples].sort((a, b) => getRunNumber(a.protocolRunName) - getRunNumber(b.protocolRunName));
  }, [samples, sortOrder]);

  const chartData = React.useMemo(() => {
    const colors = isDark ? COLORS_DARK : COLORS_LIGHT;
    const labels = orderedSamples.map((s) => {
      const match = s.protocolRunName.match(/_(\d+)$/);
      return match ? match[1] : s.protocolRunName;
    });

    const datasets = outputNames.map((name, idx) => ({
      label: name,
      data: orderedSamples.map((s) => s.outputs[name]),
      borderColor: colors[idx % colors.length].border,
      backgroundColor: colors[idx % colors.length].background,
      tension: 0.1,
      pointRadius: 0,
      pointHoverRadius: 5,
      pointHitRadius: 10,
    }));

    return { labels, datasets };
  }, [orderedSamples, outputNames, isDark]);

  const options: ChartOptions<'line'> = React.useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index' as const,
        intersect: false,
      },
      plugins: {
        legend: {
          position: 'top' as const,
          labels: {
            usePointStyle: true,
            padding: 20,
            color: textColor,
          },
        },
        title: {
          display: false,
        },
        tooltip: {
          callbacks: {
            title: (items) => `Protocol Run ${items[0].label}`,
            label: (context) => {
              const value = context.parsed.y;
              return `${context.dataset.label}: ${value?.toFixed(4) ?? '-'}`;
            },
          },
        },
      },
      scales: {
        x: {
          title: {
            display: true,
            text: 'Protocol Run',
            color: textColor,
          },
          ticks: {
            color: textColor,
          },
          grid: {
            display: false,
          },
        },
        y: {
          title: {
            display: true,
            text: 'Objective Value',
            color: textColor,
          },
          ticks: {
            color: textColor,
          },
          grid: {
            color: gridColor,
          },
        },
      },
    }),
    [textColor, gridColor]
  );

  const chartRef = React.useRef<ChartJS<'line'>>(null);

  const handleClick = React.useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      const chart = chartRef.current;
      if (!chart) return;
      const elements = getElementAtEvent(chart, event);
      if (elements.length === 0) return;
      const sample = orderedSamples[elements[0].index];
      if (sample) {
        router.push(
          `/protocol-runs/${encodeURIComponent(sample.protocolRunName)}?from=campaign&campaign=${encodeURIComponent(campaignName)}`
        );
      }
    },
    [orderedSamples, campaignName, router]
  );

  if (samples.length === 0) {
    return <p className="text-gray-500 dark:text-gray-400 text-center py-8">No optimization data available yet.</p>;
  }

  return (
    <div className="relative h-80">
      <div className="absolute top-0 right-0 z-10">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button className="inline-flex items-center gap-1.5 px-2 py-1 text-xs rounded border border-gray-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 backdrop-blur-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-slate-700 transition-colors">
              <ArrowUpDown className="h-3 w-3" />
              {SORT_OPTIONS.find((o) => o.value === sortOrder)?.label}
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content className="w-40 rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-1 shadow-md z-50">
              {SORT_OPTIONS.map((option) => (
                <DropdownMenu.Item
                  key={option.value}
                  className={`relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-xs outline-none transition-colors hover:bg-gray-100 dark:hover:bg-slate-700 focus:bg-gray-100 dark:focus:bg-slate-700 dark:text-gray-300 ${
                    sortOrder === option.value ? 'bg-gray-100 dark:bg-slate-700 font-medium' : ''
                  }`}
                  onClick={() => setSortOrder(option.value)}
                >
                  {option.label}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>
      <Line ref={chartRef} data={chartData} options={options} onClick={handleClick} />
    </div>
  );
}
