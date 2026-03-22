'use client';

import * as React from 'react';

interface ParetoSolutionsTableProps {
  solutions: Array<Record<string, unknown>>;
  inputNames: string[];
  outputNames: string[];
}

export function ParetoSolutionsTable({ solutions, inputNames, outputNames }: ParetoSolutionsTableProps) {
  // Find best values for each output (for highlighting)
  const bestValues = React.useMemo(() => {
    const bests: Record<string, { value: number; isMin: boolean }> = {};

    outputNames.forEach((name) => {
      const values = solutions.map((s) => s[name] as number).filter((v) => v !== undefined);
      if (values.length === 0) return;

      // For now, assume lower is better (minimize). In a real implementation,
      // this would come from optimizer configuration.
      const minVal = Math.min(...values);
      bests[name] = { value: minVal, isMin: true };
    });

    return bests;
  }, [solutions, outputNames]);

  // Get all columns from the solutions
  const allColumns = React.useMemo(() => {
    const cols = new Set<string>();
    solutions.forEach((s) => {
      Object.keys(s).forEach((k) => cols.add(k));
    });
    return Array.from(cols);
  }, [solutions]);

  // Separate input and output columns
  const inputCols = allColumns.filter((c) => inputNames.includes(c));
  const outputCols = allColumns.filter((c) => outputNames.includes(c));
  const otherCols = allColumns.filter((c) => !inputNames.includes(c) && !outputNames.includes(c));

  if (solutions.length === 0) {
    return <p className="text-gray-500 dark:text-gray-400 text-center py-8">No Pareto solutions available.</p>;
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-slate-700">
              <th className="text-left py-2 px-3 font-medium text-gray-500 dark:text-gray-400">#</th>
              {inputCols.length > 0 && (
                <th
                  colSpan={inputCols.length}
                  className="text-center py-2 px-3 font-medium text-gray-400 dark:text-gray-500 text-xs uppercase tracking-wider border-l border-gray-200 dark:border-slate-700"
                >
                  Inputs
                </th>
              )}
              {outputCols.length > 0 && (
                <th
                  colSpan={outputCols.length}
                  className="text-center py-2 px-3 font-medium text-gray-400 dark:text-gray-500 text-xs uppercase tracking-wider border-l border-gray-200 dark:border-slate-700"
                >
                  Outputs
                </th>
              )}
            </tr>
            <tr className="border-b border-gray-200 dark:border-slate-700">
              <th className="text-left py-2 px-3 font-medium text-gray-500 dark:text-gray-400"></th>
              {inputCols.map((col, idx) => (
                <th
                  key={col}
                  className={`text-left py-2 px-3 font-medium text-gray-500 dark:text-gray-400 ${
                    idx === 0 ? 'border-l border-gray-200 dark:border-slate-700' : ''
                  }`}
                >
                  {col}
                </th>
              ))}
              {outputCols.map((col, idx) => (
                <th
                  key={col}
                  className={`text-left py-2 px-3 font-medium text-gray-500 dark:text-gray-400 ${
                    idx === 0 ? 'border-l border-gray-200 dark:border-slate-700' : ''
                  }`}
                >
                  {col}
                </th>
              ))}
              {otherCols.map((col) => (
                <th key={col} className="text-left py-2 px-3 font-medium text-gray-500 dark:text-gray-400">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {solutions.map((solution, idx) => (
              <tr
                key={idx}
                className="border-b border-gray-100 dark:border-slate-800 hover:bg-gray-50 dark:hover:bg-slate-800/50"
              >
                <td className="py-2 px-3 text-gray-500 dark:text-gray-400">{idx + 1}</td>
                {inputCols.map((col, colIdx) => (
                  <td
                    key={col}
                    className={`py-2 px-3 text-gray-900 dark:text-white font-mono text-xs ${
                      colIdx === 0 ? 'border-l border-gray-200 dark:border-slate-700' : ''
                    }`}
                  >
                    {formatValue(solution[col])}
                  </td>
                ))}
                {outputCols.map((col, colIdx) => {
                  const value = solution[col] as number;
                  const best = bestValues[col];
                  const isBest = best && value === best.value;

                  return (
                    <td
                      key={col}
                      className={`py-2 px-3 font-mono text-xs ${
                        colIdx === 0 ? 'border-l border-gray-200 dark:border-slate-700' : ''
                      } ${
                        isBest ? 'text-green-600 dark:text-green-400 font-semibold' : 'text-gray-900 dark:text-white'
                      }`}
                    >
                      {formatValue(value)}
                      {isBest && ' *'}
                    </td>
                  );
                })}
                {otherCols.map((col) => (
                  <td key={col} className="py-2 px-3 text-gray-900 dark:text-white font-mono text-xs">
                    {formatValue(solution[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">* Best value for each objective</p>
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'number') {
    return Number.isInteger(value) ? value.toString() : value.toFixed(4);
  }
  return String(value);
}
