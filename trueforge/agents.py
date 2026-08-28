"""TrueForge agent definitions for DataForge."""

# Agent spec for the DataForge investigator
DATAFORGE_INVESTIGATOR_SPEC = {
    "model": {
        "name": "groq/openai/gpt-oss-20b",
        "params": {
            "max_tokens": 4096,
            "temperature": 0.1,
        },
    },
    "instructions": """You are DataForge, an autonomous DataOps incident-response agent.

Your job is to investigate data quality incidents, identify root causes, and coordinate remediation.

## Investigation Steps
1. Understand the incident from the description
2. Inspect database schemas and data quality
3. Check pipeline status and logs
4. Review recent code changes and deployments
5. Run sandbox analysis for statistical verification
6. Correlate evidence to identify root cause
7. Generate a remediation plan
8. Execute remediation after approval
9. Verify the fix worked

## Rules
- Investigation tools are read-only — never modify data during investigation
- Use the sandbox for numerical analysis — don't hardcode results
- High-risk actions (rerun_pipeline, rollback, ticket) require human approval
- Always verify remediation after execution
- Distinguish evidence (facts) from hypotheses (interpretations)

## Evidence Format
Return evidence as a list with source, type, summary, data, confidence, and is_hypothesis fields.
""",
    "mcp_servers": [
        {
            "name": "dataforge-database",
            "enable_tools": ["@all"],
            "require_approval_for_tools": [],
        },
        {
            "name": "dataforge-monitoring",
            "enable_tools": ["@all"],
            "require_approval_for_tools": [],
        },
        {
            "name": "dataforge-github",
            "enable_tools": ["@all"],
            "require_approval_for_tools": [],
        },
        {
            "name": "dataforge-remediation",
            "enable_tools": ["@all"],
            "require_approval_for_tools": [
                "rerun_pipeline",
                "rollback_deployment",
                "create_incident_ticket",
            ],
        },
    ],
    "skills": [
        {"name": "dataops-investigator"},
    ],
    "config": {
        "iteration_limit": 50,
        "sandbox": {
            "enabled": True,
        },
        "dynamic_sub_agents": {
            "enabled": True,
        },
        "ask_user_questions": {
            "enabled": True,
        },
    },
}
