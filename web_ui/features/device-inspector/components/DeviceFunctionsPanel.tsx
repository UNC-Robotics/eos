'use client';

import * as React from 'react';
import { Search, ChevronDown, ChevronRight, Zap } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { toast } from '@/lib/utils/toast';
import { getDeviceIntrospection } from '../api/inspector';
import type { SelectedDevice, DeviceFunction, DeviceIntrospection } from '@/lib/types/device-inspector';
import { useOrchestratorConnected } from '@/contexts/OrchestratorStatusContext';

interface DeviceFunctionsPanelProps {
  device: SelectedDevice;
  onFunctionCall: (functionName: string, func: DeviceFunction) => void;
}

export function DeviceFunctionsPanel({ device, onFunctionCall }: DeviceFunctionsPanelProps) {
  const { isConnected } = useOrchestratorConnected();
  const [functions, setFunctions] = React.useState<DeviceIntrospection | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [isExpanded, setIsExpanded] = React.useState(true);

  // Fetch available functions
  React.useEffect(() => {
    if (!isConnected) return;

    const fetchFunctions = async () => {
      setIsLoading(true);
      try {
        const introspection = await getDeviceIntrospection(device.labName, device.deviceName);
        setFunctions(introspection);
      } catch (error) {
        console.error('Failed to fetch device functions:', error);
        toast.error('Failed to fetch device functions');
      } finally {
        setIsLoading(false);
      }
    };

    fetchFunctions();
  }, [device.labName, device.deviceName, isConnected]);

  // Filter functions based on search query
  const filteredFunctions = React.useMemo(() => {
    if (!functions) return [];

    const query = searchQuery.toLowerCase();
    return Object.entries(functions).filter(
      ([name, func]) =>
        name.toLowerCase().includes(query) ||
        func.docstring.toLowerCase().includes(query) ||
        func.return_type.toLowerCase().includes(query)
    );
  }, [functions, searchQuery]);

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-gray-100 hover:text-gray-700 dark:hover:text-gray-300"
        >
          {isExpanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
          Available Functions
          {functions && (
            <Badge variant="default" className="ml-2">
              {Object.keys(functions).length}
            </Badge>
          )}
        </button>
      </div>

      {/* Content */}
      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              type="text"
              placeholder="Search functions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* Functions list */}
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-24 bg-gray-200 dark:bg-gray-700 rounded-lg animate-pulse" />
              ))}
            </div>
          ) : filteredFunctions.length === 0 ? (
            <div className="text-center text-gray-500 dark:text-gray-400 py-8">
              {searchQuery ? 'No functions found matching your search' : 'No functions available'}
            </div>
          ) : (
            <div className="space-y-2">
              {filteredFunctions.map(([name, func]) => (
                <div key={name} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      {/* Function name */}
                      <div className="flex items-center gap-2 mb-2">
                        <code className="text-sm font-mono font-semibold text-blue-600 dark:text-yellow-400">
                          {name}
                        </code>
                        {func.is_async && (
                          <Badge variant="default" className="text-xs">
                            async
                          </Badge>
                        )}
                      </div>

                      {/* Parameters */}
                      {func.parameters.length > 0 && (
                        <div className="mb-2">
                          <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Parameters:</div>
                          <div className="flex flex-wrap gap-1">
                            {func.parameters.map((param) => (
                              <Badge
                                key={param.name}
                                variant="default"
                                className="text-xs font-mono bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                              >
                                {param.name}
                                {!param.required && '?'}: {param.type}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Return type */}
                      <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                        Returns: <code className="font-mono">{func.return_type}</code>
                      </div>

                      {/* Docstring */}
                      {func.docstring && (
                        <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">{func.docstring}</p>
                      )}
                    </div>

                    {/* Call button */}
                    <Button
                      variant="primary"
                      size="md"
                      disabled={!isConnected}
                      onClick={() => onFunctionCall(name, func)}
                      className="flex-shrink-0"
                    >
                      <Zap className="h-4 w-4 mr-1" />
                      Call
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
