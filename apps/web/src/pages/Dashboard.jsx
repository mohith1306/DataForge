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
  const [incidents, setIncidents] = useState([]);
  const [stats, setStats] = useState({ total: 0, open: 0, resolved: 0, critical: 0 });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [creating, setCreating] = useState(false);
  const [connectors, setConnectors] = useState([]);
  const [checking, setChecking] = useState(null);
  const [checkResult, setCheckResult] = useState(null);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, [filter]);

  async function loadData() {
    try {
      const [statsData, listData, connData] = await Promise.all([
        fetchStats(),
        fetchIncidents(filter !== 'all' ? { status: filter } : {}),
        listConnectors(),
      ]);
      setStats(statsData);
      setIncidents(listData);
      setConnectors(connData);
    } catch (err) {
      console.error('[Dashboard] Failed to load data:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleRunCheck(connId) {
    setChecking(connId);
    setCheckResult(null);
    try {
      const res = await runConnectorCheck(connId);
      setCheckResult(res);
      loadData();
    } catch (err) {
      setCheckResult({ error: err.message });
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

  const totalIssues = checkResult
    ? (checkResult.failures?.length || 0) + (checkResult.stale?.length || 0) + (checkResult.quality_issues?.length || 0)
    : null;

  return (
    <div>
      {/* Connector Health */}
      {connectors.length > 0 && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Connected Databases</span>
            <button className="btn btn-primary" style={{ fontSize: '0.75rem', padding: '0.25rem 0.75rem' }} onClick={() => navigate('/')}>
              + Add Database
            </button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {connectors.map(conn => (
              <div key={conn.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem', background: '#1a1a1a', borderRadius: '6px' }}>
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                  <span style={{ fontSize: '1.25rem' }}>{DB_ICONS[conn.db_type] || '🗄️'}</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{conn.name}</div>
                    <div style={{ color: '#888', fontSize: '0.75rem' }}>
                      {conn.db_type} · {conn.discovered_tables.length} table{conn.discovered_tables.length !== 1 ? 's' : ''} · {conn.monitoring ? 'Monitoring' : 'Idle'}
                    </div>
                  </div>
                </div>
                <button
                  className="btn btn-primary"
                  style={{ fontSize: '0.75rem', padding: '0.25rem 0.75rem', background: '#f59e0b' }}
                  onClick={() => handleRunCheck(conn.id)}
                  disabled={checking === conn.id}
                >
                  {checking === conn.id ? 'Checking...' : 'Run Check'}
                </button>
              </div>
            ))}
          </div>

          {/* Check Results */}
          {checkResult && !checkResult.error && (
            <div style={{ marginTop: '1rem', padding: '1rem', background: totalIssues > 0 ? '#ef444410' : '#22c55e10', border: `1px solid ${totalIssues > 0 ? '#ef444440' : '#22c55e40'}`, borderRadius: '6px' }}>
              <div style={{ fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.5rem', color: totalIssues > 0 ? '#ef4444' : '#22c55e' }}>
                {totalIssues > 0 ? `${totalIssues} issue${totalIssues !== 1 ? 's' : ''} found` : 'All healthy — no issues found'}
              </div>
              <div style={{ display: 'flex', gap: '1.5rem', fontSize: '0.8rem', color: '#888' }}>
                {checkResult.failures?.length > 0 && <span style={{ color: '#ef4444' }}>🔴 {checkResult.failures.length} failures</span>}
                {checkResult.stale?.length > 0 && <span style={{ color: '#f59e0b' }}>🟡 {checkResult.stale.length} stale</span>}
                {checkResult.quality_issues?.length > 0 && <span style={{ color: '#a855f7' }}>🟣 {checkResult.quality_issues.length} quality</span>}
              </div>
              {/* Show failure details */}
              {checkResult.failures?.length > 0 && (
                <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
                  {checkResult.failures.slice(0, 5).map((f, i) => (
                    <div key={i} style={{ fontSize: '0.75rem', color: '#e5e5e5', padding: '0.375rem 0.5rem', background: '#0a0a0a', borderRadius: '4px' }}>
                      <span style={{ color: '#ef4444' }}>{f.pipeline_name || f.pipeline_id}</span>
                      <span style={{ color: '#666', margin: '0 0.5rem' }}>·</span>
                      <span style={{ color: '#888' }}>{f.error_message || 'No error message'}</span>
                    </div>
                  ))}
                </div>
              )}
              {checkResult.stale?.length > 0 && (
                <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
                  {checkResult.stale.slice(0, 5).map((s, i) => (
                    <div key={i} style={{ fontSize: '0.75rem', color: '#e5e5e5', padding: '0.375rem 0.5rem', background: '#0a0a0a', borderRadius: '4px' }}>
                      <span style={{ color: '#f59e0b' }}>{s.pipeline_name || s.pipeline_id}</span>
                      <span style={{ color: '#666', margin: '0 0.5rem' }}>·</span>
                      <span style={{ color: '#888' }}>last run: {s.last_run || 'unknown'}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {checkResult?.error && (
            <div className="alert alert-error" style={{ marginTop: '1rem' }}>{checkResult.error}</div>
          )}
        </div>
      )}

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">Total Incidents</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#3b82f6' }}>{stats.open}</div>
          <div className="stat-label">Open</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#22c55e' }}>{stats.resolved}</div>
          <div className="stat-label">Resolved</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#ef4444' }}>{stats.critical}</div>
          <div className="stat-label">Critical</div>
        </div>
      </div>

      {/* Incidents */}
      <div className="card" style={{ marginTop: '1.5rem' }}>
        <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Incidents</span>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <div className="filter-group">
              {['all', 'created', 'investigating', 'resolved'].map(s => (
                <button
                  key={s}
                  className={`filter-btn ${filter === s ? 'active' : ''}`}
                  onClick={() => setFilter(s)}
                >
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </button>
              ))}
            </div>
            <button
              className="btn btn-primary"
              style={{ padding: '0.375rem 0.75rem', fontSize: '0.8rem' }}
              onClick={handleCreateIncident}
              disabled={creating}
            >
              {creating ? 'Creating...' : '+ New Incident'}
            </button>
          </div>
        </div>

        {loading ? (
          <div className="loading">Loading incidents...</div>
        ) : incidents.length === 0 ? (
          <div className="empty-state">
            <p>No incidents yet</p>
            <p style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.5rem' }}>
              Run a check on your database to detect issues
            </p>
          </div>
        ) : (
          <div className="incident-list">
            {incidents.map(inc => (
              <div key={inc.id} className="incident-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Link
                  to={`/incidents/${inc.id}`}
                  style={{ flex: 1, textDecoration: 'none', color: 'inherit' }}
                >
                  <div className="incident-main">
                    <span
                      className="severity-dot"
                      style={{ background: SEVERITY_COLORS[inc.severity] || '#666' }}
                    />
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
                  <span
                    className="badge"
                    style={{
                      background: `${STATUS_COLORS[inc.status] || '#666'}20`,
                      color: STATUS_COLORS[inc.status] || '#666',
                    }}
                  >
                    {inc.status}
                  </span>
                  {inc.status === 'created' && (
                    <button
                      className="btn btn-primary"
                      style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem' }}
                      onClick={(e) => {
                        e.preventDefault();
                        handleStartInvestigation(inc.id);
                      }}
                    >
                      Start
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
