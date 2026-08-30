import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { getConnector, runConnectorCheck, testConnector, deleteConnector, fetchIncidents } from '../api';

const DB_ICONS = { clickhouse: '🏗️', postgres: '🐘', mysql: '🐬', snowflake: '❄️', databricks: '🧱' };

export default function DatabaseDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [connector, setConnector] = useState(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [tab, setTab] = useState('overview');

  useEffect(() => { load(); }, [id]);

  async function load() {
    try {
      const [conn, inc] = await Promise.all([
        getConnector(id),
        fetchIncidents(),
      ]);
      setConnector(conn);
      setIncidents(inc);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleRunCheck() {
    setChecking(true);
    setCheckResult(null);
    try {
      const res = await runConnectorCheck(id);
      setCheckResult(res);
      load();
    } catch (err) {
      setCheckResult({ error: err.message });
    } finally {
      setChecking(false);
    }
  }

  async function handleTest() {
    try {
      const res = await testConnector(id);
      alert(`Connected! ${res.tables} tables found.`);
    } catch (err) {
      alert('Test failed: ' + err.message);
    }
  }

  async function handleDelete() {
    if (!confirm('Delete this connector?')) return;
    await deleteConnector(id);
    navigate('/');
  }

  if (loading) return <div className="loading">Loading database...</div>;
  if (!connector) return <div className="error">Database not found</div>;

  const totalIssues = checkResult
    ? (checkResult.failures?.length || 0) + (checkResult.stale?.length || 0) + (checkResult.quality_issues?.length || 0)
    : null;

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <span style={{ fontSize: '2rem' }}>{DB_ICONS[connector.db_type] || '🗄️'}</span>
          <div>
            <h1 style={{ fontSize: '1.25rem', fontWeight: 700 }}>{connector.name}</h1>
            <div style={{ color: '#888', fontSize: '0.8rem' }}>
              {connector.db_type} · {connector.host}:{connector.port}/{connector.database}
              {connector.monitoring && <span style={{ color: '#22c55e', marginLeft: '0.75rem' }}>● Monitoring</span>}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-primary" style={{ fontSize: '0.8rem' }} onClick={() => navigate('/')}>Back</button>
          <button className="btn btn-primary" style={{ fontSize: '0.8rem', background: '#f59e0b' }} onClick={handleTest}>Test</button>
          <button className="btn btn-primary" style={{ fontSize: '0.8rem', background: '#8b5cf6' }} onClick={handleRunCheck} disabled={checking}>
            {checking ? 'Checking...' : 'Run Check'}
          </button>
          <button className="btn btn-danger" style={{ fontSize: '0.8rem' }} onClick={handleDelete}>Delete</button>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        {['overview', 'tables', 'incidents'].map(t => (
          <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {tab === 'overview' && (
        <div>
          {/* Check Results */}
          {checkResult && !checkResult.error && (
            <div className="card" style={{ marginBottom: '1.5rem' }}>
              <div className="card-header">Latest Check Result</div>
              <div style={{ padding: '1rem', background: totalIssues > 0 ? '#ef444410' : '#22c55e10', border: `1px solid ${totalIssues > 0 ? '#ef444440' : '#22c55e40'}`, borderRadius: '6px' }}>
                <div style={{ fontWeight: 600, fontSize: '1rem', marginBottom: '0.5rem', color: totalIssues > 0 ? '#ef4444' : '#22c55e' }}>
                  {totalIssues > 0 ? `${totalIssues} issue${totalIssues !== 1 ? 's' : ''} detected` : 'All healthy'}
                </div>
                <div style={{ display: 'flex', gap: '2rem', fontSize: '0.85rem' }}>
                  <div>
                    <span style={{ color: '#ef4444', fontSize: '1.5rem', fontWeight: 700 }}>{checkResult.failures?.length || 0}</span>
                    <span style={{ color: '#888', marginLeft: '0.5rem' }}>Failures</span>
                  </div>
                  <div>
                    <span style={{ color: '#f59e0b', fontSize: '1.5rem', fontWeight: 700 }}>{checkResult.stale?.length || 0}</span>
                    <span style={{ color: '#888', marginLeft: '0.5rem' }}>Stale</span>
                  </div>
                  <div>
                    <span style={{ color: '#a855f7', fontSize: '1.5rem', fontWeight: 700 }}>{checkResult.quality_issues?.length || 0}</span>
                    <span style={{ color: '#888', marginLeft: '0.5rem' }}>Quality</span>
                  </div>
                </div>
              </div>

              {/* Failures */}
              {checkResult.failures?.length > 0 && (
                <div style={{ marginTop: '1rem' }}>
                  <div style={{ fontSize: '0.8rem', color: '#ef4444', fontWeight: 600, marginBottom: '0.5rem' }}>Pipeline Failures</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
                    {checkResult.failures.map((f, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: '#1a1a1a', borderRadius: '4px', fontSize: '0.8rem' }}>
                        <div>
                          <span style={{ color: '#ef4444', fontWeight: 500 }}>{f.pipeline_name || f.pipeline_id}</span>
                          <span style={{ color: '#666', margin: '0 0.5rem' }}>·</span>
                          <span style={{ color: '#888' }}>{f.error_message || 'No error message'}</span>
                        </div>
                        <span style={{ color: '#666' }}>{f.started_at || ''}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Stale */}
              {checkResult.stale?.length > 0 && (
                <div style={{ marginTop: '1rem' }}>
                  <div style={{ fontSize: '0.8rem', color: '#f59e0b', fontWeight: 600, marginBottom: '0.5rem' }}>Stale Pipelines</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
                    {checkResult.stale.map((s, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: '#1a1a1a', borderRadius: '4px', fontSize: '0.8rem' }}>
                        <span style={{ color: '#f59e0b', fontWeight: 500 }}>{s.pipeline_name || s.pipeline_id}</span>
                        <span style={{ color: '#666' }}>last run: {s.last_run || 'unknown'}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Quality */}
              {checkResult.quality_issues?.length > 0 && (
                <div style={{ marginTop: '1rem' }}>
                  <div style={{ fontSize: '0.8rem', color: '#a855f7', fontWeight: 600, marginBottom: '0.5rem' }}>Data Quality Issues</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
                    {checkResult.quality_issues.map((q, i) => (
                      <div key={i} style={{ padding: '0.5rem 0.75rem', background: '#1a1a1a', borderRadius: '4px', fontSize: '0.8rem' }}>
                        <span style={{ color: '#a855f7' }}>{q.table || '?'}.{q.column || '?'}</span>
                        <span style={{ color: '#666', margin: '0 0.5rem' }}>·</span>
                        <span style={{ color: '#888' }}>null rate: {((q.nulls || 0) / (q.total || 1) * 100).toFixed(1)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          {checkResult?.error && (
            <div className="alert alert-error" style={{ marginBottom: '1rem' }}>{checkResult.error}</div>
          )}

          {/* Quick Stats */}
          <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
            <div className="stat-card">
              <div className="stat-value">{connector.discovered_tables.length}</div>
              <div className="stat-label">Discovered Tables</div>
            </div>
            <div className="stat-card">
              <div className="stat-value" style={{ color: connector.monitoring ? '#22c55e' : '#888' }}>
                {connector.monitoring ? 'Active' : 'Idle'}
              </div>
              <div className="stat-label">Monitoring Status</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{connector.poll_interval}s</div>
              <div className="stat-label">Check Interval</div>
            </div>
          </div>
        </div>
      )}

      {/* Tables Tab */}
      {tab === 'tables' && (
        <div className="card">
          <div className="card-header">Discovered Tables</div>
          {connector.discovered_tables.length === 0 ? (
            <div className="empty-state">
              <p>No tables discovered yet</p>
              <p style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.5rem' }}>
                Run a check to auto-discover pipeline tables
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {connector.discovered_tables.map((t, i) => (
                <div key={i} style={{ padding: '1rem', background: '#1a1a1a', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>{t.table}</div>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <span className={`badge ${t.type === 'pipeline' ? 'badge-created' : 'badge-resolved'}`}>
                        {t.type}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: '#666' }}>
                        {(t.row_count || 0).toLocaleString()} rows
                      </span>
                      <span style={{ fontSize: '0.75rem', color: '#444' }}>
                        confidence: {(t.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                  {t.columns && Object.keys(t.columns).length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
                      {Object.entries(t.columns).map(([logical, actual]) => (
                        <span key={logical} style={{ fontSize: '0.7rem', background: '#0a0a0a', border: '1px solid #333', borderRadius: '3px', padding: '0.125rem 0.5rem' }}>
                          <span style={{ color: '#888' }}>{logical}</span>
                          <span style={{ color: '#555', margin: '0 0.25rem' }}>→</span>
                          <span style={{ color: '#e5e5e5' }}>{actual}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Incidents Tab */}
      {tab === 'incidents' && (
        <div className="card">
          <div className="card-header">Incidents</div>
          {incidents.length === 0 ? (
            <div className="empty-state">
              <p>No incidents yet</p>
              <p style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.5rem' }}>
                Run a check to detect issues and create incidents
              </p>
            </div>
          ) : (
            <div className="incident-list">
              {incidents.map(inc => (
                <Link key={inc.id} to={`/incidents/${inc.id}`} className="incident-row" style={{ textDecoration: 'none', color: 'inherit' }}>
                  <div className="incident-main">
                    <span className="severity-dot" style={{ background: inc.severity === 'critical' ? '#ef4444' : inc.severity === 'high' ? '#f97316' : inc.severity === 'medium' ? '#eab308' : '#22c55e' }} />
                    <div>
                      <div className="incident-title">{inc.title}</div>
                      <div className="incident-meta">
                        <span className="incident-type">{inc.incident_type}</span>
                        <span>{new Date(inc.created_at).toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                  <span className="badge" style={{ background: '#3b82f620', color: '#3b82f6' }}>{inc.status}</span>
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
