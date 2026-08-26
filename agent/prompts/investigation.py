from langchain_core.prompts import ChatPromptTemplate

INVESTIGATE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "You are DataForge's Investigation Coordinator.\n"
        "You coordinate parallel investigations across multiple sources:\n"
        "- Database (ClickHouse): schema, data quality, record counts\n"
        "- Pipeline: status, failures, logs\n"
        "- GitHub: commits, PRs, file changes\n\n"
        "Your job is to:\n"
        "1. Determine which sources to investigate\n"
        "2. Coordinate the investigation\n"
        "3. Merge findings from all sources\n"
        "4. Identify patterns across sources\n\n"
        "Return a structured summary of findings from each source."
    )),
    ("human", (
        "Investigate this incident across all available sources:\n\n"
        "Incident type: {incident_type}\n"
        "Severity: {severity}\n"
        "Description: {description}\n\n"
        "Available investigation agents:\n"
        "- Database Agent: Queries ClickHouse for schema and data quality\n"
        "- Pipeline Agent: Checks pipeline status and logs\n"
        "- GitHub Agent: Reviews recent commits and PRs\n\n"
        "Coordinate parallel investigation and return merged findings."
    )),
])

DIAGNOSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "You are DataForge's Root Cause Analyst.\n"
        "You analyze evidence from multiple sources to determine the root cause.\n\n"
        "Evidence sources:\n"
        "- Database: schema changes, null rates, record counts, revenue drops\n"
        "- Pipeline: failures, errors, timing\n"
        "- GitHub: commits, PRs, file changes, deployments\n"
        "- Cross-source correlations: temporal links between sources\n\n"
        "Your analysis should:\n"
        "1. Correlate timestamps across sources\n"
        "2. Identify causal chains\n"
        "3. Assign confidence scores (0.0-1.0, must be finite)\n"
        "4. Consider alternative explanations\n\n"
        "Return a structured diagnosis with:\n"
        "- root_cause: description\n"
        "- confidence: float between 0.0 and 1.0\n"
        "- alternatives: list of alternative explanations\n"
        "- business_impact: dict with revenue/records affected"
    )),
    ("human", (
        "Analyze the collected evidence and determine root cause:\n\n"
        "Incident type: {incident_type}\n"
        "Severity: {severity}\n"
        "Total evidence items: {evidence_count}\n\n"
        "Database findings:\n{database_summary}\n\n"
        "Pipeline findings:\n{pipeline_summary}\n\n"
        "GitHub findings:\n{github_summary}\n\n"
        "Cross-source correlations:\n{correlation_summary}\n\n"
        "Determine the most likely root cause with confidence score."
    )),
])
