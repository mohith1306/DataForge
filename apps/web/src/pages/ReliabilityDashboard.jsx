import { useState, useEffect } from 'react';

const GRADE_COLORS = {
  A: '#22c55e', B: '#3b82f6', C: '#eab308', D: '#f97316', F: '#ef4444',
};

const RISK_COLORS = {
  low: '#22c55e', medium: '#eab308', high: '#f97316', critical: '#ef4444',
};

export default function ReliabilityDashboard() {
  const [score, setScore] = useState(null);
  const [tiers, setTiers] = useState([]);
  const [subscription, setSubscription] = useState(null);
  const [memStats, setMemStats] = useState(null);
  const [predictions, setPredictions] = useState([]);
  const [changeStats, setChangeStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  async function loadData() {
    try {
      const results = await Promise.allSettled([
        fetch('/api/commercial/reliability/score/cdc7cdb7-8506-4faf-a93e-31bf1aa668a3', { headers: authHeaders() }).then(r => r.json()),
        fetch('/api/commercial/tiers', { headers: authHeaders() }).then(r => r.json()),
        fetch('/api/commercial/subscription/cdc7cdb7-8506-4faf-a93e-31bf1aa668a3', { headers: authHeaders() }).then(r => r.ok ? r.json() : null),
        fetch('/api/commercial/memory/stats', { headers: authHeaders() }).then(r => r.json()),
        fetch('/api/commercial/preventive/predictions?min_risk=medium', { headers: authHeaders() }).then(r => r.json()),
        fetch('/api/commercial/changes/stats', { headers: authHeaders() }).then(r => r.json()),
      ]);

      if (results[0].status === 'fulfilled') setScore(results[0].value);
      if (results[1].status === 'fulfilled') setTiers(results[1].value.tiers || []);
      if (results[2].status === 'fulfilled' && results[2].value) setSubscription(results[2].value);
      if (results[3].status === 'fulfilled') setMemStats(results[3].value);
      if (results[4].status === 'fulfilled') setPredictions(results[4].value.predictions || []);
      if (results[5].status === 'fulfilled') setChangeStats(results[5].value);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <div className="loading">Loading reliability data...</div>;
  if (error) return <div className="empty-state">Error: {error}</div>;

  const grade = score?.grade || 'F';
  const overall = score?.overall_score ?? 0;
  const dims = score?.dimensions || [];
  const recs = score?.recommendations || [];

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ margin: 0, fontSize: '1.25rem' }}>Reliability Dashboard</h2>
        {subscription && (
          <span className="badge" style={{ background: '#8b5cf620', color: '#8b5cf6', fontSize: '0.8rem' }}>
            {subscription.tier_name || subscription.tier}
          </span>
        )}
      </div>

      {/* Overall Score */}
      <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
        <div className="stat-card">
          <div className="stat-value" style={{ color: GRADE_COLORS[grade] || '#e5e5e5' }}>
            {grade}
          </div>
          <div className="stat-label">Grade</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{overall.toFixed(0)}</div>
          <div className="stat-label">Score / 100</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{memStats?.total_records ?? 0}</div>
          <div className="stat-label">Incidents in Memory</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{predictions.length}</div>
          <div className="stat-label">Active Risk Predictions</div>
        </div>
      </div>

      {/* Summary */}
      {score?.summary && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">Summary</div>
          <p style={{ margin: 0, color: '#ccc', fontSize: '0.9rem' }}>{score.summary}</p>
        </div>
      )}

      {/* Dimension Breakdown */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header">Score Dimensions</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {dims.map(dim => (
            <div key={dim.name}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.25rem' }}>
                <span style={{ color: '#ccc', textTransform: 'capitalize' }}>
                  {dim.name.replace(/_/g, ' ')}
                </span>
                <span style={{ color: dim.score >= 70 ? '#22c55e' : dim.score >= 50 ? '#eab308' : '#ef4444' }}>
                  {dim.score.toFixed(0)}/100 <span style={{ color: '#555' }}>(×{dim.weight})</span>
                </span>
              </div>
              <div style={{ background: '#1a1a1a', borderRadius: '4px', height: '8px', overflow: 'hidden' }}>
                <div
                  style={{
                    width: `${dim.score}%`,
                    height: '100%',
                    background: dim.score >= 70 ? '#22c55e' : dim.score >= 50 ? '#eab308' : '#ef4444',
                    borderRadius: '4px',
                    transition: 'width 0.5s',
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recommendations */}
      {recs.length > 0 && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">Recommendations</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {recs.map((rec, i) => (
              <div
                key={i}
                style={{
                  padding: '0.6rem 0.75rem',
                  background: rec.startsWith('URGENT') ? '#ef444410' : '#eab30810',
                  border: `1px solid ${rec.startsWith('URGENT') ? '#ef444440' : '#eab30840'}`,
                  borderRadius: '6px',
                  fontSize: '0.8rem',
                  color: rec.startsWith('URGENT') ? '#ef4444' : '#eab308',
                }}
              >
                {rec}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        {/* Risk Predictions */}
        <div className="card">
          <div className="card-header">Preventive Risk Predictions</div>
          {predictions.length === 0 ? (
            <div style={{ color: '#666', fontSize: '0.85rem' }}>No active predictions</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {predictions.slice(0, 5).map(pred => (
                <div
                  key={pred.prediction_id}
                  style={{
                    padding: '0.5rem 0.75rem',
                    background: '#1a1a1a',
                    border: `1px solid ${RISK_COLORS[pred.risk_level] || '#333'}40`,
                    borderRadius: '6px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span
                      className="badge"
                      style={{ background: `${RISK_COLORS[pred.risk_level]}20`, color: RISK_COLORS[pred.risk_level] }}
                    >
                      {pred.risk_level}
                    </span>
                    <span style={{ fontSize: '0.75rem', color: '#888' }}>
                      {(pred.probability * 100).toFixed(0)}% probability
                    </span>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#ccc', marginTop: '0.375rem' }}>
                    {pred.description}
                  </div>
                  {pred.preventive_actions?.length > 0 && (
                    <div style={{ fontSize: '0.7rem', color: '#888', marginTop: '0.375rem' }}>
                      → {pred.preventive_actions[0]}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Incident Memory */}
        <div className="card">
          <div className="card-header">Incident Memory (Failure DNA)</div>
          {memStats ? (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#e5e5e5' }}>{memStats.total_records}</div>
                  <div style={{ fontSize: '0.7rem', color: '#888' }}>Incidents</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#8b5cf6' }}>{memStats.unique_dna}</div>
                  <div style={{ fontSize: '0.7rem', color: '#888' }}>DNA Patterns</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#3b82f6' }}>{memStats.services_affected}</div>
                  <div style={{ fontSize: '0.7rem', color: '#888' }}>Services</div>
                </div>
              </div>
              {memStats.categories && Object.keys(memStats.categories).length > 0 && (
                <div>
                  <div style={{ fontSize: '0.75rem', color: '#888', marginBottom: '0.375rem' }}>Categories</div>
                  <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap' }}>
                    {Object.entries(memStats.categories).map(([cat, count]) => (
                      <span key={cat} style={{ fontSize: '0.7rem', background: '#1a1a1a', border: '1px solid #333', borderRadius: '3px', padding: '0.125rem 0.5rem', color: '#888' }}>
                        {cat}: {count}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ color: '#666', fontSize: '0.85rem' }}>No memory data yet</div>
          )}
        </div>
      </div>

      {/* Product Tiers */}
      <div className="card" style={{ marginTop: '1.5rem' }}>
        <div className="card-header">Product Tiers</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
          {tiers.map(tier => {
            const isActive = subscription?.tier === tier.tier;
            return (
              <div
                key={tier.tier}
                style={{
                  padding: '1rem',
                  background: isActive ? '#8b5cf610' : '#1a1a1a',
                  border: `1px solid ${isActive ? '#8b5cf6' : '#333'}`,
                  borderRadius: '8px',
                  textAlign: 'center',
                }}
              >
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: isActive ? '#8b5cf6' : '#ccc' }}>
                  {tier.name}
                </div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#e5e5e5', margin: '0.5rem 0' }}>
                  {tier.price_monthly === 0 ? 'Free' : `$${tier.price_monthly}/mo`}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#888' }}>
                  {tier.feature_count} features
                </div>
                {isActive && (
                  <div style={{ fontSize: '0.7rem', color: '#8b5cf6', marginTop: '0.5rem', fontWeight: 600 }}>
                    ✓ Current Plan
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Change Stats */}
      {changeStats && changeStats.total_changes > 0 && (
        <div className="card" style={{ marginTop: '1.5rem' }}>
          <div className="card-header">Change Intelligence</div>
          <div style={{ display: 'flex', gap: '2rem', fontSize: '0.85rem' }}>
            <div>
              <span style={{ color: '#888' }}>Total changes: </span>
              <span style={{ color: '#e5e5e5', fontWeight: 600 }}>{changeStats.total_changes}</span>
            </div>
            <div>
              <span style={{ color: '#888' }}>Correlations: </span>
              <span style={{ color: '#e5e5e5', fontWeight: 600 }}>{changeStats.correlations_found}</span>
            </div>
            {changeStats.by_type && Object.entries(changeStats.by_type).map(([type, count]) => (
              <div key={type}>
                <span style={{ color: '#888', textTransform: 'capitalize' }}>{type}: </span>
                <span style={{ color: '#e5e5e5', fontWeight: 600 }}>{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
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
