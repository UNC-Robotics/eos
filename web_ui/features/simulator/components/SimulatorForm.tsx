'use client';

import { useState } from 'react';
import { Plus, Trash2, Play, Loader2, Download, Upload } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Combobox } from '@/components/ui/Combobox';
import { DescriptionTooltip } from '@/components/ui/DescriptionTooltip';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select';
import type { SimConfig, ProtocolRunConfig } from '../types';

interface Props {
  protocolTypes: string[];
  loading: boolean;
  onRun: (config: SimConfig) => void;
  onLoadConfig: (config: SimConfig) => void;
  config: SimConfig;
  setConfig: (config: SimConfig) => void;
}

export function SimulatorForm({ protocolTypes, loading, onRun, onLoadConfig, config, setConfig }: Props) {
  const [error, setError] = useState<string | null>(null);

  const updateProtocol = (index: number, updates: Partial<ProtocolRunConfig>) => {
    const protocols = config.protocols.map((p, i) => (i === index ? { ...p, ...updates } : p));
    setConfig({ ...config, protocols });
  };

  const addProtocol = () => {
    setConfig({
      ...config,
      protocols: [...config.protocols, { type: protocolTypes[0] || '', iterations: 10, max_concurrent: 0 }],
    });
  };

  const removeProtocol = (index: number) => {
    setConfig({ ...config, protocols: config.protocols.filter((_, i) => i !== index) });
  };

  const handleSubmit = () => {
    if (config.protocols.length === 0) {
      setError('Add at least one protocol.');
      return;
    }
    if (config.protocols.some((p) => !p.type)) {
      setError('All protocols must have a type selected.');
      return;
    }
    setError(null);
    onRun(config);
  };

  const downloadConfig = () => {
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sim_config.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const uploadConfig = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const parsed = JSON.parse(text) as SimConfig;
        onLoadConfig(parsed);
      } catch {
        setError('Invalid config file.');
      }
    };
    input.click();
  };

  return (
    <div className="bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Configuration</h2>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={uploadConfig} title="Load config">
            <Upload className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={downloadConfig} title="Save config">
            <Download className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-md text-red-600 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      <div className="space-y-4">
        {/* Protocols */}
        <div>
          <Label className="mb-2 block">Protocols</Label>
          {/* Column headers */}
          <div className="flex items-center gap-2 px-3 mb-1">
            <div className="flex-1 min-w-0">
              <span className="text-xs text-gray-500 dark:text-gray-400">Type</span>
              <DescriptionTooltip description="The protocol to simulate." />
            </div>
            <div className="w-24">
              <span className="text-xs text-gray-500 dark:text-gray-400">Iterations</span>
              <DescriptionTooltip description="Number of protocol runs to create for this protocol type." />
            </div>
            <div className="w-32">
              <span className="text-xs text-gray-500 dark:text-gray-400">Max Concurrent</span>
              <DescriptionTooltip description="Maximum number of concurrent runs allowed for this protocol type. 0 means unlimited." />
            </div>
            <div className="w-8" />
          </div>
          <div className="space-y-2">
            {config.protocols.map((protocol, i) => (
              <div
                key={i}
                className="flex items-center gap-2 p-3 bg-gray-50 dark:bg-slate-800/50 rounded-md border border-gray-200 dark:border-slate-700"
              >
                <div className="flex-1 min-w-0">
                  <Combobox
                    options={protocolTypes.map((t) => ({ value: t, label: t }))}
                    value={protocol.type}
                    onChange={(v) => updateProtocol(i, { type: v })}
                    placeholder="Protocol type"
                    searchPlaceholder="Search protocols..."
                    className="h-8 text-sm"
                  />
                </div>
                <div className="w-24">
                  <Input
                    type="number"
                    min={1}
                    value={protocol.iterations}
                    onChange={(e) => updateProtocol(i, { iterations: parseInt(e.target.value) || 1 })}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="w-32">
                  <Input
                    type="number"
                    min={0}
                    value={protocol.max_concurrent}
                    onChange={(e) => updateProtocol(i, { max_concurrent: parseInt(e.target.value) || 0 })}
                    className="h-8 text-sm"
                  />
                </div>
                <Button variant="ghost" size="sm" onClick={() => removeProtocol(i)} className="h-8 w-8 p-0">
                  <Trash2 className="h-4 w-4 text-gray-400" />
                </Button>
              </div>
            ))}
          </div>
          <Button variant="ghost" size="sm" onClick={addProtocol} className="mt-2">
            <Plus className="h-4 w-4 mr-1" />
            Add Protocol
          </Button>
        </div>

        {/* Settings row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <Label htmlFor="scheduler" className="mb-1 block">
              Scheduler
              <DescriptionTooltip description="The scheduling algorithm to use. Greedy schedules tasks as soon as resources are available. CP-SAT uses constraint programming to find an optimal schedule." />
            </Label>
            <Select value={config.scheduler} onValueChange={(v) => setConfig({ ...config, scheduler: v })}>
              <SelectTrigger id="scheduler" className="h-9 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="greedy">Greedy</SelectItem>
                <SelectItem value="cpsat">CP-SAT</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="jitter" className="mb-1 block">
              Jitter
              <DescriptionTooltip description="Random variation applied to task durations. For example, 10% means each task duration varies by up to ±10%. Task durations are always at least 1 second." />
            </Label>
            <div className="relative">
              <Input
                id="jitter"
                type="number"
                min={0}
                step={1}
                value={Math.round(config.jitter * 100)}
                onChange={(e) => setConfig({ ...config, jitter: (parseFloat(e.target.value) || 0) / 100 })}
                className="h-9 text-sm pr-8"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-400 dark:text-gray-500 pointer-events-none">
                %
              </span>
            </div>
          </div>
          <div>
            <Label htmlFor="seed" className="mb-1 block">
              Seed
              <DescriptionTooltip description="Random seed for reproducible simulation results. Leave empty for a random seed." />
            </Label>
            <Input
              id="seed"
              type="number"
              value={config.seed ?? ''}
              onChange={(e) => setConfig({ ...config, seed: e.target.value ? parseInt(e.target.value) : null })}
              className="h-9 text-sm"
              placeholder="Optional"
            />
          </div>
          <div className="flex items-end">
            <Button variant="primary" onClick={handleSubmit} disabled={loading} className="w-full h-9">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {loading ? 'Running...' : 'Run'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
