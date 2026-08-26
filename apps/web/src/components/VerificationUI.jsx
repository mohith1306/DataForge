export default function VerificationUI({ events }) {
  const verificationEvents = events?.filter(
    e => e.type?.includes('verification')
  ) || [];

  if (verificationEvents.length === 0) {
    return (
      <div className="empty-state">
        <p>No verification results yet</p>
        <p style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.5rem' }}>
          Verification runs after remediation execution
        </p>
      </div>
    );
  }

  const latestVerification = verificationEvents[verificationEvents.length - 1];

  // Try to get results from metadata_ (may be verification_result or direct results)
  const metadata = latestVerification.metadata_ || {};
  const results = metadata.results || metadata.verification_result?.results || [];
  const overall = metadata.overall_status || metadata.verification_result?.overall_status || 'unknown';

  const resolved = results.filter(r => r.status === 'resolved').length;
  const total = results.length;

  return (
    <div className="verification-ui">
      <div className="card">
        <div className="card-header">Verification Results</div>

        <div className="verification-summary">
          <div className="verification-status">
            <span
              className="status-indicator"
              style={{
                background: overall === 'resolved' ? '#22c55e' :
                           overall === 'partially_resolved' ? '#eab308' : '#ef4444',
              }}
            />
            <span style={{ fontWeight: 600 }}>
              {overall === 'resolved' ? 'All Checks Passed' :
               overall === 'partially_resolved' ? 'Partially Resolved' :
               results.length > 0 ? 'Verification Failed' : 'No Results'}
            </span>
          </div>
          {results.length > 0 && (
            <div className="verification-count">
              {resolved}/{total} checks passed
            </div>
          )}
        </div>

        {results.length > 0 && (
          <div className="verification-results">
            <div className="results-header">
              <span>Metric</span>
              <span>Before</span>
              <span>After</span>
              <span>Status</span>
            </div>
            {results.map((result, i) => (
              <div key={i} className="result-row">
                <span className="result-metric">{result.metric}</span>
                <span className="result-before">{result.before || '—'}</span>
                <span className="result-after">{result.after || '—'}</span>
                <span
                  className="result-status"
                  style={{
                    color: result.status === 'resolved' ? '#22c55e' :
                          result.status === 'error' ? '#ef4444' : '#eab308',
                  }}
                >
                  {result.status === 'resolved' ? '✓' :
                   result.status === 'error' ? '✗' : '○'}
                </span>
              </div>
            ))}
          </div>
        )}

        {(metadata.before_summary || metadata.verification_result?.before_summary) && (
          <div className="before-after-section">
            <h3 style={{ fontSize: '0.875rem', color: '#999', marginBottom: '0.5rem' }}>
              Before/After Summary
            </h3>
            <div className="before-after-grid">
              {Object.entries(
                metadata.before_summary || metadata.verification_result?.before_summary || {}
              ).map(([key, before]) => (
                <div key={key} className="before-after-item">
                  <div className="ba-metric">{key}</div>
                  <div className="ba-values">
                    <span className="ba-before">{before}</span>
                    <span className="ba-arrow">→</span>
                    <span className="ba-after">
                      {(metadata.after_summary || metadata.verification_result?.after_summary)?.[key] || '—'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
