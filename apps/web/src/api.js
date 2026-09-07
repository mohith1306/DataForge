const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

// ── Auth Helpers ─────────────────────────────────────────────────────────────

function getApiKey() {
  return localStorage.getItem('dataforge_api_key');
}

function getHeaders(includeContentType = true) {
  const headers = {};
  if (includeContentType) {
    headers['Content-Type'] = 'application/json';
  }
  const apiKey = getApiKey();
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }
  return headers;
}

// ── Auth API ─────────────────────────────────────────────────────────────────

export async function getCurrentUser() {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Not authenticated');
  return res.json();
}

export async function createApiKey(data) {
  const res = await fetch(`${API_BASE}/auth/api-keys`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create API key');
  }
  return res.json();
}

export async function listApiKeys() {
  const res = await fetch(`${API_BASE}/auth/api-keys`, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to fetch API keys');
  return res.json();
}

export async function revokeApiKey(keyId) {
  const res = await fetch(`${API_BASE}/auth/api-keys/${keyId}`, {
    method: 'DELETE',
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to revoke API key');
  return res.json();
}

// ── Connector API ────────────────────────────────────────────────────────────

export async function listConnectors() {
  console.log('[API] GET /connectors');
  const res = await fetch(`${API_BASE}/connectors`, {
    headers: getHeaders(false),
  });
  console.log('[API] Response:', res.status);
  if (!res.ok) throw new Error('Failed to fetch connectors');
  return res.json();
}

export async function addConnector(data) {
  console.log('[API] POST /connectors', data.name, data.db_type);
  const res = await fetch(`${API_BASE}/connectors`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  console.log('[API] Response:', res.status);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.message || 'Connection failed');
  }
  return res.json();
}

export async function deleteConnector(id) {
  console.log('[API] DELETE /connectors/' + id);
  const res = await fetch(`${API_BASE}/connectors/${id}`, {
    method: 'DELETE',
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to delete connector');
  return res.json();
}

export async function testConnector(id) {
  console.log('[API] POST /connectors/' + id + '/test');
  const res = await fetch(`${API_BASE}/connectors/${id}/test`, {
    method: 'POST',
    headers: getHeaders(false),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Test failed');
  }
  return res.json();
}

export async function runConnectorCheck(id) {
  console.log('[API] POST /connectors/' + id + '/check');
  const res = await fetch(`${API_BASE}/connectors/${id}/check`, {
    method: 'POST',
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Check failed');
  return res.json();
}

export async function getConnector(id) {
  console.log('[API] GET /connectors/' + id);
  const res = await fetch(`${API_BASE}/connectors/${id}`, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Connector not found');
  return res.json();
}

export async function injectTestData(id) {
  console.log('[API] POST /connectors/' + id + '/inject');
  const res = await fetch(`${API_BASE}/connectors/${id}/inject`, {
    method: 'POST',
    headers: getHeaders(false),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Inject failed');
  }
  return res.json();
}

// ── Incidents API ────────────────────────────────────────────────────────────

export async function fetchStats() {
  console.log('[API] GET /incidents/stats');
  const res = await fetch(`${API_BASE}/incidents/stats`, {
    headers: getHeaders(false),
  });
  console.log('[API] Response:', res.status, res.statusText);
  if (!res.ok) throw new Error('Failed to fetch stats');
  const data = await res.json();
  console.log('[API] Stats:', data);
  return data;
}

export async function fetchIncidents(params = {}) {
  const query = new URLSearchParams(params).toString();
  console.log('[API] GET /incidents', query ? `?${query}` : '');
  const res = await fetch(`${API_BASE}/incidents${query ? '?' + query : ''}`, {
    headers: getHeaders(false),
  });
  console.log('[API] Response:', res.status, res.statusText);
  if (!res.ok) throw new Error('Failed to fetch incidents');
  const data = await res.json();
  console.log('[API] Incidents count:', data.length);
  return data;
}

export async function fetchIncident(id) {
  console.log('[API] GET /incidents/' + id);
  const res = await fetch(`${API_BASE}/incidents/${id}`, {
    headers: getHeaders(false),
  });
  console.log('[API] Response:', res.status, res.statusText);
  if (!res.ok) throw new Error('Failed to fetch incident');
  const data = await res.json();
  console.log('[API] Incident:', data.title, '| status:', data.status);
  return data;
}

export async function createIncident(data) {
  console.log('[API] POST /incidents', data);
  const res = await fetch(`${API_BASE}/incidents`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  console.log('[API] Response:', res.status, res.statusText);
  if (!res.ok) throw new Error('Failed to create incident');
  const result = await res.json();
  console.log('[API] Created incident:', result.id, result.title);
  return result;
}

export async function startInvestigation(id) {
  console.log('[API] POST /incidents/' + id + '/start');
  const res = await fetch(`${API_BASE}/incidents/${id}/start`, {
    method: 'POST',
    headers: getHeaders(false),
  });
  console.log('[API] Response:', res.status, res.statusText);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    console.error('[API] Start investigation failed:', err);
    throw new Error(err.detail || 'Failed to start investigation');
  }
  const result = await res.json();
  console.log('[API] Investigation started:', result);
  return result;
}

export async function executeRemediation(id) {
  console.log('[API] POST /incidents/' + id + '/remediate');
  const res = await fetch(`${API_BASE}/incidents/${id}/remediate`, {
    method: 'POST',
    headers: getHeaders(false),
  });
  console.log('[API] Response:', res.status, res.statusText);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    console.error('[API] Execute remediation failed:', err);
    throw new Error(err.detail || 'Failed to execute remediation');
  }
  const result = await res.json();
  console.log('[API] Remediation started:', result);
  return result;
}

export async function approveIncident(id, action, reviewer = 'ui_user') {
  console.log('[API] POST /incidents/' + id + '/approval', { action, reviewer });
  const res = await fetch(`${API_BASE}/incidents/${id}/approval`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ action, reviewer }),
  });
  console.log('[API] Response:', res.status, res.statusText);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    console.error('[API] Approval failed:', err);
    throw new Error(err.detail || 'Failed to submit approval');
  }
  const result = await res.json();
  console.log('[API] Approval result:', result);
  return result;
}

export async function fetchEvents(incidentId) {
  console.log('[API] GET /incidents/' + incidentId + '/events');
  const res = await fetch(`${API_BASE}/incidents/${incidentId}/events`, {
    headers: getHeaders(false),
  });
  console.log('[API] Response:', res.status, res.statusText);
  if (!res.ok) throw new Error('Failed to fetch events');
  const data = await res.json();
  console.log('[API] Events count:', data.length);
  return data;
}

// ── Chaos API ────────────────────────────────────────────────────────────────

export async function injectChaos(faultType) {
  console.log('[API] POST /chaos/' + faultType);
  const res = await fetch(`${API_BASE}/chaos/${faultType}`, {
    method: 'POST',
    headers: getHeaders(false),
  });
  console.log('[API] Response:', res.status, res.statusText);
  if (!res.ok) throw new Error('Failed to inject chaos');
  const result = await res.json();
  console.log('[API] Chaos injected:', result);
  return result;
}

export async function fetchFaults() {
  console.log('[API] GET /chaos/faults');
  const res = await fetch(`${API_BASE}/chaos/faults`, {
    headers: getHeaders(false),
  });
  console.log('[API] Response:', res.status, res.statusText);
  if (!res.ok) throw new Error('Failed to fetch faults');
  const data = await res.json();
  console.log('[API] Faults:', data);
  return data;
}

// ── Reliability Graph API ────────────────────────────────────────────────────

export async function createGraphNode(data) {
  const res = await fetch(`${API_BASE}/graph/nodes`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create node');
  }
  return res.json();
}

export async function listGraphNodes(params = {}) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE}/graph/nodes${query ? '?' + query : ''}`, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to fetch nodes');
  return res.json();
}

export async function getGraphNode(id) {
  const res = await fetch(`${API_BASE}/graph/nodes/${id}`, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Node not found');
  return res.json();
}

export async function updateGraphNode(id, data) {
  const res = await fetch(`${API_BASE}/graph/nodes/${id}`, {
    method: 'PATCH',
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update node');
  }
  return res.json();
}

export async function deleteGraphNode(id) {
  const res = await fetch(`${API_BASE}/graph/nodes/${id}`, {
    method: 'DELETE',
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to delete node');
  return res.json();
}

export async function createGraphEdge(data) {
  const res = await fetch(`${API_BASE}/graph/edges`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create edge');
  }
  return res.json();
}

export async function listGraphEdges(params = {}) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE}/graph/edges${query ? '?' + query : ''}`, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to fetch edges');
  return res.json();
}

export async function deleteGraphEdge(id) {
  const res = await fetch(`${API_BASE}/graph/edges/${id}`, {
    method: 'DELETE',
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to delete edge');
  return res.json();
}

export async function getUpstreamNodes(nodeId, depth = 5) {
  const res = await fetch(`${API_BASE}/graph/nodes/${nodeId}/upstream?depth=${depth}`, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to fetch upstream nodes');
  return res.json();
}

export async function getDownstreamNodes(nodeId, depth = 5) {
  const res = await fetch(`${API_BASE}/graph/nodes/${nodeId}/downstream?depth=${depth}`, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to fetch downstream nodes');
  return res.json();
}

export async function getSubgraph(nodeId, depth = 3) {
  const res = await fetch(`${API_BASE}/graph/nodes/${nodeId}/subgraph?depth=${depth}`, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to fetch subgraph');
  return res.json();
}

export async function getBlastRadius(nodeId, depth = 10) {
  const res = await fetch(`${API_BASE}/graph/nodes/${nodeId}/blast-radius?depth=${depth}`, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to calculate blast radius');
  return res.json();
}

export async function getReliabilityScore(nodeId) {
  const res = await fetch(`${API_BASE}/graph/nodes/${nodeId}/reliability-score`, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to get reliability score');
  return res.json();
}

export async function getGraphStats() {
  const res = await fetch(`${API_BASE}/graph/stats`, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error('Failed to fetch graph stats');
  return res.json();
}

// ── SSE Streaming ────────────────────────────────────────────────────────────

export function streamIncident(incidentId, onEvent) {
  console.log('[SSE] Connecting to /stream/' + incidentId);
  const eventSource = new EventSource(`${API_BASE}/stream/${incidentId}`);

  eventSource.onopen = () => {
    console.log('[SSE] Connection opened for incident:', incidentId);
  };

  eventSource.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      console.log('[SSE] Event:', event.type, event.data?.message || '');
      onEvent(event);
    } catch (err) {
      console.error('[SSE] Parse error:', err);
    }
  };

  eventSource.onerror = (err) => {
    console.error('[SSE] Connection error:', err);
  };

  return () => {
    console.log('[SSE] Closing connection for incident:', incidentId);
    eventSource.close();
  };
}
