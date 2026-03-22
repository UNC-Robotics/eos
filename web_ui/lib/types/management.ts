/**
 * Type definitions for the Management UI
 */

export type DeviceStatus = 'ACTIVE' | 'INACTIVE';

export interface Device {
  name: string;
  lab_name: string;
  type: string;
  computer: string;
  status: DeviceStatus;
  meta: Record<string, unknown>;
}

export interface DeviceReport {
  [key: string]: unknown;
}

export interface Lab {
  name: string;
  loaded: boolean;
}

export interface TaskPluginInfo {
  type: string;
  description?: string;
}

export interface ExperimentType {
  name: string;
  loaded: boolean;
}

export interface PackageInfo {
  name: string;
  active: boolean;
}

export interface ActionResult<T = void> {
  success: boolean;
  data?: T;
  error?: string;
}
