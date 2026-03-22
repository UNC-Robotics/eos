/**
 * EOS Orchestrator API Client
 *
 * Handles communication with the EOS orchestrator backend API.
 */

const ORCHESTRATOR_BASE_URL = process.env.ORCHESTRATOR_API_URL || 'http://localhost:8070/api';

/**
 * Make a POST request to the orchestrator API
 */
export async function orchestratorPost(endpoint: string, data?: unknown): Promise<unknown> {
  const url = `${ORCHESTRATOR_BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: data ? JSON.stringify(data) : undefined,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Orchestrator API error (${response.status}): ${errorText}`);
  }

  // Check content type to determine how to parse response
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  } else {
    // Return text for non-JSON responses
    return response.text();
  }
}

/**
 * Make a GET request to the orchestrator API
 */
export async function orchestratorGet(endpoint: string): Promise<unknown> {
  const url = `${ORCHESTRATOR_BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Orchestrator API error (${response.status}): ${errorText}`);
  }

  // Check content type to determine how to parse response
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  } else {
    // Return text for non-JSON responses
    return response.text();
  }
}

/**
 * Make a PUT request to the orchestrator API
 */
export async function orchestratorPut(endpoint: string, data?: unknown): Promise<unknown> {
  const url = `${ORCHESTRATOR_BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: data ? JSON.stringify(data) : undefined,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Orchestrator API error (${response.status}): ${errorText}`);
  }

  // Check content type to determine how to parse response
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  } else {
    // Return text for non-JSON responses
    return response.text();
  }
}
