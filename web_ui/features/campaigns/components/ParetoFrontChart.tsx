'use client';

import * as React from 'react';
import { Chart as ChartJS, LinearScale, PointElement, Tooltip, Legend, ChartOptions } from 'chart.js';
import { Scatter } from 'react-chartjs-2';
import { useTheme } from 'next-themes';
import type { CampaignSample } from '../api/campaignDetails';

// Register Chart.js components
ChartJS.register(LinearScale, PointElement, Tooltip, Legend);

interface ParetoFrontChartProps {
  samples: CampaignSample[];
  paretoSolutions: Array<Record<string, unknown>>;
  outputNames: string[];
}

export function ParetoFrontChart({ samples, paretoSolutions, outputNames }: ParetoFrontChartProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const textColor = isDark ? 'rgb(209, 213, 219)' : 'rgb(107, 114, 128)';
  const gridColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.05)';

  // For 2D Pareto front, we need at least 2 objectives
  // If more than 2, let user select which pair to view
  const [xAxis, setXAxis] = React.useState<string>('');
  const [yAxis, setYAxis] = React.useState<string>('');

  // Sync axis state when outputNames changes
  React.useEffect(() => {
    if (outputNames.length >= 2) {
      setXAxis(outputNames[0]);
      setYAxis(outputNames[1]);
    } else if (outputNames.length === 1) {
      setXAxis(outputNames[0]);
      setYAxis(outputNames[0]);
    }
  }, [outputNames]);

  const chartData = React.useMemo(() => {
    if (!xAxis || !yAxis) return { datasets: [] };

    // Theme-aware colors for Pareto front
    const paretoColor = isDark
      ? { bg: 'rgba(234, 179, 8, 0.8)', border: 'rgb(234, 179, 8)' }
      : { bg: 'rgba(59, 130, 246, 0.8)', border: 'rgb(59, 130, 246)' };

    // Pareto solutions as highlighted points
    const paretoPoints = paretoSolutions.map((s) => ({
      x: s[xAxis] as number,
      y: s[yAxis] as number,
    }));

    // Create a set of Pareto point keys to filter them from all samples
    const paretoKeys = new Set(paretoPoints.map((p) => `${p.x},${p.y}`));

    // All samples as gray points (excluding Pareto points to avoid duplicates)
    const nonParetoPoints = samples
      .map((s) => ({
        x: s.outputs[xAxis] as number,
        y: s.outputs[yAxis] as number,
      }))
      .filter((p) => !paretoKeys.has(`${p.x},${p.y}`));

    return {
      datasets: [
        {
          label: 'Other Samples',
          data: nonParetoPoints,
          backgroundColor: 'rgba(156, 163, 175, 0.5)',
          borderColor: 'rgba(156, 163, 175, 0.8)',
          pointRadius: 5,
          pointHoverRadius: 7,
        },
        ...(paretoPoints.length > 0
          ? [
              {
                label: 'Pareto Front',
                data: paretoPoints,
                backgroundColor: paretoColor.bg,
                borderColor: paretoColor.border,
                pointRadius: 8,
                pointHoverRadius: 10,
                borderWidth: 2,
              },
            ]
          : []),
      ],
    };
  }, [samples, paretoSolutions, xAxis, yAxis, isDark]);

  const options: ChartOptions<'scatter'> = React.useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top' as const,
          labels: {
            usePointStyle: true,
            padding: 20,
            color: textColor,
          },
        },
        tooltip: {
          callbacks: {
            label: (context) => {
              const point = context.raw as { x: number; y: number };
              if (xAxis === yAxis) {
                return `${xAxis}: ${point.x.toFixed(4)}`;
              }
              return [`${xAxis}: ${point.x.toFixed(4)}`, `${yAxis}: ${point.y.toFixed(4)}`];
            },
          },
        },
      },
      scales: {
        x: {
          title: {
            display: true,
            text: xAxis,
            color: textColor,
          },
          ticks: {
            color: textColor,
          },
          grid: {
            color: gridColor,
          },
        },
        y: {
          title: {
            display: true,
            text: yAxis,
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
    [xAxis, yAxis, textColor, gridColor]
  );

  if (samples.length === 0) {
    return (
      <p className="text-gray-500 dark:text-gray-400 text-center py-8">No data available for Pareto visualization.</p>
    );
  }

  // Pareto front requires at least 2 objectives to visualize trade-offs
  if (outputNames.length < 2) {
    return (
      <p className="text-gray-500 dark:text-gray-400 text-center py-8">
        Pareto front visualization requires at least 2 objectives. Use the &quot;Progress Over Time&quot; tab for
        single-objective optimization.
      </p>
    );
  }

  return (
    <div>
      {/* Axis selectors for 2+ objectives */}
      {outputNames.length >= 2 && (
        <div className="flex gap-4 mb-4">
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-600 dark:text-gray-400">X-Axis:</label>
            <select
              value={xAxis}
              onChange={(e) => setXAxis(e.target.value)}
              className="text-sm border border-gray-300 dark:border-slate-600 rounded px-2 py-1 bg-white dark:bg-slate-800 text-gray-900 dark:text-white"
            >
              {outputNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-600 dark:text-gray-400">Y-Axis:</label>
            <select
              value={yAxis}
              onChange={(e) => setYAxis(e.target.value)}
              className="text-sm border border-gray-300 dark:border-slate-600 rounded px-2 py-1 bg-white dark:bg-slate-800 text-gray-900 dark:text-white"
            >
              {outputNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      <div className="h-80">
        <Scatter data={chartData} options={options} />
      </div>

      {paretoSolutions.length === 0 && (
        <p className="text-sm text-gray-500 dark:text-gray-400 text-center mt-2">
          Pareto front will be highlighted when the campaign completes.
        </p>
      )}
    </div>
  );
}
