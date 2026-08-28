import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { fetchIncidents, fetchStats, startInvestigation, createIncident } from '../api';

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

export default function Dashboard() {
  const [incidents, setIncidents] = useState([]);
  const [stats, setStats] = useState({ total: 0, open: 0, resolved: 0, critical: 0 });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    console.log('[Dashboard] Mounted');
    loadData();
    const interval = setInterval(() => {
      console.log('[Dashboard] Auto-refresh polling');
      loadData();
    }, 10000);
    return () => {
      console.log('[Dashboard] Unmounted');
      clearInterval(interval);
    };
  }, [filter]);

  async function loadData() {
    try {
      console.log('[Dashboard] Loading data, filter:', filter);
      const [statsData, listData] = await Promise.all([
        fetchStats(),
        fetchIncidents(filter !== 'all' ? { status: filter } : {}),
      ]);
      setStats(statsData);
      setIncidents(listData);
      console.log('[Dashboard] Data loaded:', listData.length, 'incidents');
    } catch (err) {
      console.error('[Dashboard] Failed to load data:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateIncident() {
    console.log('[Dashboard] Creating incident...');
    setCreating(true);
    try {
      const result = await createIncident({
        title: 'APAC revenue dropped 42%',
        severity: 'critical',
        incident_type: 'volume_drop',
        description: 'APAC region showing 42% revenue drop in last 5 days. Pipeline PL-001 failed.',
      });
      console.log('[Dashboard] Incident created:', result.id);
      loadData();
    } catch (err) {
      console.error('[Dashboard] Failed to create incident:', err);
    } finally {
      setCreating(false);
    }
  }

  async function handleStartInvestigation(incidentId) {
    console.log('[Dashboard] Starting investigation for:', incidentId);
    try {
      await startInvestigation(incidentId);
      console.log('[Dashboard] Investigation started, refreshing...');
      loadData();
    } catch (err) {
      console.error('[Dashboard] Failed to start investigation:', err);
    }
  }

  return (
    <div>
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

      <div className="card" style={{ marginTop: '1.5rem' }}>
        <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Incidents</span>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <div className="filter-group">
              {['all', 'created', 'investigating', 'resolved'].map(s => (
                <button
                  key={s}
                  className={`filter-btn ${filter === s ? 'active' : ''}`}
                  onClick={() => {
                    console.log('[Dashboard] Filter changed to:', s);
                    setFilter(s);
                  }}
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
            <p>No incidents found</p>
            <p style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.5rem' }}>
              Click "+ New Incident" to create one
            </p>
          </div>
        ) : (
          <div className="incident-list">
            {incidents.map(inc => (
              <div key={inc.id} className="incident-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Link
                  to={`/incidents/${inc.id}`}
                  style={{ flex: 1, textDecoration: 'none', color: 'inherit' }}
                  onClick={() => console.log('[Dashboard] Navigating to incident:', inc.id)}
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
