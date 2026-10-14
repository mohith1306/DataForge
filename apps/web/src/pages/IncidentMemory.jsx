import { useState, useEffect } from 'react';

const SEVERITY_COLORS = {
  critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#22c55e',
};

export default function IncidentMemory() {
  const [stats, setStats] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [searchCategory, setSearchCategory] = useState('');
  const [searchService, setSearchService] = useState('');
  const [selected, setSelected] = useState(null);
  const [preventionTips, setPreventionTips] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { load(); }, []);

  async function load() {
    try {
      const [statsRes, searchRes, tipsRes] = await Promise.all([
        fetch('/api/commercial/memory/stats', { headers: authHeaders() }).then(r => r.json()),
        fetch('/api/commercial/memory/search', {
          method: 'POST',
          headers: authHeaders(),
          body: JSON.stringify({ limit: 50 }),
        }).then(r => r.json()),
        fetch('/api/commercial/memory/prevention-tips', { headers: authHeaders() }).then(r => r.json()),
      ]);
      setStats(statsRes);
      setIncidents(searchRes.incidents || []);
      setPreventionTips(tipsRes.tips || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function searchMemory(cat, svc) {
    try {
      const res = await fetch('/api/commercial/memory/search', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          category: cat || null,
          service: svc || null,
          limit: 50,
        }),
      }).then(r => r.json());
      setIncidents(res.incidents || []);
    } catch (err) {
      console.error(err);
    }
  }

  async function handleSearch() {
    await searchMemory(searchCategory, searchService);
  }

  async function recordSample() {
    try {
      await fetch('/api/commercial/memory/incident', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          title: 'Sample: Orders pipeline timeout',
          description: 'Pipeline failed due to connection timeout',
          severity: 'high',
          category: 'pipeline_failure',
          root_cause: 'Database overloaded during peak hours',
          resolution: 'Scaled connection pool and restarted pipeline',
          affected_services: ['pg-main', 'orders-pipeline'],
          error_signatures: ['connection_timeout', 'pool_exhausted'],
          resolution_steps: ['Increased pool size', 'Restarted pipeline', 'Verified data freshness'],
          prevention_tip: 'Monitor connection pool usage during peak hours',
        }),
      });
      load();
    } catch (err) {
      console.error(err);
    }
  }

  if (loading) return <div className="loading">Loading incident memory...</div>;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ margin: 0, fontSize: '1.25rem' }}>Incident Memory — Failure DNA</h2>
        <button className="btn btn-primary" onClick={recordSample} style={{ fontSize: '0.8rem' }}>
          + Record Sample Incident
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
          <div className="stat-card">
            <div className="stat-value">{stats.total_records}</div>
            <div className="stat-label">Total Incidents</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: '#8b5cf6' }}>{stats.unique_dna}</div>
            <div className="stat-label">Unique DNA Patterns</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: '#3b82f6' }}>{stats.services_affected}</div>
            <div className="stat-label">Services Affected</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: '#22c55e' }}>{Object.keys(stats.categories || {}).length}</div>
            <div className="stat-label">Categories</div>
          </div>
        </div>
      )}

      {/* Category breakdown */}
      {stats?.categories && Object.keys(stats.categories).length > 0 && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">Categories</div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {Object.entries(stats.categories).map(([cat, count]) => (
              <span
                key={cat}
                style={{
                  fontSize: '0.8rem', background: '#1a1a1a', border: '1px solid #333',
                  borderRadius: '4px', padding: '0.25rem 0.75rem', color: '#ccc', cursor: 'pointer',
                }}
                onClick={() => { setSearchCategory(cat); searchMemory(cat, searchService); }}
              >
                {cat} <span style={{ color: '#8b5cf6', fontWeight: 600 }}>{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Search */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header">Search Memory</div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <input
            placeholder="Category (e.g. pipeline_failure)"
            value={searchCategory}
            onChange={e => setSearchCategory(e.target.value)}
            style={{
              background: '#1a1a1a', border: '1px solid #333', borderRadius: '4px',
              padding: '0.5rem 0.75rem', color: '#e5e5e5', fontSize: '0.85rem', flex: 1,
            }}
          />
          <input
            placeholder="Service (e.g. pg-main)"
            value={searchService}
            onChange={e => setSearchService(e.target.value)}
            style={{
              background: '#1a1a1a', border: '1px solid #333', borderRadius: '4px',
              padding: '0.5rem 0.75rem', color: '#e5e5e5', fontSize: '0.85rem', flex: 1,
            }}
          />
          <button className="btn btn-primary" onClick={handleSearch} style={{ fontSize: '0.8rem' }}>
            Search
          </button>
          <button className="btn" onClick={() => { setSearchCategory(''); setSearchService(''); load(); }} style={{ fontSize: '0.8rem', background: '#333', color: '#ccc' }}>
            Clear
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>
        {/* Incident list */}
        <div className="card">
          <div className="card-header">Past Incidents ({incidents.length})</div>
          {incidents.length === 0 ? (
            <div style={{ color: '#666', fontSize: '0.85rem' }}>No incidents in memory</div>
          ) : (
            <div className="incident-list">
              {incidents.map(inc => (
                <div
                  key={inc.incident_id}
                  className="incident-row"
                  style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    cursor: 'pointer', padding: '0.6rem 0',
                    borderBottom: '1px solid #222',
                  }}
                  onClick={() => setSelected(selected?.incident_id === inc.incident_id ? null : inc)}
                >
                  <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flex: 1 }}>
                    <span
                      style={{
                        width: '8px', height: '8px', borderRadius: '50%', flexShrink: 0,
                        background: SEVERITY_COLORS[inc.severity] || '#666',
                      }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#e5e5e5' }}>
                        {inc.title}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: '#888' }}>
                        {inc.category} · {inc.severity} · {inc.affected_services?.join(', ')}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '0.375rem', alignItems: 'center' }}>
                    {inc.failure_dna && (
                      <span style={{
                        fontSize: '0.65rem', background: '#8b5cf620', color: '#8b5cf6',
                        borderRadius: '3px', padding: '0.125rem 0.375rem', fontFamily: 'monospace',
                      }}>
                        {inc.failure_dna.fingerprint}
                      </span>
                    )}
                    <span style={{ fontSize: '0.7rem', color: '#555' }}>
                      {selected?.incident_id === inc.incident_id ? '▾' : '▸'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Expanded detail */}
          {selected && (
            <div style={{
              marginTop: '1rem', padding: '1rem', background: '#0a0a0a',
              border: '1px solid #333', borderRadius: '8px',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                <span style={{ fontWeight: 700, fontSize: '0.95rem', color: '#e5e5e5' }}>{selected.title}</span>
                <span style={{
                  fontSize: '0.7rem', background: `${SEVERITY_COLORS[selected.severity]}20`,
                  color: SEVERITY_COLORS[selected.severity], padding: '0.125rem 0.5rem', borderRadius: '3px',
                }}>
                  {selected.severity}
                </span>
              </div>

              {selected.description && (
                <p style={{ fontSize: '0.8rem', color: '#aaa', margin: '0 0 0.75rem' }}>{selected.description}</p>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', fontSize: '0.8rem' }}>
                <div>
                  <div style={{ color: '#888', fontSize: '0.7rem', marginBottom: '0.25rem' }}>ROOT CAUSE</div>
                  <div style={{ color: '#f97316' }}>{selected.root_cause || 'Unknown'}</div>
                </div>
                <div>
                  <div style={{ color: '#888', fontSize: '0.7rem', marginBottom: '0.25rem' }}>RESOLUTION</div>
                  <div style={{ color: '#22c55e' }}>{selected.resolution || 'None'}</div>
                </div>
              </div>

              {selected.resolution_steps?.length > 0 && (
                <div style={{ marginTop: '0.75rem' }}>
                  <div style={{ color: '#888', fontSize: '0.7rem', marginBottom: '0.25rem' }}>RESOLUTION STEPS</div>
                  <ol style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.8rem', color: '#ccc' }}>
                    {selected.resolution_steps.map((s, i) => <li key={i}>{s}</li>)}
                  </ol>
                </div>
              )}

              {selected.error_signatures?.length > 0 && (
                <div style={{ marginTop: '0.75rem' }}>
                  <div style={{ color: '#888', fontSize: '0.7rem', marginBottom: '0.25rem' }}>ERROR SIGNATURES</div>
                  <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap' }}>
                    {selected.error_signatures.map((s, i) => (
                      <span key={i} style={{
                        fontSize: '0.7rem', background: '#ef444415', color: '#f87171',
                        borderRadius: '3px', padding: '0.125rem 0.5rem', fontFamily: 'monospace',
                      }}>
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {selected.failure_dna && (
                <div style={{ marginTop: '0.75rem', padding: '0.5rem', background: '#8b5cf610', border: '1px solid #8b5cf630', borderRadius: '4px' }}>
                  <div style={{ color: '#8b5cf6', fontSize: '0.7rem', marginBottom: '0.25rem' }}>FAILURE DNA</div>
                  <div style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#a78bfa' }}>
                    {selected.failure_dna.fingerprint}
                  </div>
                  <div style={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#666', marginTop: '0.25rem' }}>
                    hash: {selected.failure_dna.hash}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Prevention tips */}
        <div className="card">
          <div className="card-header">Prevention Tips</div>
          {preventionTips.length === 0 ? (
            <div style={{ color: '#666', fontSize: '0.85rem' }}>No tips yet — record incidents with prevention tips</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {preventionTips.map((tip, i) => (
                <div key={i} style={{
                  padding: '0.6rem 0.75rem', background: '#22c55e10',
                  border: '1px solid #22c55e30', borderRadius: '6px',
                  fontSize: '0.8rem', color: '#4ade80',
                }}>
                  💡 {tip}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function authHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  const apiKey = localStorage.getItem('dataforge_api_key');
  if (apiKey) { headers['X-API-Key'] = apiKey; return headers; }
  const devToken = localStorage.getItem('dataforge_dev_token');
  if (devToken) headers['Authorization'] = `Bearer ${devToken}`;
  return headers;
}
