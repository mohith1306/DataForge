import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { fetchIncident, fetchEvents, streamIncident, startInvestigation, executeRemediation } from '../api';
import AgentTimeline from '../components/AgentTimeline';
import EvidenceViewer from '../components/EvidenceViewer';
import RootCausePanel from '../components/RootCausePanel';
import ApprovalUI from '../components/ApprovalUI';
import VerificationUI from '../components/VerificationUI';

export default function IncidentDetail() {
  const { id } = useParams();
  const [incident, setIncident] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('timeline');

  useEffect(() => {
    loadData();
    const unsub = streamIncident(id, (event) => {
      if (event.type === 'incident.updated') {
        setIncident(prev => ({ ...prev, ...event.data }));
      }
      if (event.type === 'event.created') {
        setEvents(prev => [...prev, event.data]);
      }
    });
    return () => unsub();
  }, [id]);

  async function loadData() {
    try {
      const [inc, evts] = await Promise.all([
        fetchIncident(id),
        fetchEvents(id),
      ]);
      setIncident(inc);
      setEvents(evts);
    } catch (err) {
      console.error('Failed to load incident:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleStartInvestigation() {
    try {
      await startInvestigation(id);
      loadData();
    } catch (err) {
      console.error('Failed to start investigation:', err);
    }
  }

  async function handleRemediate() {
    try {
      await executeRemediation(id);
      loadData();
    } catch (err) {
      console.error('Failed to execute remediation:', err);
    }
  }

  if (loading) return <div className="loading">Loading incident...</div>;
  if (!incident) return <div className="error">Incident not found</div>;

  return (
    <div>
      <div className="card">
        <div className="incident-header">
          <div>
            <h1 style={{ fontSize: '1.25rem', fontWeight: 600 }}>{incident.title}</h1>
            <div className="incident-meta" style={{ marginTop: '0.5rem' }}>
              <span className={`badge badge-${incident.severity}`}>{incident.severity}</span>
              <span className="badge" style={{ background: '#3b82f620', color: '#3b82f6' }}>
                {incident.status}
              </span>
              {incident.incident_type && (
                <span className="incident-type">{incident.incident_type}</span>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {incident.status === 'created' && (
              <button className="btn btn-primary" onClick={handleStartInvestigation}>
                Start Investigation
              </button>
            )}
            {incident.status === 'awaiting_approval' && (
              <button className="btn btn-warning" onClick={handleRemediate}>
                Execute Remediation
              </button>
            )}
          </div>
        </div>
        {incident.description && (
          <p style={{ color: '#999', marginTop: '0.75rem', fontSize: '0.875rem' }}>
            {incident.description}
          </p>
        )}
      </div>

      <div className="tabs">
        {['timeline', 'evidence', 'root_cause', 'approval', 'verification'].map(tab => (
          <button
            key={tab}
            className={`tab ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}
          </button>
        ))}
      </div>

      <div className="tab-content">
        {activeTab === 'timeline' && <AgentTimeline events={events} />}
        {activeTab === 'evidence' && <EvidenceViewer events={events} />}
        {activeTab === 'root_cause' && <RootCausePanel events={events} />}
        {activeTab === 'approval' && <ApprovalUI events={events} incident={incident} />}
        {activeTab === 'verification' && <VerificationUI events={events} />}
      </div>
    </div>
  );
}
