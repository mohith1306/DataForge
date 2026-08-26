const AGENT_COLORS = {
  database_agent: '#3b82f6',
  pipeline_agent: '#8b5cf6',
  github_agent: '#f59e0b',
  root_cause_agent: '#ef4444',
  remediation_agent: '#06b6d4',
  data_quality_agent: '#22c55e',
  evidence_merger: '#a855f7',
  sandbox: '#f97316',
  verifier: '#10b981',
};

const AGENT_ICONS = {
  database_agent: '🗄️',
  pipeline_agent: '⚙️',
  github_agent: '📦',
  root_cause_agent: '🔍',
  remediation_agent: '🔧',
  data_quality_agent: '📊',
  evidence_merger: '🔗',
  sandbox: '🧪',
  verifier: '✅',
};

export default function AgentTimeline({ events }) {
  if (!events || events.length === 0) {
    return (
      <div className="empty-state">
        <p>No events yet</p>
        <p style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.5rem' }}>
          Start an investigation to see the agent timeline
        </p>
      </div>
    );
  }

  return (
    <div className="timeline">
      {events.map((event, i) => {
        const agent = event.agent || 'system';
        const color = AGENT_COLORS[agent] || '#666';
        const icon = AGENT_ICONS[agent] || '📌';

        return (
          <div key={event.id || i} className="timeline-item">
            <div
              className="timeline-dot"
              style={{ background: color }}
            />
            <div className="timeline-content">
              <div className="timeline-header">
                <span className="timeline-agent" style={{ color }}>
                  {icon} {agent.replace('_', ' ')}
                </span>
                <span className="timeline-time">
                  {new Date(event.created_at).toLocaleTimeString()}
                </span>
              </div>
              <div className="timeline-message">{event.message || event.type}</div>
              {event.tool && (
                <div className="timeline-tool">
                  Tool: <code>{event.tool}</code>
                </div>
              )}
              {event.metadata_ && (
                <pre className="timeline-metadata">
                  {JSON.stringify(event.metadata_, null, 2)}
                </pre>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
