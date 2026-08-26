"""Evidence Merger — combines findings with cross-source correlation."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def merge_evidence(
    database_findings: list[dict[str, Any]],
    pipeline_findings: list[dict[str, Any]],
    github_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge findings from all agents into a unified evidence list with correlation."""
    evidence = []

    # Process database findings
    for f in database_findings:
        if f.get("type") == "error":
            continue
        relevance = _score_database_relevance(f)
        evidence.append({
            "source": "database",
            "type": f.get("type", "unknown"),
            "content": f.get("data", {}),
            "summary": f.get("summary", ""),
            "relevance_score": relevance,
        })

    # Process pipeline findings
    for f in pipeline_findings:
        if f.get("type") == "error":
            continue
        relevance = _score_pipeline_relevance(f)
        evidence.append({
            "source": "pipeline",
            "type": f.get("type", "unknown"),
            "content": f.get("data", {}),
            "summary": f.get("summary", ""),
            "relevance_score": relevance,
        })

    # Process github findings
    for f in github_findings:
        if f.get("type") == "error":
            continue
        relevance = _score_github_relevance(f)
        evidence.append({
            "source": "github",
            "type": f.get("type", "unknown"),
            "content": f.get("data", {}),
            "summary": f.get("summary", ""),
            "relevance_score": relevance,
        })

    # Cross-source correlation
    correlations = _find_correlations(evidence)
    for corr in correlations:
        evidence.append({
            "source": "correlation",
            "type": "cross_source_link",
            "content": corr,
            "summary": corr["summary"],
            "relevance_score": 0.9,
        })

    # Sort by relevance (highest first)
    evidence.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    return evidence


def _find_correlations(evidence: list[dict]) -> list[dict]:
    """Find cross-source correlations with timestamp/entity validation."""
    from datetime import datetime

    correlations = []

    db_items = [e for e in evidence if e["source"] == "database"]
    pipeline_items = [e for e in evidence if e["source"] == "pipeline"]
    github_items = [e for e in evidence if e["source"] == "github"]

    # Extract timestamps from evidence for temporal comparison
    def _extract_timestamps(items: list[dict]) -> list[datetime]:
        timestamps = []
        for item in items:
            content = item.get("content", {})
            for key in ("started_at", "date", "created_at", "merged_at"):
                val = content.get(key)
                if val:
                    try:
                        if isinstance(val, str):
                            ts = datetime.fromisoformat(val.replace("Z", "+00:00"))
                        else:
                            ts = datetime.fromtimestamp(float(val))
                        timestamps.append(ts)
                    except (ValueError, TypeError, OSError):
                        pass
        return timestamps

    def _temporal_overlap(ts_list_a: list[datetime], ts_list_b: list[datetime],
                          window_hours: int = 48) -> bool:
        """Check if any timestamps from A are within window_hours of any in B."""
        if not ts_list_a or not ts_list_b:
            return False
        for a in ts_list_a:
            for b in ts_list_b:
                if abs((a - b).total_seconds()) < window_hours * 3600:
                    return True
        return False

    failed_pipelines = [
        e for e in pipeline_items
        if e["type"] in ("failed_jobs", "failed_job_detail", "pipeline_overview")
    ]
    schema_issues = [
        e for e in db_items
        if e["type"] in ("column_profile", "aggregation", "revenue_trend")
    ]
    suspicious_commits = [
        e for e in github_items if e["type"] in ("suspicious_commit", "commit_detail")
    ]
    merged_prs = [
        e for e in github_items
        if e["type"] in ("merged_pr", "pr_file_changes")
    ]

    # Correlation 1: Pipeline failures + schema/data anomalies (require temporal proximity)
    pipeline_ts = _extract_timestamps(failed_pipelines)
    db_ts = _extract_timestamps(schema_issues)
    if failed_pipelines and schema_issues and _temporal_overlap(pipeline_ts, db_ts):
        correlations.append({
            "type": "pipeline_data_correlation",
            "sources": ["pipeline", "database"],
            "summary": (
                f"Pipeline failures ({len(failed_pipelines)} items) coincide with "
                f"data anomalies ({len(schema_issues)} items) within 48h window"
            ),
            "details": {
                "pipeline_findings": [e["summary"] for e in failed_pipelines[:3]],
                "data_findings": [e["summary"] for e in schema_issues[:3]],
            },
        })

    # Correlation 2: Suspicious commits + pipeline failures (require temporal proximity)
    github_ts = _extract_timestamps(suspicious_commits)
    if suspicious_commits and failed_pipelines and _temporal_overlap(github_ts, pipeline_ts):
        correlations.append({
            "type": "commit_pipeline_correlation",
            "sources": ["github", "pipeline"],
            "summary": (
                f"Suspicious commits ({len(suspicious_commits)}) temporally close to "
                f"pipeline failures ({len(failed_pipelines)} failed)"
            ),
            "details": {
                "commits": [e["summary"] for e in suspicious_commits[:3]],
                "failures": [e["summary"] for e in failed_pipelines[:3]],
            },
        })

    # Correlation 3: Merged PRs + data changes (require temporal proximity)
    pr_ts = _extract_timestamps(merged_prs)
    if merged_prs and schema_issues and _temporal_overlap(pr_ts, db_ts):
        correlations.append({
            "type": "pr_data_correlation",
            "sources": ["github", "database"],
            "summary": (
                f"Merged PRs ({len(merged_prs)}) temporally close to "
                f"data quality changes ({len(schema_issues)} findings)"
            ),
            "details": {
                "prs": [e["summary"] for e in merged_prs[:3]],
                "data_changes": [e["summary"] for e in schema_issues[:3]],
            },
        })

    # Correlation 4: Three-way chain — require ALL pairwise temporal overlaps
    if (suspicious_commits and failed_pipelines and schema_issues
            and _temporal_overlap(github_ts, pipeline_ts)
            and _temporal_overlap(pipeline_ts, db_ts)):
        correlations.append({
            "type": "full_causal_chain",
            "sources": ["github", "pipeline", "database"],
            "summary": (
                "Strong causal chain with temporal evidence: "
                "commit → pipeline failure → data impact"
            ),
            "details": {
                "commit": suspicious_commits[0]["summary"],
                "pipeline_failure": failed_pipelines[0]["summary"],
                "data_impact": schema_issues[0]["summary"],
            },
        })

    return correlations


def _score_database_relevance(finding: dict) -> float:
    """Score how relevant a database finding is to an incident."""
    score = 0.5
    ftype = finding.get("type", "")

    if ftype == "column_profile":
        data = finding.get("data", {})
        null_rate = data.get("null_rate", 0)
        if null_rate > 0.1:
            score += 0.3
        elif null_rate > 0.05:
            score += 0.15
    elif ftype == "aggregation":
        score += 0.2
    elif ftype == "revenue_trend":
        score += 0.25
    elif ftype == "revenue_summary":
        score += 0.2
    elif ftype == "partition_gaps":
        score += 0.3
    elif ftype == "duplication_rate":
        data = finding.get("data", {})
        if data.get("duplicate_rate", 0) > 0.01:
            score += 0.2

    return min(score, 1.0)


def _score_pipeline_relevance(finding: dict) -> float:
    """Score how relevant a pipeline finding is to an incident."""
    score = 0.5
    ftype = finding.get("type", "")

    if ftype == "failed_jobs":
        data = finding.get("data", {})
        count = data.get("count", 0)
        if count > 0:
            score += 0.3
        if count > 3:
            score += 0.1
    elif ftype == "failed_job_detail":
        score += 0.35
    elif ftype == "pipeline_overview":
        data = finding.get("data", {})
        if data.get("failed_count", 0) > 0:
            score += 0.25
    elif ftype == "pipeline_logs":
        score += 0.25
    elif ftype == "pipeline_metrics":
        score += 0.2

    return min(score, 1.0)


def _score_github_relevance(finding: dict) -> float:
    """Score how relevant a github finding is to an incident."""
    score = 0.5
    ftype = finding.get("type", "")

    if ftype == "suspicious_commit":
        score += 0.35
    elif ftype == "commit_detail":
        score += 0.3
    elif ftype == "merged_pr":
        data = finding.get("data", {})
        pr = data.get("pr", {})
        if pr.get("merged"):
            score += 0.25
    elif ftype == "pr_file_changes":
        score += 0.2
    elif ftype == "recent_commits":
        score += 0.1

    return min(score, 1.0)
