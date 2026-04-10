import { useState, useEffect, useCallback } from 'react';

interface OrchestratorStatus {
  isConnected: boolean;
  isChecking: boolean;
  lastChecked: Date | null;
}

const POLL_INTERVAL = 30000; // 30 seconds

export function useOrchestratorStatus(): OrchestratorStatus & { checkNow: () => void } {
  const [isConnected, setIsConnected] = useState(false);
  const [isChecking, setIsChecking] = useState(true);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const checkHealth = useCallback(async () => {
    setIsChecking(true);
    try {
      const response = await fetch('/api/orchestrator/health');
      const data = await response.json();
      setIsConnected(data.connected);
    } catch {
      setIsConnected(false);
    } finally {
      setIsChecking(false);
      setLastChecked(new Date());
    }
  }, []);

  useEffect(() => {
    // Initial check
    checkHealth();

    // Set up polling interval
    const intervalId = setInterval(checkHealth, POLL_INTERVAL);

    // Cleanup on unmount
    return () => clearInterval(intervalId);
  }, [checkHealth]);

  return { isConnected, isChecking, lastChecked, checkNow: checkHealth };
}
