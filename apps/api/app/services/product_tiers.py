"""Product Tiers — defines DataForge product packaging.

Tiers:
- Observe: Monitoring, alerting, dashboards
- Investigate: AI-powered root cause analysis
- Remediate: Approval-controlled remediation
- Autonomous: Full autonomous reliability
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProductTier(str, Enum):
    OBSERVE = "observe"
    INVESTIGATE = "investigate"
    REMEDIATE = "remediate"
    AUTONOMOUS = "autonomous"


TIER_FEATURES: dict[ProductTier, dict[str, Any]] = {
    ProductTier.OBSERVE: {
        "name": "DataForge Observe",
        "description": "Monitoring, alerting, and dashboards for data pipelines",
        "price_monthly": 0,
        "features": [
            "Pipeline monitoring",
            "Schema drift detection",
            "Freshness monitoring",
            "Data quality checks",
            "Alerting",
            "Dashboards",
            "Basic Reliability Graph",
        ],
        "limits": {
            "connectors": 3,
            "pipelines": 10,
            "incidents_per_month": 50,
            "retention_days": 30,
        },
    },
    ProductTier.INVESTIGATE: {
        "name": "DataForge Investigate",
        "description": "AI-powered root cause analysis and investigation",
        "price_monthly": 499,
        "features": [
            "Everything in Observe",
            "AI-powered investigation",
            "Root cause analysis",
            "GitHub correlation",
            "Blast radius calculation",
            "Incident memory",
            "Change intelligence",
            "Custom dashboards",
        ],
        "limits": {
            "connectors": 10,
            "pipelines": 50,
            "incidents_per_month": 200,
            "retention_days": 90,
        },
    },
    ProductTier.REMEDIATE: {
        "name": "DataForge Remediate",
        "description": "Approval-controlled automated remediation",
        "price_monthly": 1499,
        "features": [
            "Everything in Investigate",
            "Automated repair plans",
            "Approval-controlled execution",
            "Rollback support",
            "Verification engine",
            "Safe execution pipeline",
            "Circuit breaker",
            "Sandbox simulation",
        ],
        "limits": {
            "connectors": 25,
            "pipelines": 200,
            "incidents_per_month": 1000,
            "retention_days": 365,
        },
    },
    ProductTier.AUTONOMOUS: {
        "name": "DataForge Autonomous",
        "description": "Full autonomous reliability with predictive capabilities",
        "price_monthly": 4999,
        "features": [
            "Everything in Remediate",
            "Full autonomous remediation",
            "Predictive reliability",
            "Preventive recommendations",
            "Enterprise SSO (SAML/OIDC)",
            "RBAC",
            "Audit trail",
            "SLA guarantees",
            "Dedicated support",
        ],
        "limits": {
            "connectors": -1,
            "pipelines": -1,
            "incidents_per_month": -1,
            "retention_days": 730,
        },
    },
}


@dataclass
class Subscription:
    """A customer subscription to a product tier."""
    org_id: str
    tier: ProductTier
    started_at: str = ""
    expires_at: str = ""
    is_active: bool = True
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "org_id": self.org_id,
            "tier": self.tier.value,
            "tier_name": TIER_FEATURES[self.tier]["name"],
            "started_at": self.started_at,
            "expires_at": self.expires_at,
            "is_active": self.is_active,
            "features": TIER_FEATURES[self.tier]["features"],
            "limits": TIER_FEATURES[self.tier]["limits"],
        }


class ProductManager:
    """Manages product tiers and subscriptions."""

    def __init__(self):
        self.subscriptions: dict[str, Subscription] = {}

    def get_tier_features(self, tier: ProductTier) -> dict:
        """Get features for a product tier."""
        return TIER_FEATURES.get(tier, {})

    def list_tiers(self) -> list[dict]:
        """List all product tiers."""
        return [
            {
                "tier": tier.value,
                "name": info["name"],
                "description": info["description"],
                "price_monthly": info["price_monthly"],
                "feature_count": len(info["features"]),
            }
            for tier, info in TIER_FEATURES.items()
        ]

    def subscribe(self, org_id: str, tier: ProductTier, started_at: str = "") -> Subscription:
        """Subscribe an organization to a tier."""
        sub = Subscription(org_id=org_id, tier=tier, started_at=started_at, is_active=True)
        self.subscriptions[org_id] = sub
        return sub

    def get_subscription(self, org_id: str) -> Subscription | None:
        """Get an organization's subscription."""
        return self.subscriptions.get(org_id)

    def upgrade(self, org_id: str, new_tier: ProductTier) -> Subscription | None:
        """Upgrade an organization's subscription."""
        sub = self.subscriptions.get(org_id)
        if not sub:
            return None
        sub.tier = new_tier
        return sub

    def has_feature(self, org_id: str, feature_name: str) -> bool:
        """Check if an organization has a specific feature."""
        sub = self.subscriptions.get(org_id)
        if not sub or not sub.is_active:
            return False
        features = TIER_FEATURES.get(sub.tier, {}).get("features", [])
        return any(feature_name.lower() in f.lower() for f in features)

    def check_limit(self, org_id: str, limit_name: str, current_usage: int) -> dict:
        """Check if an organization is within a usage limit."""
        sub = self.subscriptions.get(org_id)
        if not sub:
            return {"within_limit": False, "reason": "No subscription"}

        limits = TIER_FEATURES.get(sub.tier, {}).get("limits", {})
        limit = limits.get(limit_name, 0)

        if limit == -1:
            return {"within_limit": True, "limit": "unlimited", "usage": current_usage}

        return {
            "within_limit": current_usage < limit,
            "limit": limit,
            "usage": current_usage,
            "remaining": max(0, limit - current_usage),
        }
