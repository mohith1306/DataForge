import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  listConnectors,
  addConnector,
  deleteConnector,
  testConnector,
  runConnectorCheck,
} from '../api';

const DB_TYPES = [
  { id: 'clickhouse', label: 'ClickHouse', icon: '🏗️', defaultPort: 8123, defaultSchema: '' },
  { id: 'postgres', label: 'PostgreSQL', icon: '🐘', defaultPort: 5432, defaultSchema: 'public' },
  { id: 'mysql', label: 'MySQL', icon: '🐬', defaultPort: 3306, defaultSchema: '' },
];

export default function Connectors() {
  const navigate = useNavigate();
  const [connectors, setConnectors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [selectedDb, setSelectedDb] = useState('clickhouse');
  const [form, setForm] = useState({
    name: '',
    host: 'localhost',
    port: 8123,
    database: '',
    username: 'default',
    password: '',
    poll_interval: 30,
  });
  const [connecting, setConnecting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    loadConnectors();
  }, []);

  async function loadConnectors() {
    try {
      const data = await listConnectors();
      setConnectors(data);
      if (data.length > 0 && !showForm) {
        // Already have connectors, show the list
      }
    } catch (err) {
      console.error('Failed to load connectors:', err);
    } finally {
      setLoading(false);
    }
  }

  function handleDbSelect(dbType) {
    const db = DB_TYPES.find(d => d.id === dbType);
    setSelectedDb(dbType);
    setForm(f => ({
      ...f,
      name: '',
      port: db.defaultPort,
      database: '',
      username: dbType === 'clickhouse' ? 'default' : '',
      password: '',
    }));
  }

  async function handleConnect(e) {
    e.preventDefault();
    setConnecting(true);
    setError('');
    setResult(null);

    try {
      const res = await addConnector({
        ...form,
        db_type: selectedDb,
        schema: DB_TYPES.find(d => d.id === selectedDb)?.defaultSchema || '',
      });
      setResult(res);
      setShowForm(false);
      loadConnectors();
    } catch (err) {
      setError(err.message || 'Connection failed');
    } finally {
      setConnecting(false);
    }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this connector and stop monitoring?')) return;
    try {
      await deleteConnector(id);
      loadConnectors();
    } catch (err) {
      console.error('Delete failed:', err);
    }
  }

  async function handleTest(id) {
    try {
      const res = await testConnector(id);
      alert(`Connected! Found ${res.tables} tables.`);
    } catch (err) {
      alert('Connection test failed: ' + err.message);
    }
  }

  async function handleCheckNow(id) {
    try {
      const res = await runConnectorCheck(id);
      const issues = res.failures.length + res.stale.length + res.quality_issues.length;
      if (issues > 0) {
        alert(`Found ${res.failures.length} failures, ${res.stale.length} stale pipelines, ${res.quality_issues.length} quality issues.`);
      } else {
        alert('No issues found. All healthy!');
      }
    } catch (err) {
      alert('Check failed: ' + err.message);
    }
  }

  if (loading) return <div className="loading">Loading connectors...</div>;

  // Show connectors list if we have any and not in form mode
  if (connectors.length > 0 && !showForm) {
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Database Connectors</h2>
            <p style={{ color: '#888', fontSize: '0.8rem', marginTop: '0.25rem' }}>
              {connectors.length} connector{connectors.length > 1 ? 's' : ''} active — monitoring your databases
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button className="btn btn-primary" onClick={() => navigate('/')}>
              View Dashboard
            </button>
            <button className="btn btn-primary" style={{ background: '#22c55e' }} onClick={() => setShowForm(true)}>
              + Add Database
            </button>
          </div>
        </div>

        {result && (
          <div className="alert alert-success" style={{ marginBottom: '1rem' }}>
            {result.message}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {connectors.map(conn => (
            <div key={conn.id} className="card" style={{ padding: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                  <div style={{ fontSize: '1.5rem' }}>
                    {DB_TYPES.find(d => d.id === conn.db_type)?.icon || '🗄️'}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>{conn.name}</div>
                    <div style={{ color: '#888', fontSize: '0.8rem', marginTop: '0.25rem' }}>
                      {conn.db_type} · {conn.host}:{conn.port}/{conn.database}
                    </div>
                    <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
                      <span className={`badge ${conn.monitoring ? 'badge-resolved' : 'badge-created'}`}>
                        {conn.monitoring ? 'Monitoring' : 'Idle'}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: '#666' }}>
                        {conn.discovered_tables.length} table{conn.discovered_tables.length !== 1 ? 's' : ''} discovered
                      </span>
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button className="btn btn-primary" style={{ fontSize: '0.75rem', padding: '0.25rem 0.75rem' }} onClick={() => handleTest(conn.id)}>
                    Test
                  </button>
                  <button className="btn btn-primary" style={{ fontSize: '0.75rem', padding: '0.25rem 0.75rem', background: '#f59e0b' }} onClick={() => handleCheckNow(conn.id)}>
                    Check Now
                  </button>
                  <button className="btn btn-danger" style={{ fontSize: '0.75rem', padding: '0.25rem 0.75rem' }} onClick={() => handleDelete(conn.id)}>
                    Delete
                  </button>
                </div>
              </div>

              {conn.discovered_tables.length > 0 && (
                <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid #222' }}>
                  <div style={{ fontSize: '0.75rem', color: '#888', marginBottom: '0.5rem' }}>Discovered Tables:</div>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {conn.discovered_tables.map((t, i) => (
                      <div key={i} style={{ background: '#1a1a1a', border: '1px solid #333', borderRadius: '4px', padding: '0.375rem 0.75rem', fontSize: '0.75rem' }}>
                        <span style={{ color: '#e5e5e5' }}>{t.table}</span>
                        <span style={{ color: '#666', marginLeft: '0.5rem' }}>{t.type}</span>
                        <span style={{ color: '#444', marginLeft: '0.5rem' }}>{t.row_count} rows</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Setup form
  return (
    <div style={{ maxWidth: '640px', margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '0.5rem' }}>
          Connect Your Database
        </h1>
        <p style={{ color: '#888', fontSize: '0.9rem' }}>
          DataForge will auto-discover your pipelines and monitor for failures, stale runs, and quality issues.
        </p>
      </div>

      {/* Database Type Selection */}
      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem' }}>
        {DB_TYPES.map(db => (
          <button
            key={db.id}
            onClick={() => handleDbSelect(db.id)}
            style={{
              flex: 1,
              padding: '1rem',
              background: selectedDb === db.id ? '#1a1a1a' : '#141414',
              border: `1px solid ${selectedDb === db.id ? '#3b82f6' : '#333'}`,
              borderRadius: '8px',
              color: '#e5e5e5',
              cursor: 'pointer',
              textAlign: 'center',
              transition: 'all 0.2s',
            }}
          >
            <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>{db.icon}</div>
            <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{db.label}</div>
          </button>
        ))}
      </div>

      {/* Connection Form */}
      <form onSubmit={handleConnect} className="card" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', color: '#888', marginBottom: '0.25rem' }}>
              Connection Name
            </label>
            <input
              type="text"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="My Production DB"
              required
              style={{ width: '100%', padding: '0.5rem 0.75rem', background: '#0a0a0a', border: '1px solid #333', borderRadius: '4px', color: '#e5e5e5', fontSize: '0.875rem' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', color: '#888', marginBottom: '0.25rem' }}>
              Database Name
            </label>
            <input
              type="text"
              value={form.database}
              onChange={e => setForm(f => ({ ...f, database: e.target.value }))}
              placeholder="dataforge"
              required
              style={{ width: '100%', padding: '0.5rem 0.75rem', background: '#0a0a0a', border: '1px solid #333', borderRadius: '4px', color: '#e5e5e5', fontSize: '0.875rem' }}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', color: '#888', marginBottom: '0.25rem' }}>
              Host
            </label>
            <input
              type="text"
              value={form.host}
              onChange={e => setForm(f => ({ ...f, host: e.target.value }))}
              placeholder="localhost"
              required
              style={{ width: '100%', padding: '0.5rem 0.75rem', background: '#0a0a0a', border: '1px solid #333', borderRadius: '4px', color: '#e5e5e5', fontSize: '0.875rem' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', color: '#888', marginBottom: '0.25rem' }}>
              Port
            </label>
            <input
              type="number"
              value={form.port}
              onChange={e => setForm(f => ({ ...f, port: parseInt(e.target.value) || 0 }))}
              required
              style={{ width: '100%', padding: '0.5rem 0.75rem', background: '#0a0a0a', border: '1px solid #333', borderRadius: '4px', color: '#e5e5e5', fontSize: '0.875rem' }}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', color: '#888', marginBottom: '0.25rem' }}>
              Username
            </label>
            <input
              type="text"
              value={form.username}
              onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
              style={{ width: '100%', padding: '0.5rem 0.75rem', background: '#0a0a0a', border: '1px solid #333', borderRadius: '4px', color: '#e5e5e5', fontSize: '0.875rem' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', color: '#888', marginBottom: '0.25rem' }}>
              Password
            </label>
            <input
              type="password"
              value={form.password}
              onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
              style={{ width: '100%', padding: '0.5rem 0.75rem', background: '#0a0a0a', border: '1px solid #333', borderRadius: '4px', color: '#e5e5e5', fontSize: '0.875rem' }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', color: '#888', marginBottom: '0.25rem' }}>
              Check Interval (sec)
            </label>
            <input
              type="number"
              value={form.poll_interval}
              onChange={e => setForm(f => ({ ...f, poll_interval: parseInt(e.target.value) || 30 }))}
              min="5"
              style={{ width: '100%', padding: '0.5rem 0.75rem', background: '#0a0a0a', border: '1px solid #333', borderRadius: '4px', color: '#e5e5e5', fontSize: '0.875rem' }}
            />
          </div>
        </div>

        {error && (
          <div className="alert alert-error" style={{ marginBottom: '1rem' }}>{error}</div>
        )}

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={connecting}
            style={{ flex: 1, padding: '0.75rem', fontSize: '0.95rem' }}
          >
            {connecting ? 'Connecting & Discovering...' : 'Connect & Start Monitoring'}
          </button>
          {connectors.length > 0 && (
            <button
              type="button"
              className="btn btn-primary"
              style={{ background: '#333', padding: '0.75rem 1.5rem' }}
              onClick={() => setShowForm(false)}
            >
              Cancel
            </button>
          )}
        </div>

        <p style={{ color: '#666', fontSize: '0.75rem', marginTop: '0.75rem', textAlign: 'center' }}>
          DataForge will auto-discover pipeline tables and start monitoring for failures, stale runs, and data quality issues.
        </p>
      </form>
    </div>
  );
}
