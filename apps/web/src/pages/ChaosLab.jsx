import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { injectChaos, fetchFaults } from '../api';

const FAULT_ICONS = {
  schema_drift: '📋',
  null_injection: '🕳️',
  volume_drop: '📉',
  duplicate_injection: '👯',
  freshness_lag: '⏰',
  distribution_shift: '🌍',
  pipeline_failure: '💥',
};

const SEVERITY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
};

export default function ChaosLab() {
  const [faults, setFaults] = useState([]);
  const [injecting, setInjecting] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    loadFaults();
  }, []);

  async function loadFaults() {
    try {
      const data = await fetchFaults();
      setFaults(data.faults || []);
    } catch (err) {
      console.error('Failed to load faults:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleInject(faultType) {
    setInjecting(faultType);
    setResult(null);
    try {
      const res = await injectChaos(faultType);
      setResult(res);
      if (res.incident_id) {
        setTimeout(() => navigate(`/incidents/${res.incident_id}`), 2000);
      }
    } catch (err) {
      setResult({ status: 'error', message: err.message });
    } finally {
      setInjecting(null);
    }
  }

  return (
    <div>
      <div className="card">
        <div className="card-header">Chaos Lab</div>
        <p style={{ color: '#888', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
          Inject faults to test DataForge's autonomous incident response. Each fault creates an incident that triggers the full investigation pipeline.
        </p>

        {loading ? (
          <div className="loading">Loading faults...</div>
        ) : (
          <div className="chaos-grid">
            {faults.map(fault => (
              <div key={fault.type} className="chaos-card">
                <div className="chaos-icon">{FAULT_ICONS[fault.type] || '⚡'}</div>
                <div className="chaos-title">
                  {fault.type.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}
                </div>
                <div className="chaos-desc">{fault.description}</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.75rem' }}>
                  <span
                    className="badge"
                    style={{
                      background: `${SEVERITY_COLORS[fault.severity]}20`,
                      color: SEVERITY_COLORS[fault.severity],
                    }}
                  >
                    {fault.severity}
                  </span>
                  <button
                    className="btn btn-danger"
                    onClick={() => handleInject(fault.type)}
                    disabled={injecting !== null}
                  >
                    {injecting === fault.type ? 'Injecting...' : 'Inject Fault'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {result && (
          <div className={`alert alert-${result.status === 'error' ? 'error' : 'success'}`} style={{ marginTop: '1.5rem' }}>
            <strong>{result.status === 'error' ? 'Error' : 'Fault Injected!'}</strong>
            <p>{result.message}</p>
            {result.incident_id && (
              <p style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>
                Incident created: {result.incident_id.slice(0, 8)}...
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
