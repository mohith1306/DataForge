import { useState } from 'react';
import { approveIncident } from '../api';

export default function ApprovalUI({ events, incident }) {
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState(null);

  const planEvent = events?.find(e => e.type === 'plan.created');
  const approvalEvent = events?.find(e => e.type?.includes('approval'));

  // Parse REMEDIATION PLAN from investigation_complete text
  const completedEvent = events?.find(e => e.type === 'investigation_complete' || e.type === 'investigation.completed');
  let parsedPlan = null;
  if (completedEvent?.message && !planEvent) {
    const remMatch = completedEvent.message.match(/REMEDIATION(?:\s*PLAN)?:\s*([\s\S]*?)$/i);
    if (remMatch) {
      parsedPlan = { summary: remMatch[1].trim() };
    }
  }

  const plan = planEvent?.metadata_ || parsedPlan;

  if (!planEvent && !approvalEvent && !parsedPlan) {
    return (
      <div className="empty-state">
        <p>No remediation plan yet</p>
        <p style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.5rem' }}>
          A plan is generated after root cause analysis
        </p>
      </div>
    );
  }

  async function handleApproval(action) {
    console.log('[ApprovalUI] User clicked:', action, '| incident:', incident.id);
    setApproving(true);
    setError(null);
    try {
      const result = await approveIncident(incident.id, action);
      console.log('[ApprovalUI] Approval result:', result);
      window.location.reload();
    } catch (err) {
      console.error('[ApprovalUI] Approval failed:', err);
      setError(err.message);
    } finally {
      setApproving(false);
    }
  }

  return (
    <div className="approval-ui">
      <div className="card">
        <div className="card-header">Remediation Plan</div>

        {plan.summary && (
          <div className="plan-summary">
            <h3 style={{ fontSize: '0.875rem', color: '#999', marginBottom: '0.5rem' }}>
              Summary
            </h3>
            <p>{plan.summary}</p>
          </div>
        )}

        {plan.risk_level && (
          <div className="risk-badge" style={{
            background: plan.risk_level === 'dangerous' ? '#ef444420' :
                       plan.risk_level === 'high' ? '#f9731620' : '#eab30820',
            color: plan.risk_level === 'dangerous' ? '#ef4444' :
                  plan.risk_level === 'high' ? '#f97316' : '#eab308',
          }}>
            Risk Level: {plan.risk_level}
          </div>
        )}

        {plan.actions && plan.actions.length > 0 && (
          <div className="plan-actions">
            <h3 style={{ fontSize: '0.875rem', color: '#999', marginBottom: '0.5rem' }}>
              Actions
            </h3>
            {plan.actions.map((action, i) => (
              <div key={i} className="plan-action">
                <span className="action-tool">{action.tool}</span>
                <span className="action-params">
                  {action.params && Object.entries(action.params).map(([k, v]) => (
                    <span key={k} className="action-param">
                      {k}: {typeof v === 'string' ? v : JSON.stringify(v)}
                    </span>
                  ))}
                </span>
              </div>
            ))}
          </div>
        )}

        {plan.estimated_recovery_time && (
          <div className="recovery-time">
            Estimated Recovery: {plan.estimated_recovery_time}
          </div>
        )}

        {error && (
          <div className="alert alert-error" style={{ marginTop: '1rem' }}>
            {error}
          </div>
        )}

        {incident?.status === 'awaiting_approval' && (
          <div className="approval-actions" style={{ marginTop: '1.5rem' }}>
            <button
              className="btn btn-success"
              disabled={approving}
              onClick={() => handleApproval('approve')}
            >
              {approving ? 'Approving...' : 'Approve & Execute'}
            </button>
            <button
              className="btn btn-danger"
              disabled={approving}
              onClick={() => handleApproval('reject')}
            >
              Reject
            </button>
          </div>
        )}

        {approvalEvent && (
          <div className="approval-result" style={{ marginTop: '1rem', color: '#888', fontSize: '0.875rem' }}>
            {approvalEvent.message}
          </div>
        )}
      </div>
    </div>
  );
}
