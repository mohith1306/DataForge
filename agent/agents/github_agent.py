"""GitHub Agent — investigates source code changes using real GitHub API."""

import logging

from mcp.github.tools.commits import (
    get_changed_files,
    get_commit,
    get_pull_requests,
    get_recent_commits,
    search_commits,
)

logger = logging.getLogger(__name__)

REPO = "mohith1306/DataForge"

# Default keywords if incident context doesn't match specific categories
DEFAULT_KEYWORDS = ["schema", "region", "deploy", "data", "pipeline"]

# Incident-type → relevant search keywords
INCIDENT_KEYWORDS = {
    "schema_drift": ["schema", "region", "enum", "nullable", "column", "migration", "type"],
    "null_explosion": ["null", "nullable", "schema", "column", "transform"],
    "missing_partition": ["partition", "date", "pipeline", "scheduler", "cron"],
    "duplicate_records": ["dedup", "unique", "merge", "upsert", "key"],
    "pipeline_failure": ["pipeline", "deploy", "release", "config", "error"],
    "volume_anomaly": ["volume", "batch", "streaming", "kafka", "queue"],
    "business_metric_anomaly": ["revenue", "metric", "kpi", "dashboard", "transform"],
}


async def investigate_github(incident_type: str, description: str) -> dict:
    """Investigate GitHub commits and PRs related to the incident."""
    findings = []
    errors = []
    seen_shas: set[str] = set()

    # Select keywords based on incident type
    keywords = INCIDENT_KEYWORDS.get(incident_type, DEFAULT_KEYWORDS)
    # Also extract domain keywords from description
    desc_words = description.lower().split()
    desc_keywords = [w for w in desc_words if len(w) > 4][:3]
    search_keywords = list(dict.fromkeys(keywords + desc_keywords))[:6]

    # Step 1: Get recent commits
    try:
        commits_result = await get_recent_commits(repo=REPO, limit=20)
        commits = commits_result.get("commits", [])
        findings.append({
            "type": "recent_commits",
            "data": {"commits": commits, "count": len(commits)},
            "summary": f"Retrieved {len(commits)} recent commits",
        })

        # Search for suspicious commits using incident-aware keywords
        for kw in search_keywords:
            try:
                search_result = await search_commits(repo=REPO, keyword=kw, limit=5)
                matched = search_result.get("commits", [])
                for c in matched:
                    sha = c.get("sha", "")
                    if sha and sha not in seen_shas:
                        seen_shas.add(sha)
                        findings.append({
                            "type": "suspicious_commit",
                            "data": {"commit": c, "keyword": kw},
                            "summary": (
                                f"Suspicious commit ({kw}): {sha} — "
                                f"{c['message']}"
                            ),
                        })
            except Exception as e:
                errors.append(f"Search commits for '{kw}' failed: {e}")
    except Exception as e:
        errors.append(f"Recent commits fetch failed: {e}")

    # Step 2: Get recent PRs
    try:
        prs_result = await get_pull_requests(repo=REPO, state="all", limit=10)
        prs = prs_result.get("pull_requests", [])
        findings.append({
            "type": "recent_prs",
            "data": {"pull_requests": prs, "count": len(prs)},
            "summary": f"Retrieved {len(prs)} recent PRs",
        })

        # Look for merged PRs that might be related
        merged = [p for p in prs if p.get("merged")]
        for pr in merged[:3]:
            merged_at = pr.get("merged_at", "unknown")
            findings.append({
                "type": "merged_pr",
                "data": {"pr": pr},
                "summary": f"PR #{pr['number']}: {pr['title']} (merged {merged_at})",
            })

            # Get files changed in merged PRs
            try:
                files_result = await get_changed_files(repo=REPO, pr_number=pr["number"])
                files = files_result.get("files", [])
                if files:
                    findings.append({
                        "type": "pr_file_changes",
                        "data": {"pr_number": pr["number"], "files": files},
                        "summary": f"PR #{pr['number']} changed {len(files)} files",
                    })
            except Exception as e:
                errors.append(f"Changed files for PR #{pr['number']} failed: {e}")
    except Exception as e:
        errors.append(f"PRs fetch failed: {e}")

    # Step 3: Get details on most recent suspicious commit
    suspicious = [f for f in findings if f.get("type") == "suspicious_commit"]
    if suspicious:
        top_sha = suspicious[0].get("data", {}).get("commit", {}).get("sha", "")
        if top_sha:
            try:
                detail = await get_commit(repo=REPO, sha=top_sha)
                if not detail.get("error"):
                    findings.append({
                        "type": "commit_detail",
                        "data": detail,
                        "summary": (
                            f"Commit {top_sha}: {detail.get('message', '')} — "
                            f"{len(detail.get('files', []))} files changed"
                        ),
                    })
            except Exception as e:
                errors.append(f"Commit detail for {top_sha} failed: {e}")

    return {
        "agent": "github",
        "findings": findings,
        "errors": errors,
        "summary": f"GitHub investigation: {len(findings)} findings, {len(errors)} errors",
    }
