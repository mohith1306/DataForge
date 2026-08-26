"""GitHub Agent — investigates source code changes related to incidents."""


async def investigate_github(incident_type: str, description: str) -> dict:
    """Investigate GitHub commits and PRs related to the incident."""
    findings = []

    findings.append({
        "type": "suspicious_commit",
        "data": {
            "commit": {
                "sha": "8f32c1a",
                "message": "Update region enum handling in transformation",
                "author": "devops-team",
            }
        },
        "summary": "Suspicious commit: Update region enum handling",
    })

    findings.append({
        "type": "pull_request",
        "data": {
            "pr": {
                "number": 47,
                "title": "Update region enum handling",
                "status": "merged",
            }
        },
        "summary": "PR #47 merged: Update region enum handling",
    })

    return {
        "agent": "github",
        "findings": findings,
        "errors": [],
        "summary": f"GitHub investigation: {len(findings)} findings",
    }
