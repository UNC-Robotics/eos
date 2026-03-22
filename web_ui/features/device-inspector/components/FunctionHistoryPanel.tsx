'use client';

import * as React from 'react';
import { ChevronDown, ChevronRight, Trash2, CheckCircle, XCircle, Clock } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { JsonDisplay } from '@/components/ui/JsonDisplay';
import { ScrollArea } from '@/components/ui/ScrollArea';
import { useDeviceInspectorStore } from '@/lib/stores/deviceInspectorStore';

export function FunctionHistoryPanel() {
  const [isExpanded, setIsExpanded] = React.useState(false);
  const [expandedCalls, setExpandedCalls] = React.useState<Set<string>>(new Set());

  const { callHistory, clearCallHistory } = useDeviceInspectorStore();

  const toggleCallExpanded = (callId: string) => {
    setExpandedCalls((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(callId)) {
        newSet.delete(callId);
      } else {
        newSet.add(callId);
      }
      return newSet;
    });
  };

  const formatTimestamp = (timestamp: number) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  const formatDuration = (duration: number | undefined) => {
    if (!duration) return 'N/A';
    if (duration < 1000) return `${duration}ms`;
    return `${(duration / 1000).toFixed(2)}s`;
  };

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-gray-100 hover:text-gray-700 dark:hover:text-gray-300"
        >
          {isExpanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
          Call History
          {callHistory.length > 0 && (
            <Badge variant="default" className="ml-2">
              {callHistory.length}
            </Badge>
          )}
        </button>

        {callHistory.length > 0 && (
          <Button variant="outline" size="sm" onClick={clearCallHistory}>
            <Trash2 className="h-4 w-4 mr-2" />
            Clear
          </Button>
        )}
      </div>

      {/* Content */}
      {isExpanded && (
        <ScrollArea className="max-h-96">
          <div className="p-4">
            {callHistory.length === 0 ? (
              <div className="text-center text-gray-500 dark:text-gray-400 py-8">No function calls yet</div>
            ) : (
              <div className="space-y-2">
                {callHistory.map((call) => {
                  const isExpanded = expandedCalls.has(call.id);
                  const success = call.result.success;

                  return (
                    <div
                      key={call.id}
                      className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
                    >
                      {/* Call header */}
                      <button
                        onClick={() => toggleCallExpanded(call.id)}
                        className="w-full px-4 py-3 flex items-start justify-between hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                      >
                        <div className="flex items-start gap-3 flex-1 text-left">
                          {success ? (
                            <CheckCircle className="h-5 w-5 text-green-500 flex-shrink-0 mt-0.5" />
                          ) : (
                            <XCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
                          )}

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <code className="text-sm font-mono font-semibold text-gray-900 dark:text-gray-100">
                                {call.functionName}
                              </code>
                              <Badge variant={success ? 'success' : 'error'} className="text-xs">
                                {success ? 'success' : 'error'}
                              </Badge>
                            </div>

                            <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                              <div className="flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {formatTimestamp(call.timestamp)}
                              </div>
                              {call.duration !== undefined && <div>Duration: {formatDuration(call.duration)}</div>}
                            </div>
                          </div>
                        </div>

                        <div className="flex-shrink-0 ml-2">
                          {isExpanded ? (
                            <ChevronDown className="h-5 w-5 text-gray-400" />
                          ) : (
                            <ChevronRight className="h-5 w-5 text-gray-400" />
                          )}
                        </div>
                      </button>

                      {/* Call details */}
                      {isExpanded && (
                        <div className="px-4 pb-3 space-y-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
                          {/* Parameters */}
                          {Object.keys(call.parameters).length > 0 && (
                            <div>
                              <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2 mt-3">
                                Parameters
                              </div>
                              <JsonDisplay data={call.parameters} />
                            </div>
                          )}

                          {/* Result */}
                          <div>
                            <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                              {success ? 'Result' : 'Error'}
                            </div>
                            {success ? (
                              typeof call.result.result === 'object' && call.result.result !== null ? (
                                <JsonDisplay data={call.result.result} />
                              ) : (
                                <pre className="text-sm text-gray-800 dark:text-gray-200 bg-white dark:bg-gray-800 p-2 rounded border border-gray-200 dark:border-gray-700">
                                  {String(call.result.result)}
                                </pre>
                              )
                            ) : (
                              <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-2 max-h-48 overflow-y-auto">
                                <pre className="whitespace-pre-wrap break-words font-mono text-xs text-red-800 dark:text-red-200">
                                  {(call.result.error || 'Unknown error').replace(/\u001b\[[0-9;]*m/g, '')}
                                </pre>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </ScrollArea>
      )}
    </div>
  );
}
