const SOURCE_COLORS = {
  database: '#3b82f6',
  pipeline: '#8b5cf6',
  github: '#f59e0b',
  correlation: '#a855f7',
  sandbox: '#f97316',
};

const SOURCE_ICONS = {
  database: '🗄️',
  pipeline: '⚙️',
  github: '📦',
  correlation: '🔗',
  sandbox: '🧪',
};

export default function EvidenceViewer({ events }) {
  const evidenceEvents = events?.filter(
    e => e.type?.includes('evidence') || e.type?.includes('finding')
  ) || [];

  if (evidenceEvents.length === 0) {
    return (
      <div className="empty-state">
        <p>No evidence collected yet</p>
        <p style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.5rem' }}>
          Evidence is gathered during the investigation phase
        </p>
      </div>
    );
  }

  // Group by source
  const grouped = evidenceEvents.reduce((acc, event) => {
    const source = event.agent || 'unknown';
    if (!acc[source]) acc[source] = [];
    acc[source].push(event);
    return acc;
  }, {});

  return (
    <div className="evidence-viewer">
      {Object.entries(grouped).map(([source, events]) => (
        <div key={source} className="evidence-group">
          <div className="evidence-group-header">
            <span
              className="evidence-source-icon"
              style={{ color: SOURCE_COLORS[source] || '#666' }}
            >
              {SOURCE_ICONS[source] || '📌'}
            </span>
            <span className="evidence-source-name">
              {source.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}
            </span>
            <span className="evidence-count">{events.length}</span>
          </div>
          <div className="evidence-items">
            {events.map((event, i) => (
              <div key={event.id || i} className="evidence-item">
                <div className="evidence-type">{event.type}</div>
                <div className="evidence-message">{event.message}</div>
                {event.metadata_ && (
                  <pre className="evidence-data">
                    {JSON.stringify(event.metadata_, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
