'use server';

/**
 * Server Actions for Device Inspector
 */

import { revalidatePath } from 'next/cache';
import { orchestratorGet, orchestratorPost } from '@/lib/api/orchestrator';
import type { DeviceIntrospection, FunctionCallResult } from '@/lib/types/device-inspector';
import type { DeviceReport, ActionResult } from '@/lib/types/management';

/**
 * Get device introspection (available functions and their metadata)
 */
export async function getDeviceIntrospection(labName: string, deviceName: string): Promise<DeviceIntrospection> {
  try {
    const response = (await orchestratorPost(
      `/rpc/${labName}/${deviceName}/get_available_functions`,
      {}
    )) as DeviceIntrospection;
    return response;
  } catch (error) {
    console.error('Failed to fetch device introspection:', error);
    throw new Error('Failed to fetch device introspection');
  }
}

/**
 * Call a device function via RPC
 */
export async function callDeviceFunction(
  labName: string,
  deviceName: string,
  functionName: string,
  parameters: Record<string, unknown>
): Promise<FunctionCallResult> {
  try {
    const result = await orchestratorPost(`/rpc/${labName}/${deviceName}/${functionName}`, parameters);

    return {
      success: true,
      result,
    };
  } catch (error) {
    console.error(`Failed to call device function ${functionName}:`, error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to call device function',
    };
  }
}

/**
 * Get device state/report
 */
export async function getDeviceState(labName: string, deviceName: string): Promise<DeviceReport> {
  try {
    const response = (await orchestratorGet(`/labs/${labName}/device/${deviceName}/report`)) as DeviceReport;
    return response;
  } catch (error) {
    console.error('Failed to fetch device state:', error);
    throw new Error('Failed to fetch device state');
  }
}

/**
 * Reload a specific device
 */
export async function reloadDevice(labName: string, deviceName: string): Promise<ActionResult> {
  try {
    await orchestratorPost(`/labs/${labName}/devices/reload`, {
      device_names: [deviceName],
    });

    // Revalidate the device inspector page to show updated status
    revalidatePath('/devices/inspect');

    return {
      success: true,
    };
  } catch (error) {
    console.error('Failed to reload device:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to reload device',
    };
  }
}

/**
 * Get device status
 */
export async function getDeviceStatus(
  labName: string,
  deviceName: string
): Promise<{ name: string; lab_name: string; status: string }> {
  try {
    const result = (await orchestratorPost(`/rpc/${labName}/${deviceName}/get_status`, {})) as {
      name: string;
      lab_name: string;
      status: { _name_: string; _value_: string };
    };

    // The status comes as an enum object, extract the value
    const status =
      typeof result.status === 'object' && '_value_' in result.status ? result.status._value_ : String(result.status);

    return {
      name: result.name,
      lab_name: result.lab_name,
      status,
    };
  } catch (error) {
    console.error('Failed to fetch device status:', error);
    throw new Error('Failed to fetch device status');
  }
}
