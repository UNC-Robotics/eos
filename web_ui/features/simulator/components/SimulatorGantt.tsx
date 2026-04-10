'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Maximize2, Minimize2 } from 'lucide-react';
import * as echarts from 'echarts/core';
import { CustomChart } from 'echarts/charts';
import { TooltipComponent, GridComponent, DataZoomComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { useTheme } from 'next-themes';
import type { TaskRecord, SimStats } from '../types';

echarts.use([CustomChart, TooltipComponent, GridComponent, DataZoomComponent, CanvasRenderer]);

// Generate a visually distinct color for index i using golden-angle hue spacing
function hslToHex(h: number, s: number, l: number): string {
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * color)
      .toString(16)
      .padStart(2, '0');
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

function generateColor(index: number): string {
  // Golden angle (~137.5°) gives maximally spaced hues
  const hue = (index * 137.508) % 360;
  // Alternate saturation/lightness bands for more distinction when hues wrap
  const saturation = 0.65 + (index % 3) * 0.1;
  const lightness = 0.42 + (index % 2) * 0.08;
  return hslToHex(hue, saturation, lightness);
}

function textColorForBg(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  // Perceived luminance (sRGB)
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.45 ? '#1a1a2e' : '#ffffff';
}

const taskColorMap = new Map<string, { bg: string; fg: string }>();
function taskColors(name: string): { bg: string; fg: string } {
  let colors = taskColorMap.get(name);
  if (!colors) {
    const bg = generateColor(taskColorMap.size);
    colors = { bg, fg: textColorForBg(bg) };
    taskColorMap.set(name, colors);
  }
  return colors;
}

function fmtTime(s: number): string {
  s = Math.round(s);
  if (s < 60) return s + 's';
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r ? m + 'm' + String(r).padStart(2, '0') + 's' : m + 'm';
}

type ViewMode = 'protocol' | 'device';

interface Props {
  timeline: TaskRecord[];
  stats: SimStats;
}

export default function SimulatorGantt({ timeline, stats }: Props) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const [view, setView] = useState<ViewMode>('protocol');
  const [maximized, setMaximized] = useState(false);
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  // Measure the scrollable content area and size the chart to fill it
  const updateLayout = useCallback(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const scrollParent = el.closest('.overflow-auto') as HTMLElement | null;
    if (!scrollParent) return;

    if (maximized) {
      const w = scrollParent.clientWidth;
      const h = scrollParent.clientHeight;
      const margin = 16;
      el.style.position = 'fixed';
      const rect = scrollParent.getBoundingClientRect();
      el.style.top = `${rect.top + margin}px`;
      el.style.left = `${rect.left + margin}px`;
      el.style.width = `${w - margin * 2}px`;
      el.style.height = `${h - margin * 2}px`;
      el.style.zIndex = '40';
      el.style.marginLeft = '';
      if (chartRef.current) chartRef.current.style.height = `${h - margin * 2 - 48}px`;
    } else {
      el.style.position = '';
      el.style.top = '';
      el.style.left = '';
      el.style.height = '';
      el.style.zIndex = '';
      const available = scrollParent.clientWidth;
      const margin = 40;
      el.style.width = `${available - margin * 2}px`;
      el.style.marginLeft = `${-(available - margin * 2 - el.parentElement!.clientWidth) / 2}px`;
      if (chartRef.current) chartRef.current.style.height = '';
    }
    chartInstance.current?.resize();
  }, [maximized]);

  useEffect(() => {
    updateLayout();
    window.addEventListener('resize', updateLayout);
    const observer = new ResizeObserver(updateLayout);
    const scrollParent = wrapperRef.current?.closest('.overflow-auto');
    if (scrollParent) observer.observe(scrollParent);
    return () => {
      window.removeEventListener('resize', updateLayout);
      observer.disconnect();
    };
  }, [updateLayout]);

  useEffect(() => {
    taskColorMap.clear();
  }, [timeline]);

  useEffect(() => {
    if (!chartRef.current) return;

    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }

    const buildView = (mode: ViewMode) => {
      if (mode === 'protocol') {
        const lanes = [...new Set(timeline.map((t) => t.protocol_run))];
        return {
          categories: lanes,
          data: timeline.map((t) => ({ ...t, lane: lanes.indexOf(t.protocol_run) })),
        };
      } else {
        const deviceSet = new Set<string>();
        timeline.forEach((t) => t.devices.forEach((d) => deviceSet.add(d.lab + '.' + d.name)));
        const lanes = [...deviceSet].sort();
        const data: (TaskRecord & { lane: number })[] = [];
        timeline.forEach((t) => {
          t.devices.forEach((d) => {
            data.push({ ...t, lane: lanes.indexOf(d.lab + '.' + d.name) });
          });
        });
        return { categories: lanes, data };
      }
    };

    const v = buildView(view);
    const laneCount = v.categories.length;
    const rowH = Math.max(24, Math.min(36, 800 / laneCount));
    const chartH = Math.max(600, laneCount * rowH + 120);

    if (!maximized) {
      chartRef.current.style.height = chartH + 'px';
    }
    chartInstance.current.resize();

    const textColor = isDark ? 'rgb(209, 213, 219)' : 'rgb(107, 114, 128)';
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.04)';
    const borderColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.08)';
    const tooltipBg = isDark ? 'rgba(30, 41, 59, 0.96)' : 'rgba(255, 255, 255, 0.96)';
    const tooltipBorder = isDark ? '#475569' : '#ddd';
    const tooltipTextColor = isDark ? '#e2e8f0' : '#333';

    const seriesData = v.data.map((t) => ({
      value: [t.start, t.lane, t.end, t.duration],
      itemStyle: { color: taskColors(t.task).bg },
      _task: t,
    }));

    chartInstance.current.setOption(
      {
        tooltip: {
          trigger: 'item',
          backgroundColor: tooltipBg,
          borderColor: tooltipBorder,
          borderWidth: 1,
          textStyle: { color: tooltipTextColor, fontSize: 12 },
          formatter: (p: { data: { _task: TaskRecord } }) => {
            const t = p.data._task;
            const devs = t.devices.map((d) => `<code>${d.lab}.${d.name}</code>`).join(', ') || 'none';
            const res = Object.values(t.resources).join(', ') || 'none';
            return (
              `<div style="min-width:220px">` +
              `<div style="font-weight:600;margin-bottom:6px">${t.task}</div>` +
              `<div style="opacity:0.7;margin-bottom:6px">${t.protocol_run}</div>` +
              `<table style="font-size:12px;width:100%">` +
              `<tr><td style="opacity:0.6;padding:1px 8px 1px 0">Start</td><td>${fmtTime(t.start)}</td></tr>` +
              `<tr><td style="opacity:0.6;padding:1px 8px 1px 0">Duration</td><td>${fmtTime(t.duration)}</td></tr>` +
              `<tr><td style="opacity:0.6;padding:1px 8px 1px 0">End</td><td>${fmtTime(t.end)}</td></tr>` +
              `<tr><td style="opacity:0.6;padding:1px 8px 1px 0">Devices</td><td>${devs}</td></tr>` +
              `<tr><td style="opacity:0.6;padding:1px 8px 1px 0">Resources</td><td>${res}</td></tr>` +
              `</table></div>`
            );
          },
        },
        grid: { left: 180, right: 20, top: 30, bottom: 50 },
        xAxis: {
          type: 'value',
          min: 0,
          max: stats.makespan,
          name: 'Time',
          nameLocation: 'middle',
          nameGap: 30,
          nameTextStyle: { fontSize: 12, color: textColor },
          axisLabel: { formatter: (v: number) => fmtTime(v), fontSize: 11, color: textColor },
          axisLine: { lineStyle: { color: borderColor } },
          splitLine: { lineStyle: { color: gridColor } },
        },
        yAxis: {
          type: 'category',
          data: v.categories,
          inverse: true,
          axisLabel: { fontSize: 11, color: textColor, width: 160, overflow: 'truncate' },
          axisTick: { show: false },
          axisLine: { lineStyle: { color: borderColor } },
          splitLine: { show: true, lineStyle: { color: gridColor } },
        },
        dataZoom: [
          { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
          { type: 'inside', yAxisIndex: 0, filterMode: 'none' },
          {
            type: 'slider',
            xAxisIndex: 0,
            bottom: 10,
            height: 20,
            borderColor,
            fillerColor: isDark ? 'rgba(234, 179, 8, 0.08)' : 'rgba(67, 97, 238, 0.08)',
            handleStyle: { color: isDark ? '#eab308' : '#4361ee' },
            labelFormatter: (v: number) => fmtTime(Math.round(v)),
          },
        ],
        series: [
          {
            type: 'custom',
            renderItem: (
              params: { dataIndex: number },
              api: {
                value: (i: number) => number;
                coord: (v: [number, number]) => [number, number];
                size: (v: [number, number]) => [number, number];
                style: () => Record<string, unknown>;
                visual: (v: string) => string;
              }
            ) => {
              const laneIdx = api.value(1);
              const start = api.coord([api.value(0), laneIdx]);
              const end = api.coord([api.value(2), laneIdx]);
              const bandW = api.size([0, 1])[1] * 0.65;
              const w = Math.max(end[0] - start[0], 2);
              const x = start[0];
              const y = start[1] - bandW / 2;
              const task = seriesData[params.dataIndex]._task;
              const colors = taskColors(task.task);
              const padding = 6;
              const textW = w - padding * 2;
              const children: Record<string, unknown>[] = [
                {
                  type: 'rect',
                  shape: { x: 0, y: 0, width: w, height: bandW, r: 3 },
                  style: { fill: api.visual('color') },
                  emphasis: { style: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.15)' } },
                },
              ];
              if (textW > 16) {
                const fontSize = Math.min(Math.max(9, w / 12), bandW - 4, 14);
                children.push({
                  type: 'text',
                  style: {
                    text: task.task,
                    x: padding,
                    y: bandW / 2,
                    fill: colors.fg,
                    fontSize,
                    textVerticalAlign: 'middle',
                    width: textW,
                    overflow: 'truncate',
                    ellipsis: '...',
                  },
                });
              }
              return { type: 'group', x, y, children };
            },
            encode: { x: [0, 2], y: 1 },
            data: seriesData,
            clip: true,
          },
        ],
        animation: false,
      },
      true
    );
  }, [timeline, stats, view, isDark, maximized]);

  useEffect(() => {
    return () => {
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, []);

  return (
    <div
      ref={wrapperRef}
      className="bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700"
    >
      <div className="flex items-center justify-between p-3 border-b border-gray-200 dark:border-slate-700">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setView('protocol')}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
              view === 'protocol'
                ? 'bg-blue-50 text-blue-600 dark:bg-yellow-500/10 dark:text-yellow-500'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            Protocol Runs
          </button>
          <button
            onClick={() => setView('device')}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
              view === 'device'
                ? 'bg-blue-50 text-blue-600 dark:bg-yellow-500/10 dark:text-yellow-500'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            Devices
          </button>
        </div>
        <button
          onClick={() => setMaximized((m) => !m)}
          className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors"
          title={maximized ? 'Minimize' : 'Maximize'}
        >
          {maximized ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </button>
      </div>
      <div ref={chartRef} style={{ width: '100%', minHeight: 600 }} />
    </div>
  );
}
