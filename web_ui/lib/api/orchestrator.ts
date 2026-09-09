/**
 * EOS Orchestrator API Client
 *
 * Handles communication with the EOS orchestrator backend API.
 */

import { getAccessToken } from '@/lib/auth/session';

export const ORCHESTRATOR_BASE_URL = process.env.ORCHESTRATOR_API_URL || 'http://localhost:8070/api';

async function buildHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = await getAccessToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

async function handleErrorResponse(response: Response): Promise<never> {
  const text = await response.text();
  let detail: string;
  try {
    const errorJson = JSON.parse(text);
    detail = errorJson.error || text;
  } catch {
    detail = text;
  }
  // Strip ANSI color codes
  detail = detail.replace(/\u001b\[[0-9;]*m/g, '');
  throw new Error(detail);
}

async function parseResponse(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }
  return response.text();
}

/**
 * Make a POST request to the orchestrator API
 */
export async function orchestratorPost(endpoint: string, data?: unknown): Promise<unknown> {
  const response = await fetch(`${ORCHESTRATOR_BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: await buildHeaders(),
    body: data ? JSON.stringify(data) : undefined,
  });

  if (!response.ok) await handleErrorResponse(response);
  return parseResponse(response);
}

/**
 * Make a GET request to the orchestrator API
 */
export async function orchestratorGet(endpoint: string): Promise<unknown> {
  const response = await fetch(`${ORCHESTRATOR_BASE_URL}${endpoint}`, {
    method: 'GET',
    headers: await buildHeaders(),
    cache: 'no-store',
  });

  if (!response.ok) await handleErrorResponse(response);
  return parseResponse(response);
}

/**
 * Make a PUT request to the orchestrator API
 */
export async function orchestratorPut(endpoint: string, data?: unknown): Promise<unknown> {
  const response = await fetch(`${ORCHESTRATOR_BASE_URL}${endpoint}`, {
    method: 'PUT',
    headers: await buildHeaders(),
    body: data ? JSON.stringify(data) : undefined,
  });

  if (!response.ok) await handleErrorResponse(response);
  return parseResponse(response);
}

/**
 * Make a DELETE request to the orchestrator API
 */
export async function orchestratorDelete(endpoint: string): Promise<unknown> {
  const response = await fetch(`${ORCHESTRATOR_BASE_URL}${endpoint}`, {
    method: 'DELETE',
    headers: await buildHeaders(),
  });

  if (!response.ok) await handleErrorResponse(response);
  return parseResponse(response);
}
