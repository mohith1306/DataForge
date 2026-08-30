import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { fetchIncidents, fetchStats, startInvestigation, createIncident, listConnectors, runConnectorCheck } from '../api';

const SEVERITY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
};

const STATUS_COLORS = {
  created: '#3b82f6',
  investigating: '#a855f7',
  diagnosed: '#f59e0b',
  planning: '#f97316',
  awaiting_approval: '#ef4444',
  executing: '#06b6d4',
  verifying: '#8b5cf6',
  resolved: '#22c55e',
  failed: '#ef4444',
};

const DB_ICONS = { clickhouse: '🏗️', postgres: '🐘', mysql: '🐬', snowflake: '❄️', databricks: '🧱' };

export default function Dashboard() {
  const navigate = useNavigate();
  const [connectors, setConnectors] = useState([]);
  const [allIncidents, setAllIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [checkResults, setCheckResults] = useState({});  // connId → result
  const [checking, setChecking] = useState(null);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, []);

  async function loadData() {
    try {
      const [connData, incData] = await Promise.all([
        listConnectors(),
        fetchIncidents(),
      ]);
      setConnectors(connData);
      setAllIncidents(incData);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleRunCheck(connId) {
    setChecking(connId);
    try {
      const res = await runConnectorCheck(connId);
      setCheckResults(prev => ({ ...prev, [connId]: res }));
      loadData();
    } catch (err) {
      setCheckResults(prev => ({ ...prev, [connId]: { error: err.message } }));
    } finally {
      setChecking(null);
    }
  }

  async function handleCreateIncident() {
    setCreating(true);
    try {
      await createIncident({
        title: 'APAC revenue dropped 42%',
        severity: 'critical',
        incident_type: 'volume_drop',
        description: 'APAC region showing 42% revenue drop in last 5 days.',
      });
      loadData();
    } catch (err) {
      console.error(err);
    } finally {
      setCreating(false);
    }
  }

  async function handleStartInvestigation(incidentId) {
    try {
      await startInvestigation(incidentId);
      loadData();
    } catch (err) {
      console.error(err);
    }
  }

  if (loading) return <div className="loading">Loading dashboard...</div>;

  return (
    <div>
      {/* Global Stats */}
      {connectors.length > 0 && (
        <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
          <div className="stat-card" onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>
            <div className="stat-value">{connectors.length}</div>
            <div className="stat-label">Databases</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: '#22c55e' }}>
              {connectors.filter(c => c.monitoring).length}
            </div>
            <div className="stat-label">Monitoring</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{allIncidents.length}</div>
            <div className="stat-label">Total Incidents</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: '#ef4444' }}>
              {allIncidents.filter(i => i.status === 'created').length}
            </div>
            <div className="stat-label">Open</div>
          </div>
        </div>
      )}

      {/* Per-Database Sections */}
      {connectors.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <p>No databases connected</p>
            <button className="btn btn-primary" style={{ marginTop: '1rem' }} onClick={() => navigate('/')}>
              Connect a Database
            </button>
          </div>
        </div>
      ) : (
        connectors.map(conn => {
          const result = checkResults[conn.id];
          const totalIssues = result
            ? (result.failures?.length || 0) + (result.stale?.length || 0) + (result.quality_issues?.length || 0)
            : null;
          const dbIncidents = allIncidents.filter(inc => inc.connector_id === conn.id);

          return (
            <div key={conn.id} className="card" style={{ marginBottom: '1.5rem' }}>
              {/* Database Header */}
              <div
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', padding: '0.5rem 0' }}
                onClick={() => navigate(`/databases/${conn.id}`)}
              >
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                  <span style={{ fontSize: '1.5rem' }}>{DB_ICONS[conn.db_type] || '🗄️'}</span>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '1rem' }}>{conn.name}</div>
                    <div style={{ color: '#888', fontSize: '0.8rem' }}>
                      {conn.db_type} · {conn.discovered_tables.length} table{conn.discovered_tables.length !== 1 ? 's' : ''} · {conn.monitoring ? '● Monitoring' : '○ Idle'}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    className="btn btn-primary"
                    style={{ fontSize: '0.75rem', padding: '0.375rem 0.75rem', background: '#8b5cf6' }}
                    onClick={(e) => { e.stopPropagation(); handleRunCheck(conn.id); }}
                    disabled={checking === conn.id}
                  >
                    {checking === conn.id ? 'Checking...' : 'Run Check'}
                  </button>
                  <button
                    className="btn btn-primary"
                    style={{ fontSize: '0.75rem', padding: '0.375rem 0.75rem' }}
                    onClick={(e) => { e.stopPropagation(); navigate(`/databases/${conn.id}`); }}
                  >
                    Details
                  </button>
                </div>
              </div>

              {/* Check Results */}
              {result && !result.error && (
                <div style={{ marginTop: '0.75rem', padding: '0.75rem', background: totalIssues > 0 ? '#ef444410' : '#22c55e10', border: `1px solid ${totalIssues > 0 ? '#ef444440' : '#22c55e40'}`, borderRadius: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.875rem', color: totalIssues > 0 ? '#ef4444' : '#22c55e' }}>
                      {totalIssues > 0 ? `${totalIssues} issue${totalIssues !== 1 ? 's' : ''} detected` : 'All healthy'}
                    </span>
                    <div style={{ display: 'flex', gap: '1rem', fontSize: '0.75rem' }}>
                      {result.failures?.length > 0 && <span style={{ color: '#ef4444' }}>🔴 {result.failures.length} failures</span>}
                      {result.stale?.length > 0 && <span style={{ color: '#f59e0b' }}>🟡 {result.stale.length} stale</span>}
                      {result.quality_issues?.length > 0 && <span style={{ color: '#a855f7' }}>🟣 {result.quality_issues.length} quality</span>}
                    </div>
                  </div>

                  {/* Failure Details */}
                  {result.failures?.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                      {result.failures.slice(0, 3).map((f, i) => (
                        <div key={i} style={{ fontSize: '0.75rem', padding: '0.375rem 0.5rem', background: '#0a0a0a', borderRadius: '4px' }}>
                          <span style={{ color: '#ef4444', fontWeight: 500 }}>{f.pipeline_name || f.pipeline_id}</span>
                          <span style={{ color: '#555', margin: '0 0.375rem' }}>·</span>
                          <span style={{ color: '#888' }}>{f.error_message || 'No error'}</span>
                        </div>
                      ))}
                      {result.failures.length > 3 && (
                        <div style={{ fontSize: '0.7rem', color: '#666' }}>+{result.failures.length - 3} more</div>
                      )}
                    </div>
                  )}

                  {/* Stale Details */}
                  {result.stale?.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', marginTop: result.failures?.length ? '0.5rem' : 0 }}>
                      {result.stale.slice(0, 3).map((s, i) => (
                        <div key={i} style={{ fontSize: '0.75rem', padding: '0.375rem 0.5rem', background: '#0a0a0a', borderRadius: '4px' }}>
                          <span style={{ color: '#f59e0b', fontWeight: 500 }}>{s.pipeline_name || s.pipeline_id}</span>
                          <span style={{ color: '#555', margin: '0 0.375rem' }}>·</span>
                          <span style={{ color: '#888' }}>last run: {s.last_run || 'unknown'}</span>
                        </div>
                      ))}
                      {result.stale.length > 3 && (
                        <div style={{ fontSize: '0.7rem', color: '#666' }}>+{result.stale.length - 3} more</div>
                      )}
                    </div>
                  )}
                </div>
              )}
              {result?.error && (
                <div style={{ marginTop: '0.75rem', padding: '0.5rem 0.75rem', background: '#ef444410', border: '1px solid #ef444440', borderRadius: '6px', fontSize: '0.8rem', color: '#ef4444' }}>
                  {result.error}
                </div>
              )}

              {/* Discovered Tables Preview */}
              {conn.discovered_tables.length > 0 && (
                <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.375rem', flexWrap: 'wrap' }}>
                  {conn.discovered_tables.map((t, i) => (
                    <span key={i} style={{ fontSize: '0.7rem', background: '#1a1a1a', border: '1px solid #333', borderRadius: '3px', padding: '0.125rem 0.5rem', color: '#888' }}>
                      {t.table} <span style={{ color: '#555' }}>({t.row_count || 0} rows)</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })
      )}

      {/* All Incidents */}
      {allIncidents.length > 0 && (
        <div className="card" style={{ marginTop: '1.5rem' }}>
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>All Incidents</span>
            <button
              className="btn btn-primary"
              style={{ padding: '0.375rem 0.75rem', fontSize: '0.8rem' }}
              onClick={handleCreateIncident}
              disabled={creating}
            >
              {creating ? 'Creating...' : '+ New Incident'}
            </button>
          </div>
          <div className="incident-list">
            {allIncidents.slice(0, 10).map(inc => (
              <div key={inc.id} className="incident-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Link
                  to={`/incidents/${inc.id}`}
                  style={{ flex: 1, textDecoration: 'none', color: 'inherit' }}
                >
                  <div className="incident-main">
                    <span className="severity-dot" style={{ background: SEVERITY_COLORS[inc.severity] || '#666' }} />
                    <div>
                      <div className="incident-title">{inc.title}</div>
                      <div className="incident-meta">
                        {inc.incident_type && <span className="incident-type">{inc.incident_type}</span>}
                        <span>{new Date(inc.created_at).toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                </Link>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span className="badge" style={{ background: `${STATUS_COLORS[inc.status] || '#666'}20`, color: STATUS_COLORS[inc.status] || '#666' }}>
                    {inc.status}
                  </span>
                  {inc.status === 'created' && (
                    <button
                      className="btn btn-primary"
                      style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem' }}
                      onClick={(e) => { e.preventDefault(); handleStartInvestigation(inc.id); }}
                    >
                      Start
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
