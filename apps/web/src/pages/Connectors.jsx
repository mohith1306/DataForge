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
  {
    id: 'clickhouse', label: 'ClickHouse', icon: '🏗️',
    fields: ['name', 'host', 'port', 'database', 'username', 'password', 'poll_interval'],
    defaults: { host: 'localhost', port: 8123, username: 'default' },
  },
  {
    id: 'postgres', label: 'PostgreSQL', icon: '🐘',
    fields: ['name', 'host', 'port', 'database', 'username', 'password', 'schema', 'poll_interval'],
    defaults: { host: 'localhost', port: 5432, schema: 'public' },
  },
  {
    id: 'mysql', label: 'MySQL', icon: '🐬',
    fields: ['name', 'host', 'port', 'database', 'username', 'password', 'poll_interval'],
    defaults: { host: 'localhost', port: 3306 },
  },
  {
    id: 'snowflake', label: 'Snowflake', icon: '❄️',
    fields: ['name', 'account', 'database', 'schema', 'username', 'password', 'warehouse', 'role', 'poll_interval'],
    defaults: { schema: 'PUBLIC', warehouse: 'COMPUTE_WH', role: 'SYSADMIN' },
  },
  {
    id: 'databricks', label: 'Databricks', icon: '🧱',
    fields: ['name', 'workspace_url', 'http_path', 'catalog', 'token', 'poll_interval'],
    defaults: {},
  },
];

const FIELD_DEFS = {
  name:           { label: 'Connection Name', placeholder: 'My Production DB', type: 'text', required: true, half: true },
  host:           { label: 'Host', placeholder: 'localhost', type: 'text', required: true, flex: 2 },
  port:           { label: 'Port', type: 'number', required: true, flex: 1 },
  database:       { label: 'Database', placeholder: 'my_db', type: 'text', required: true, half: true },
  schema:         { label: 'Schema', placeholder: 'public', type: 'text', half: true },
  username:       { label: 'Username', type: 'text', third: true },
  password:       { label: 'Password', type: 'password', third: true },
  poll_interval:  { label: 'Check Interval (sec)', type: 'number', min: 5, third: true },
  account:        { label: 'Account', placeholder: 'your-account.snowflakecomputing.com', type: 'text', required: true, flex: 2 },
  warehouse:      { label: 'Warehouse', placeholder: 'COMPUTE_WH', type: 'text', third: true },
  role:           { label: 'Role', placeholder: 'SYSADMIN', type: 'text', third: true },
  workspace_url:  { label: 'Workspace URL', placeholder: 'https://dbc-xxx.cloud.databricks.com', type: 'text', required: true, flex: 2 },
  http_path:      { label: 'HTTP Path', placeholder: '/sql/1.0/warehouses/xxx', type: 'text', required: true, flex: 2 },
  catalog:        { label: 'Catalog', placeholder: 'hive_metastore', type: 'text', required: true, half: true },
  token:          { label: 'Access Token', placeholder: 'dapi...', type: 'password', required: true, half: true },
};

export default function Connectors() {
  const navigate = useNavigate();
  const [connectors, setConnectors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [selectedDb, setSelectedDb] = useState('clickhouse');
  const [form, setForm] = useState({ name: '', poll_interval: 30 });
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
    setForm({ name: '', poll_interval: 30, ...db.defaults });
  }

  async function handleConnect(e) {
    e.preventDefault();
    setConnecting(true);
    setError('');
    setResult(null);

    try {
      // Map form fields to API payload based on db type
      const payload = {
        name: form.name,
        db_type: selectedDb,
        poll_interval: form.poll_interval,
        extra: {},
      };

      if (selectedDb === 'databricks') {
        payload.host = form.workspace_url || '';
        payload.port = 443;
        payload.database = form.catalog || '';
        payload.username = '';
        payload.password = form.token || '';
        payload.schema = 'default';
        payload.extra = { http_path: form.http_path || '', token: form.token || '' };
      } else if (selectedDb === 'snowflake') {
        payload.host = form.account || '';
        payload.port = 443;
        payload.database = form.database || '';
        payload.username = form.username || '';
        payload.password = form.password || '';
        payload.schema = form.schema || 'PUBLIC';
        payload.extra = { warehouse: form.warehouse || 'COMPUTE_WH', role: form.role || 'SYSADMIN' };
      } else {
        payload.host = form.host || '';
        payload.port = form.port || 5432;
        payload.database = form.database || '';
        payload.username = form.username || '';
        payload.password = form.password || '';
        payload.schema = form.schema || '';
      }

      const res = await addConnector(payload);
      setResult(res);
      setShowForm(false);
      loadConnectors();
    } catch (err) {
      console.error('[Connectors] Error:', err);
      const msg = err?.message || err?.detail || (typeof err === 'string' ? err : 'Connection failed');
      setError(String(msg));
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
                      {conn.db_type === 'databricks'
                        ? `${conn.host} · catalog: ${conn.database}`
                        : `${conn.db_type} · ${conn.host}:${conn.port}${conn.database ? `/${conn.database}` : ''}`
                      }
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
        {(() => {
          const db = DB_TYPES.find(d => d.id === selectedDb);
          const fields = db.fields;
          const inputStyle = { width: '100%', padding: '0.5rem 0.75rem', background: '#0a0a0a', border: '1px solid #333', borderRadius: '4px', color: '#e5e5e5', fontSize: '0.875rem' };
          const labelStyle = { display: 'block', fontSize: '0.75rem', color: '#888', marginBottom: '0.25rem' };

          // Group fields into rows: half+half, third+third+third, rest single
          const rowGroups = [];
          let i = 0;
          while (i < fields.length) {
            const f = FIELD_DEFS[fields[i]];
            const next1 = i + 1 < fields.length ? FIELD_DEFS[fields[i + 1]] : null;
            const next2 = i + 2 < fields.length ? FIELD_DEFS[fields[i + 2]] : null;

            if (f.half && next1?.half) {
              rowGroups.push({ type: 'half', fields: [fields[i], fields[i + 1]] });
              i += 2;
            } else if (f.third && next1?.third && next2?.third) {
              rowGroups.push({ type: 'third', fields: [fields[i], fields[i + 1], fields[i + 2]] });
              i += 3;
            } else {
              rowGroups.push({ type: 'single', fields: [fields[i]] });
              i += 1;
            }
          }

          return rowGroups.map((group, gi) => {
            const cols = group.type === 'half' ? '1fr 1fr' : group.type === 'third' ? '1fr 1fr 1fr' : '1fr';
            return (
              <div key={gi} style={{ display: 'grid', gridTemplateColumns: cols, gap: '1rem', marginBottom: '1rem' }}>
                {group.fields.map(fk => {
                  const fd = FIELD_DEFS[fk];
                  return (
                    <div key={fk}>
                      <label style={labelStyle}>{fd.label}{fd.required && ' *'}</label>
                      <input
                        type={fd.type}
                        value={form[fk] || ''}
                        onChange={e => setForm(frm => ({ ...frm, [fk]: fd.type === 'number' ? parseInt(e.target.value) || 0 : e.target.value }))}
                        placeholder={fd.placeholder}
                        required={fd.required}
                        min={fd.min}
                        style={inputStyle}
                      />
                    </div>
                  );
                })}
              </div>
            );
          });
        })()}

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
