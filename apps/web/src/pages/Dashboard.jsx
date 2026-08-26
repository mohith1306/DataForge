import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { fetchIncidents, fetchStats } from '../api';

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

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, [filter]);

  async function loadData() {
    try {
      // Fetch stats separately (unfiltered) and list with current filter
      const [statsData, listData] = await Promise.all([
        fetchStats(),
        fetchIncidents(filter !== 'all' ? { status: filter } : {}),
      ]);
      setStats(statsData);
      setIncidents(listData);
    } catch (err) {
      console.error('Failed to load incidents:', err);
    } finally {
      setLoading(false);
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
        </div>

        {loading ? (
          <div className="loading">Loading incidents...</div>
        ) : incidents.length === 0 ? (
          <div className="empty-state">
            <p>No incidents found</p>
            <p style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.5rem' }}>
              Create one from the Chaos Lab or API
            </p>
          </div>
        ) : (
          <div className="incident-list">
            {incidents.map(inc => (
              <Link to={`/incidents/${inc.id}`} key={inc.id} className="incident-row">
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
                <span
                  className="badge"
                  style={{
                    background: `${STATUS_COLORS[inc.status] || '#666'}20`,
                    color: STATUS_COLORS[inc.status] || '#666',
                  }}
                >
                  {inc.status}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
