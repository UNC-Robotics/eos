import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { SelectedDevice, FunctionCall } from '@/lib/types/device-inspector';

interface DeviceInspectorStore {
  // Selected device
  selectedDevice: SelectedDevice | null;

  // Auto-refresh state
  autoRefreshEnabled: boolean;
  refreshInterval: number; // in milliseconds

  // Function call history
  callHistory: FunctionCall[];
  maxHistorySize: number;

  // Last refresh timestamp
  lastRefreshTime: number | null;

  // Actions
  setSelectedDevice: (device: SelectedDevice | null) => void;
  setAutoRefreshEnabled: (enabled: boolean) => void;
  setRefreshInterval: (interval: number) => void;
  addFunctionCall: (call: FunctionCall) => void;
  clearCallHistory: () => void;
  updateLastRefreshTime: () => void;
}

export const useDeviceInspectorStore = create<DeviceInspectorStore>()(
  persist(
    (set) => ({
      // Initial state
      selectedDevice: null,
      autoRefreshEnabled: false,
      refreshInterval: 3000, // 3 seconds default
      callHistory: [],
      maxHistorySize: 50,
      lastRefreshTime: null,

      // Actions
      setSelectedDevice: (device) => set({ selectedDevice: device }),

      setAutoRefreshEnabled: (enabled) => set({ autoRefreshEnabled: enabled }),

      setRefreshInterval: (interval) => set({ refreshInterval: interval }),

      addFunctionCall: (call) =>
        set((state) => ({
          callHistory: [call, ...state.callHistory].slice(0, state.maxHistorySize),
        })),

      clearCallHistory: () => set({ callHistory: [] }),

      updateLastRefreshTime: () => set({ lastRefreshTime: Date.now() }),
    }),
    {
      name: 'eos-device-inspector-storage',
      storage: createJSONStorage(() => localStorage),
      // Only persist selected device and call history, not refresh state
      partialize: (state) => ({
        selectedDevice: state.selectedDevice,
        callHistory: state.callHistory,
        refreshInterval: state.refreshInterval,
      }),
    }
  )
);
