import { useState } from 'react';

export default function ApprovalUI({ events, incident }) {
  const [approving, setApproving] = useState(false);

  const approvalEvents = events?.filter(
    e => e.type?.includes('approval') || e.type?.includes('plan.created')
  ) || [];

  const planEvent = approvalEvents.find(e => e.type === 'plan.created');
  const approvalEvent = approvalEvents.find(e => e.type?.includes('approval.requested'));

  if (!planEvent && approvalEvents.length === 0) {
    return (
      <div className="empty-state">
        <p>No remediation plan yet</p>
        <p style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.5rem' }}>
          A plan is generated after root cause analysis
        </p>
      </div>
    );
  }

  const plan = planEvent?.metadata_ || {};

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

        {incident?.status === 'awaiting_approval' && (
          <div className="approval-actions" style={{ marginTop: '1.5rem' }}>
            <button
              className="btn btn-success"
              disabled={approving}
              onClick={() => handleApprove('approve')}
            >
              {approving ? 'Approving...' : 'Approve & Execute'}
            </button>
            <button
              className="btn btn-danger"
              disabled={approving}
              onClick={() => handleApprove('reject')}
            >
              Reject
            </button>
          </div>
        )}
      </div>
    </div>
  );

  async function handleApprove(action) {
    setApproving(true);
    try {
      await fetch(`http://localhost:8000/api/incidents/${incident.id}/approval`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, reviewer: 'ui_user' }),
      });
      window.location.reload();
    } catch (err) {
      console.error('Approval failed:', err);
    } finally {
      setApproving(false);
    }
  }
}
