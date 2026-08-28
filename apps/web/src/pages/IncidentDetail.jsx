import { useState, useEffect, useRef } from 'react';
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
  const loadedRef = useRef(false);
  const eventIdsRef = useRef(new Set());
  const pendingEventsRef = useRef([]);

  useEffect(() => {
    console.log('[IncidentDetail] Mounted for incident:', id);
    loadedRef.current = false;
    eventIdsRef.current = new Set();
    pendingEventsRef.current = [];

    loadData();

    // Subscribe to SSE — buffer events until snapshot loads
    const unsub = streamIncident(id, (event) => {
      console.log('[IncidentDetail] SSE event received:', event.type);
      if (event.type === 'incident.updated') {
        console.log('[IncidentDetail] Incident updated:', event.data?.status);
        setIncident(prev => ({ ...prev, ...event.data }));
      }
      if (event.type === 'event.created' && event.data) {
        const key = event.data.id || `${event.data.type}-${event.data.message}`;
        if (!eventIdsRef.current.has(key)) {
          eventIdsRef.current.add(key);
          console.log('[IncidentDetail] New event:', event.data.type, event.data.message);
          if (loadedRef.current) {
            setEvents(prev => [...prev, event.data]);
          } else {
            pendingEventsRef.current.push(event.data);
          }
        }
      }
    });

    return () => {
      console.log('[IncidentDetail] Unmounted for incident:', id);
      unsub();
    };
  }, [id]);

  async function loadData() {
    try {
      console.log('[IncidentDetail] Loading incident data:', id);
      const [inc, evts] = await Promise.all([
        fetchIncident(id),
        fetchEvents(id),
      ]);
      setIncident(inc);
      console.log('[IncidentDetail] Incident loaded:', inc.title, '| status:', inc.status);
      evts.forEach(e => {
        const key = e.id || `${e.type}-${e.message}`;
        eventIdsRef.current.add(key);
      });
      const merged = [...evts, ...pendingEventsRef.current];
      pendingEventsRef.current = [];
      setEvents(merged);
      console.log('[IncidentDetail] Events loaded:', merged.length, 'events');
    } catch (err) {
      console.error('[IncidentDetail] Failed to load:', err);
    } finally {
      setLoading(false);
      loadedRef.current = true;
    }
  }

  async function handleStartInvestigation() {
    console.log('[IncidentDetail] Starting investigation for:', id);
    try {
      await startInvestigation(id);
      console.log('[IncidentDetail] Investigation started successfully');
    } catch (err) {
      console.error('[IncidentDetail] Failed to start investigation:', err);
    }
  }

  async function handleRemediate() {
    console.log('[IncidentDetail] Executing remediation for:', id);
    try {
      await executeRemediation(id);
      console.log('[IncidentDetail] Remediation started successfully');
    } catch (err) {
      console.error('[IncidentDetail] Failed to execute remediation:', err);
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
            onClick={() => {
              console.log('[IncidentDetail] Tab changed to:', tab);
              setActiveTab(tab);
            }}
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
