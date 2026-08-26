const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export async function fetchIncidents(params = {}) {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_BASE}/incidents${query ? '?' + query : ''}`);
  if (!res.ok) throw new Error('Failed to fetch incidents');
  return res.json();
}

export async function fetchIncident(id) {
  const res = await fetch(`${API_BASE}/incidents/${id}`);
  if (!res.ok) throw new Error('Failed to fetch incident');
  return res.json();
}

export async function createIncident(data) {
  const res = await fetch(`${API_BASE}/incidents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create incident');
  return res.json();
}

export async function startInvestigation(id) {
  const res = await fetch(`${API_BASE}/incidents/${id}/start`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to start investigation');
  return res.json();
}

export async function executeRemediation(id) {
  const res = await fetch(`${API_BASE}/incidents/${id}/remediate`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to execute remediation');
  return res.json();
}

export async function fetchEvents(incidentId) {
  const res = await fetch(`${API_BASE}/incidents/${incidentId}/events`);
  if (!res.ok) throw new Error('Failed to fetch events');
  return res.json();
}

export async function injectChaos(faultType) {
  const res = await fetch(`${API_BASE}/chaos/${faultType}`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to inject chaos');
  return res.json();
}

export async function fetchFaults() {
  const res = await fetch(`${API_BASE}/chaos/faults`);
  if (!res.ok) throw new Error('Failed to fetch faults');
  return res.json();
}

export function streamIncident(incidentId, onEvent) {
  const eventSource = new EventSource(`${API_BASE}/stream/${incidentId}`);
  eventSource.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data));
    } catch { /* ignore */ }
  };
  eventSource.onerror = () => {
    eventSource.close();
  };
  return () => eventSource.close();
}
