export default function RootCausePanel({ events }) {
  const diagnosisEvents = events?.filter(
    e => e.type?.includes('diagnosis') || e.type?.includes('root_cause')
  ) || [];

  if (diagnosisEvents.length === 0) {
    return (
      <div className="empty-state">
        <p>No root cause analysis yet</p>
        <p style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.5rem' }}>
          Root cause is identified after evidence collection
        </p>
      </div>
    );
  }

  const latestDiagnosis = diagnosisEvents[diagnosisEvents.length - 1];
  const metadata = latestDiagnosis.metadata_ || {};

  return (
    <div className="root-cause-panel">
      <div className="card">
        <div className="card-header">Root Cause Analysis</div>

        <div className="diagnosis-content">
          <div className="diagnosis-section">
            <h3 style={{ fontSize: '0.875rem', color: '#999', marginBottom: '0.5rem' }}>
              Root Cause
            </h3>
            <p style={{ fontSize: '0.95rem', lineHeight: '1.6' }}>
              {latestDiagnosis.message || 'No root cause identified'}
            </p>
          </div>

          {metadata.confidence !== undefined && (
            <div className="diagnosis-section">
              <h3 style={{ fontSize: '0.875rem', color: '#999', marginBottom: '0.5rem' }}>
                Confidence
              </h3>
              <div className="confidence-bar">
                <div
                  className="confidence-fill"
                  style={{
                    width: `${(metadata.confidence * 100).toFixed(0)}%`,
                    background: metadata.confidence > 0.7 ? '#22c55e' :
                               metadata.confidence > 0.4 ? '#eab308' : '#ef4444',
                  }}
                />
                <span className="confidence-value">
                  {(metadata.confidence * 100).toFixed(1)}%
                </span>
              </div>
            </div>
          )}

          {metadata.alternatives && metadata.alternatives.length > 0 && (
            <div className="diagnosis-section">
              <h3 style={{ fontSize: '0.875rem', color: '#999', marginBottom: '0.5rem' }}>
                Alternative Explanations
              </h3>
              <ul className="alternatives-list">
                {metadata.alternatives.map((alt, i) => (
                  <li key={i} className="alternative-item">
                    {typeof alt === 'string' ? alt : JSON.stringify(alt)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {metadata.business_impact && (
            <div className="diagnosis-section">
              <h3 style={{ fontSize: '0.875rem', color: '#999', marginBottom: '0.5rem' }}>
                Business Impact
              </h3>
              <div className="impact-grid">
                {Object.entries(metadata.business_impact).map(([key, value]) => (
                  <div key={key} className="impact-item">
                    <span className="impact-key">{key.replace('_', ' ')}</span>
                    <span className="impact-value">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
