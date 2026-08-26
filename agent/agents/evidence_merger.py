"""Evidence Merger — combines findings from all investigation agents into unified evidence."""

from typing import Any


def merge_evidence(
    database_findings: list[dict[str, Any]],
    pipeline_findings: list[dict[str, Any]],
    github_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge findings from all agents into a unified evidence list.

    Each evidence item has:
    - source: database, pipeline, github
    - type: schema, metric, log, commit, etc.
    - content: the raw finding data
    - summary: human-readable summary
    - relevance_score: 0.0-1.0 indicating relevance to incident
    """
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

    # Sort by relevance (highest first)
    evidence.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    return evidence


def _score_database_relevance(finding: dict) -> float:
    """Score how relevant a database finding is to an incident."""
    score = 0.5  # base
    ftype = finding.get("type", "")

    if ftype == "column_profile":
        # High relevance if null rate is elevated
        data = finding.get("data", {})
        null_rate = data.get("null_rate", 0)
        if null_rate > 0.1:
            score += 0.3
        elif null_rate > 0.05:
            score += 0.15

    elif ftype == "aggregation":
        # Check if region distribution looks abnormal
        score += 0.2

    elif ftype == "revenue_trend":
        # Revenue data is highly relevant
        score += 0.25

    elif ftype == "revenue_summary":
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

    elif ftype == "pipeline_status":
        data = finding.get("data", {})
        pipeline = data.get("pipeline", {})
        if pipeline.get("status") == "FAILED":
            score += 0.3

    elif ftype == "pipeline_logs":
        score += 0.25

    elif ftype == "revenue_metrics":
        score += 0.2

    return min(score, 1.0)


def _score_github_relevance(finding: dict) -> float:
    """Score how relevant a github finding is to an incident."""
    score = 0.5
    ftype = finding.get("type", "")

    if ftype == "suspicious_commit":
        score += 0.35

    elif ftype == "pull_request":
        data = finding.get("data", {})
        pr = data.get("pr", {})
        if pr.get("status") == "merged":
            score += 0.25

    elif ftype == "file_changes":
        score += 0.2

    elif ftype == "schema_commits":
        data = finding.get("data", {})
        if data.get("count", 0) > 0:
            score += 0.25

    return min(score, 1.0)
