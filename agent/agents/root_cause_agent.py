"""Root Cause Agent — LLM-powered analysis to determine root cause from evidence."""

import json
import logging
import math

from agent.models.llm import get_llm
from agent.prompts.investigation import DIAGNOSE_PROMPT

logger = logging.getLogger(__name__)


def _validate_confidence(value: float) -> float:
    """Validate and clamp confidence to [0.0, 1.0]."""
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return 0.5
    return max(0.0, min(1.0, float(value)))


async def analyze_root_cause(state: dict) -> dict:
    """Use LLM to analyze evidence and determine root cause with confidence."""
    llm = get_llm()

    incident_type = state.get("incident_type", "unknown")
    severity = state.get("severity", "medium")
    evidence = state.get("evidence", [])

    database_findings = [e for e in evidence if e.get("source") == "database"]
    pipeline_findings = [e for e in evidence if e.get("source") == "pipeline"]
    github_findings = [e for e in evidence if e.get("source") == "github"]
    correlations = [e for e in evidence if e.get("source") == "correlation"]

    db_summary = "\n".join(
        f"- [{e['type']}] {e['summary']}" for e in database_findings[:10]
    ) or "No database findings"
    pipeline_summary = "\n".join(
        f"- [{e['type']}] {e['summary']}" for e in pipeline_findings[:10]
    ) or "No pipeline findings"
    github_summary = "\n".join(
        f"- [{e['type']}] {e['summary']}" for e in github_findings[:10]
    ) or "No github findings"
    corr_summary = "\n".join(
        f"- [{e['type']}] {e['summary']}" for e in correlations[:5]
    ) or "No cross-source correlations"

    # Include sandbox analysis results
    analysis = state.get("analysis_results", {})
    sandbox_summary = "No sandbox analysis"
    if analysis:
        output = analysis.get("code_output", "")
        result = analysis.get("result")
        error = analysis.get("error")
        if error:
            sandbox_summary = f"Sandbox analysis error: {error}"
        elif result:
            sandbox_summary = f"Sandbox result: {json.dumps(result, default=str)[:500]}"
        elif output:
            sandbox_summary = f"Sandbox output: {output[:500]}"

    try:
        chain = DIAGNOSE_PROMPT | llm
        response = await chain.ainvoke({
            "incident_type": incident_type,
            "severity": severity,
            "evidence_count": len(evidence),
            "database_summary": db_summary,
            "pipeline_summary": pipeline_summary,
            "github_summary": github_summary,
            "sandbox_summary": sandbox_summary,
            "correlation_summary": corr_summary,
        })

        content = response.content if hasattr(response, "content") else str(response)

        # Try to parse JSON from response
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(content[start:end])
            else:
                parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {
                "root_cause": content[:500],
                "confidence": 0.6,
                "alternatives": [],
                "business_impact": {},
            }

        confidence = _validate_confidence(parsed.get("confidence", 0.6))

        root_cause = {
            "description": parsed.get("root_cause", parsed.get("description", "Unknown")),
            "confidence": confidence,
            "alternatives": parsed.get("alternatives", []),
            "business_impact": parsed.get("business_impact", {}),
            "evidence_sources": list(set(e.get("source", "") for e in evidence)),
            "correlation_count": len(correlations),
        }

        return {
            "status": "diagnosing",
            "root_cause": root_cause,
            "confidence": confidence,
            "events": state.get("events", []) + [
                {
                    "type": "diagnosis.created",
                    "agent": "root_cause_analyst",
                    "message": (
                        f"Root cause: {root_cause['description'][:100]} "
                        f"(confidence: {confidence:.0%})"
                    ),
                }
            ],
        }

    except Exception as e:
        logger.error(f"Root cause analysis failed: {e}")
        root_cause = _heuristic_analysis(state)
        return {
            "status": "diagnosing",
            "root_cause": root_cause,
            "confidence": root_cause["confidence"],
            "events": state.get("events", []) + [
                {
                    "type": "diagnosis.created",
                    "agent": "root_cause_analyst",
                    "message": f"Heuristic root cause: {root_cause['description'][:100]}",
                }
            ],
        }


def _heuristic_analysis(state: dict) -> dict:
    """Fallback heuristic analysis when LLM fails."""
    evidence = state.get("evidence", [])
    incident_type = state.get("incident_type", "unknown")

    sources = set(e.get("source", "") for e in evidence)
    has_correlation = any(e.get("source") == "correlation" for e in evidence)

    confidence = 0.5
    if len(evidence) > 5:
        confidence += 0.1
    if has_correlation:
        confidence += 0.15
    if "database" in sources and "pipeline" in sources:
        confidence += 0.1
    if "github" in sources:
        confidence += 0.05

    confidence = _validate_confidence(confidence)

    description = f"Automated analysis of {incident_type} incident"
    if has_correlation:
        description += " with cross-source correlation"
    description += f". {len(evidence)} evidence items analyzed."

    return {
        "description": description,
        "confidence": confidence,
        "alternatives": ["Manual investigation recommended"],
        "business_impact": {},
        "evidence_sources": list(sources),
    }
