'use client';

import { useState, useEffect, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { Download, Upload } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { fetchPackages, fetchProtocolTypes, runSimulation } from '../api/simulator';
import type { SimConfig, SimResults } from '../types';
import { SimulatorForm } from './SimulatorForm';
import { SimulatorStats } from './SimulatorStats';

const SimulatorGantt = dynamic(() => import('./SimulatorGantt'), {
  ssr: false,
  loading: () => (
    <div className="bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 p-8 flex items-center justify-center min-h-[400px]">
      <div className="text-gray-400 dark:text-gray-500">Loading chart...</div>
    </div>
  ),
});

const DEFAULT_CONFIG: SimConfig = {
  packages: [],
  protocols: [{ type: '', iterations: 10, max_concurrent: 0 }],
  scheduler: 'greedy',
  jitter: 0,
  seed: null,
};

export function SimulatorClient() {
  const [packages, setPackages] = useState<string[]>([]);
  const [protocolTypes, setProtocolTypes] = useState<string[]>([]);
  const [config, setConfig] = useState<SimConfig>(DEFAULT_CONFIG);
  const [results, setResults] = useState<SimResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [pkgs, protos] = await Promise.all([fetchPackages(), fetchProtocolTypes()]);
        const pkgNames = Object.keys(pkgs);
        const protoNames = Object.keys(protos);
        setPackages(pkgNames);
        setProtocolTypes(protoNames);
        if (pkgNames.length > 0) {
          setConfig((prev) => ({
            ...prev,
            packages: pkgNames,
            protocols: prev.protocols.map((p) => ({
              ...p,
              type: p.type || protoNames[0] || '',
            })),
          }));
        }
      } catch {
        // Orchestrator may not be running
      }
    };
    load();
  }, []);

  const handleRun = useCallback(
    async (cfg: SimConfig) => {
      setLoading(true);
      setError(null);
      try {
        const res = await runSimulation({ ...cfg, packages: packages.length > 0 ? packages : cfg.packages });
        setResults(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Simulation failed');
      } finally {
        setLoading(false);
      }
    },
    [packages]
  );

  const handleLoadConfig = useCallback((cfg: SimConfig) => {
    setConfig(cfg);
  }, []);

  const downloadResults = () => {
    if (!results) return;
    const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sim_results.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const uploadResults = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const parsed = JSON.parse(text) as SimResults;
        if (parsed.timeline && parsed.stats) {
          setResults(parsed);
          setError(null);
        } else {
          setError('Invalid results file.');
        }
      } catch {
        setError('Invalid results file.');
      }
    };
    input.click();
  };

  return (
    <div className="space-y-6">
      <SimulatorForm
        protocolTypes={protocolTypes}
        loading={loading}
        onRun={handleRun}
        onLoadConfig={handleLoadConfig}
        config={config}
        setConfig={setConfig}
      />

      {error && (
        <div className="p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-md text-red-600 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      {results && (
        <>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Results
              <span className="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">
                Makespan: {results.stats.makespan_fmt} &middot; {results.stats.total_tasks} tasks &middot;{' '}
                {results.stats.scheduler_type}
              </span>
            </h2>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={uploadResults} title="Load results">
                <Upload className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="sm" onClick={downloadResults} title="Save results">
                <Download className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <SimulatorStats stats={results.stats} />
          <SimulatorGantt timeline={results.timeline} stats={results.stats} />
        </>
      )}

      {!results && !loading && (
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <p className="text-gray-400 dark:text-gray-500 mb-2">No simulation results yet</p>
            <p className="text-sm text-gray-400 dark:text-gray-500">
              Configure and run a simulation, or{' '}
              <button onClick={uploadResults} className="text-blue-600 dark:text-yellow-500 hover:underline">
                load results
              </button>{' '}
              from a file.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
