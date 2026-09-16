"""Design Partner Management — tracks design partner onboarding and status.

Manages the design partner lifecycle:
- Onboarding
- Baseline measurement
- Progressive autonomy enablement
- KPI tracking
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PartnerStatus(str, Enum):
    PROSPECT = "prospect"
    ONBOARDING = "onboarding"
    READ_ONLY = "read_only"
    RECOMMENDED_REMEDIATION = "recommended_remediation"
    APPROVAL_CONTROLLED = "approval_controlled"
    AUTONOMOUS = "autonomous"
    CHURNED = "churned"


class AutonomyStage(str, Enum):
    READ_ONLY = "read_only"
    RECOMMENDED = "recommended"
    APPROVAL_CONTROLLED = "approval_controlled"
    AUTONOMOUS = "autonomous"


@dataclass
class DesignPartner:
    """A design partner organization."""
    id: str
    name: str
    status: PartnerStatus
    industry: str = ""
    data_platforms: list[str] = field(default_factory=list)
    pipeline_count: int = 0
    contact_name: str = ""
    contact_email: str = ""
    onboarded_at: str = ""
    baseline_measured_at: str = ""
    current_stage: AutonomyStage = AutonomyStage.READ_ONLY
    notes: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "industry": self.industry,
            "data_platforms": self.data_platforms,
            "pipeline_count": self.pipeline_count,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "onboarded_at": self.onboarded_at,
            "baseline_measured_at": self.baseline_measured_at,
            "current_stage": self.current_stage.value,
            "notes": self.notes,
            "metadata": self.metadata,
        }


@dataclass
class BaselineMetrics:
    """Baseline metrics collected during initial measurement."""
    partner_id: str
    incident_count: int = 0
    mttr_seconds: float = 0.0
    time_to_diagnosis_seconds: float = 0.0
    time_to_remediation_seconds: float = 0.0
    false_positive_rate: float = 0.0
    missed_incidents: int = 0
    engineer_hours_per_week: float = 0.0
    collected_at: str = ""

    def to_dict(self) -> dict:
        return {
            "partner_id": self.partner_id,
            "incident_count": self.incident_count,
            "mttr_seconds": self.mttr_seconds,
            "mttr_hours": round(self.mttr_seconds / 3600, 2),
            "time_to_diagnosis_seconds": self.time_to_diagnosis_seconds,
            "time_to_remediation_seconds": self.time_to_remediation_seconds,
            "false_positive_rate": self.false_positive_rate,
            "missed_incidents": self.missed_incidents,
            "engineer_hours_per_week": self.engineer_hours_per_week,
            "collected_at": self.collected_at,
        }


class DesignPartnerManager:
    """Manages design partner lifecycle and tracking."""

    def __init__(self):
        self.partners: dict[str, DesignPartner] = {}
        self.baselines: dict[str, BaselineMetrics] = {}
        self.stage_history: dict[str, list[dict]] = {}

    def add_partner(
        self,
        partner_id: str,
        name: str,
        industry: str = "",
        data_platforms: list[str] | None = None,
        pipeline_count: int = 0,
        contact_name: str = "",
        contact_email: str = "",
    ) -> DesignPartner:
        """Add a new design partner."""
        now = datetime.now(timezone.utc).isoformat()
        partner = DesignPartner(
            id=partner_id,
            name=name,
            status=PartnerStatus.PROSPECT,
            industry=industry,
            data_platforms=data_platforms or [],
            pipeline_count=pipeline_count,
            contact_name=contact_name,
            contact_email=contact_email,
        )
        self.partners[partner_id] = partner
        self.stage_history[partner_id] = []
        logger.info("Design partner added: %s (%s)", name, partner_id)
        return partner

    def start_onboarding(self, partner_id: str) -> DesignPartner | None:
        """Move partner to onboarding status."""
        partner = self.partners.get(partner_id)
        if not partner:
            return None
        partner.status = PartnerStatus.ONBOARDING
        partner.onboarded_at = datetime.now(timezone.utc).isoformat()
        self._record_stage_change(partner_id, "onboarding")
        return partner

    def enable_read_only(self, partner_id: str) -> DesignPartner | None:
        """Enable read-only mode for the partner."""
        partner = self.partners.get(partner_id)
        if not partner:
            return None
        partner.status = PartnerStatus.READ_ONLY
        partner.current_stage = AutonomyStage.READ_ONLY
        self._record_stage_change(partner_id, "read_only")
        return partner

    def enable_recommended_remediation(self, partner_id: str) -> DesignPartner | None:
        """Enable recommended remediation (no auto-execution)."""
        partner = self.partners.get(partner_id)
        if not partner:
            return None
        partner.status = PartnerStatus.RECOMMENDED_REMEDIATION
        partner.current_stage = AutonomyStage.RECOMMENDED
        self._record_stage_change(partner_id, "recommended_remediation")
        return partner

    def enable_approval_controlled(self, partner_id: str) -> DesignPartner | None:
        """Enable approval-controlled execution."""
        partner = self.partners.get(partner_id)
        if not partner:
            return None
        partner.status = PartnerStatus.APPROVAL_CONTROLLED
        partner.current_stage = AutonomyStage.APPROVAL_CONTROLLED
        self._record_stage_change(partner_id, "approval_controlled")
        return partner

    def enable_autonomous(self, partner_id: str) -> DesignPartner | None:
        """Enable full autonomous remediation."""
        partner = self.partners.get(partner_id)
        if not partner:
            return None
        partner.status = PartnerStatus.AUTONOMOUS
        partner.current_stage = AutonomyStage.AUTONOMOUS
        self._record_stage_change(partner_id, "autonomous")
        return partner

    def record_baseline(self, baseline: BaselineMetrics):
        """Record baseline metrics for a partner."""
        baseline.collected_at = datetime.now(timezone.utc).isoformat()
        self.baselines[baseline.partner_id] = baseline
        partner = self.partners.get(baseline.partner_id)
        if partner:
            partner.baseline_measured_at = baseline.collected_at
        logger.info("Baseline recorded for partner %s", baseline.partner_id)

    def get_partner(self, partner_id: str) -> DesignPartner | None:
        """Get a design partner by ID."""
        return self.partners.get(partner_id)

    def list_partners(self, status: PartnerStatus | None = None) -> list[DesignPartner]:
        """List all design partners, optionally filtered by status."""
        partners = list(self.partners.values())
        if status:
            partners = [p for p in partners if p.status == status]
        return partners

    def get_baseline(self, partner_id: str) -> BaselineMetrics | None:
        """Get baseline metrics for a partner."""
        return self.baselines.get(partner_id)

    def get_stage_history(self, partner_id: str) -> list[dict]:
        """Get the stage change history for a partner."""
        return self.stage_history.get(partner_id, [])

    def add_note(self, partner_id: str, note: str, author: str = "") -> bool:
        """Add a note to a partner's record."""
        partner = self.partners.get(partner_id)
        if not partner:
            return False
        partner.notes.append({
            "note": note,
            "author": author,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return True

    def get_stats(self) -> dict:
        """Get aggregate stats across all partners."""
        partners = list(self.partners.values())
        by_status = {}
        for p in partners:
            by_status[p.status.value] = by_status.get(p.status.value, 0) + 1

        by_stage = {}
        for p in partners:
            by_stage[p.current_stage.value] = by_stage.get(p.current_stage.value, 0) + 1

        return {
            "total_partners": len(partners),
            "by_status": by_status,
            "by_stage": by_stage,
            "baselines_collected": len(self.baselines),
        }

    def _record_stage_change(self, partner_id: str, new_stage: str):
        """Record a stage change in history."""
        if partner_id not in self.stage_history:
            self.stage_history[partner_id] = []
        self.stage_history[partner_id].append({
            "stage": new_stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
