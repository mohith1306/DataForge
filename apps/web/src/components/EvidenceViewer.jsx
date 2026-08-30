const SOURCE_COLORS = {
  database: '#3b82f6',
  pipeline: '#8b5cf6',
  github: '#f59e0b',
  correlation: '#a855f7',
  sandbox: '#f97316',
  system: '#666',
};

const SOURCE_ICONS = {
  database: '🗄️',
  pipeline: '⚙️',
  github: '📦',
  correlation: '🔗',
  sandbox: '🧪',
  system: '📌',
};

export default function EvidenceViewer({ events }) {
  // Match actual event types emitted by the investigation workflow
  const evidenceEvents = events?.filter(e => {
    const t = e.type || '';
    return (
      t.includes('evidence') ||
      t.includes('finding') ||
      t.includes('tool.completed') ||
      t.includes('database.') ||
      t.includes('pipeline.') ||
      t.includes('github.') ||
      t.includes('investigation.')
    );
  }) || [];

  // Also parse EVIDENCE from investigation_complete text
  const completedEvent = events?.find(e => e.type === 'investigation_complete' || e.type === 'investigation.completed');
  const parsedEvidence = [];
  if (completedEvent?.message) {
    const msg = completedEvent.message;
    const evMatch = msg.match(/EVIDENCE:\s*([\s\S]*?)(?=\nREMEDIATION|\nROOT CAUSE|\nCONFIDENCE|$)/i);
    if (evMatch) {
      parsedEvidence.push({
        id: 'parsed-evidence',
        type: 'investigation_result',
        agent: 'investigator',
        message: evMatch[1].trim(),
      });
    }
  }

  const allEvidence = [...evidenceEvents, ...parsedEvidence];

  if (allEvidence.length === 0) {
    return (
      <div className="empty-state">
        <p>No evidence collected yet</p>
        <p style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.5rem' }}>
          Evidence is gathered during the investigation phase
        </p>
      </div>
    );
  }

  // Group by source derived from event type or agent field
  const grouped = allEvidence.reduce((acc, event) => {
    let source = event.agent || 'system';
    // Derive source from event type if agent is generic
    if (source === 'system' || !source) {
      const t = event.type || '';
      if (t.includes('database') || t.includes('schema') || t.includes('profile')) source = 'database';
      else if (t.includes('pipeline')) source = 'pipeline';
      else if (t.includes('github') || t.includes('commit')) source = 'github';
      else if (t.includes('correlation')) source = 'correlation';
      else if (t.includes('sandbox')) source = 'sandbox';
    }
    if (!acc[source]) acc[source] = [];
    acc[source].push(event);
    return acc;
  }, {});

  return (
    <div className="evidence-viewer">
      {Object.entries(grouped).map(([source, evts]) => (
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
            <span className="evidence-count">{evts.length}</span>
          </div>
          <div className="evidence-items">
            {evts.map((event, i) => (
              <div key={event.id || i} className="evidence-item">
                <div className="evidence-type">{event.type || event.agent || 'event'}</div>
                <div className="evidence-message">{event.message}</div>
                {event.metadata_ && (
                  <pre className="evidence-data">
                    {typeof event.metadata_ === 'string'
                      ? event.metadata_
                      : JSON.stringify(event.metadata_, null, 2)}
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
