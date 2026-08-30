"""TrueForge agent definitions for DataForge."""


def get_investigator_spec(model_name: str = "google/gemini-3.6-flash") -> dict:
    """Return the DataForge investigator agent spec."""
    return {
        "model": {
            "name": model_name,
            "params": {
                "max_tokens": 8192,
                "temperature": 0.1,
            },
        },
        "instructions": """You are DataForge, an autonomous DataOps incident-response agent.

## TOOLS
You have exactly ONE tool: call_tool(tool_name, mcp_server, input)

## STRICT PROTOCOL - FOLLOW EXACTLY

FIRST: Call call_tool(tool_name="get_pipeline_status", mcp_server="dataforge-database", input={})

SECOND: From the results, find the failed pipeline ID. Then call call_tool(tool_name="get_pipeline_logs", mcp_server="dataforge-database", input={"pipeline_id": "THE_FAILED_PIPELINE_ID"})

THIRD: Call call_tool(tool_name="get_recent_commits", mcp_server="dataforge-database", input={})

FOURTH: You now have ALL the information you need. Write your final response immediately. Do NOT make any more tool calls.

## YOUR FINAL RESPONSE MUST BE EXACTLY THIS FORMAT:

ROOT CAUSE: [describe the root cause]
CONFIDENCE: [high/medium/low]
EVIDENCE: [list the evidence you found]
REMEDIATION PLAN: [describe how to fix it]

## ABSOLUTELY FORBIDDEN
- Do NOT call get_pipeline_status more than 1 time
- Do NOT call get_pipeline_logs more than 1 time  
- Do NOT call get_recent_commits more than 1 time
- Do NOT call list_tables, describe_table, or execute_select
- Do NOT make any tool call after the third call
- After 3 tool calls, you MUST write the ROOT CAUSE / CONFIDENCE / EVIDENCE / REMEDIATION PLAN response""",
        "mcp_servers": [
            {
                "name": "dataforge-database",
                "enable_tools": ["@all"],
                "require_approval_for_tools": [],
            },
        ],
        "config": {
            "iteration_limit": 10,
            "sandbox": {
                "enabled": False,
            },
            "dynamic_sub_agents": {
                "enabled": False,
            },
            "context_management": {
                "compaction": {
                    "enabled": True,
                    "compaction_threshold_tokens": 3000,
                },
                "large_tool_response": {
                    "enabled": True,
                    "max_tool_response_tokens": 1000,
                },
            },
            "ask_user_questions": {
                "enabled": False,
            },
        },
    }
