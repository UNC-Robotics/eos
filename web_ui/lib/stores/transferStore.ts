import { create } from 'zustand';

export type TransferStatus = 'in_progress' | 'completed' | 'error';
export type TransferType = 'download' | 'upload';

export interface Transfer {
  id: string;
  fileName: string;
  type: TransferType;
  status: TransferStatus;
  progress: number;
  bytesLoaded: number;
  bytesTotal: number;
  error?: string;
}

interface TransferStore {
  transfers: Transfer[];
  addTransfer: (transfer: Omit<Transfer, 'id'>) => string;
  updateTransfer: (id: string, updates: Partial<Transfer>) => void;
  removeTransfer: (id: string) => void;
  clearCompleted: () => void;
}

let nextId = 0;

export const useTransferStore = create<TransferStore>()((set) => ({
  transfers: [],

  addTransfer: (transfer) => {
    const id = `transfer-${++nextId}`;
    set((state) => ({
      transfers: [...state.transfers, { ...transfer, id }],
    }));
    return id;
  },

  updateTransfer: (id, updates) => {
    set((state) => ({
      transfers: state.transfers.map((t) => (t.id === id ? { ...t, ...updates } : t)),
    }));
  },

  removeTransfer: (id) => {
    set((state) => ({
      transfers: state.transfers.filter((t) => t.id !== id),
    }));
  },

  clearCompleted: () => {
    set((state) => ({
      transfers: state.transfers.filter((t) => t.status !== 'completed'),
    }));
  },
}));
