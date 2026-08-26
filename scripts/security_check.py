"""Security hardening checks for DataForge.

Run with: uv run python scripts/security_check.py

Checks for common security issues in the codebase.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ISSUES = []


def check_file(filepath: Path, checks: list) -> None:
    """Run checks on a file."""
    try:
        content = filepath.read_text()
        for _check_name, check_fn in checks:
            issues = check_fn(filepath, content)
            ISSUES.extend(issues)
    except Exception as e:
        print(f"  Error reading {filepath}: {e}")


def check_no_hardcoded_secrets(filepath: Path, content: str) -> list:
    """Check for hardcoded API keys or secrets."""
    issues = []
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if "gsk_" in line or "sk-" in line or "api_key" in line.lower():
            if "=" in line and ("'" in line or '"' in line):
                if "os.getenv" not in line and "os.environ" not in line and "settings." not in line:
                    issues.append((filepath, i, "Potential hardcoded secret"))
    return issues


def check_no_sql_injection(filepath: Path, content: str) -> list:
    """Check for potential SQL injection vulnerabilities."""
    issues = []
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        if "f\"" in line or "f'" in line:
            if any(kw in line.upper() for kw in ["SELECT", "INSERT", "UPDATE", "DELETE", "DROP"]):
                if "execute" in line or "query" in line:
                    issues.append((filepath, i, "Potential SQL injection via f-string"))
    return issues


def check_no_eval_exec(filepath: Path, content: str) -> list:
    """Check for dangerous eval/exec usage."""
    issues = []
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "eval(" in line and "ast.literal_eval" not in line:
            issues.append((filepath, i, "Use of eval() detected"))
        if "exec(" in line:
            issues.append((filepath, i, "Use of exec() detected"))
    return issues


def check_cors_config(filepath: Path, content: str) -> list:
    """Check for overly permissive CORS."""
    issues = []
    if "allow_origins" in content and '"*"' in content:
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            if "allow_origins" in line and '"*"' in line:
                issues.append((filepath, i, "CORS allows all origins"))
    return issues


CHECKS = [
    ("Hardcoded secrets", check_no_hardcoded_secrets),
    ("SQL injection", check_no_sql_injection),
    ("eval/exec usage", check_no_eval_exec),
    ("CORS configuration", check_cors_config),
]


def main():
    print("=" * 60)
    print("DataForge Security Hardening Check")
    print("=" * 60)

    python_files = list(REPO_ROOT.rglob("*.py"))
    python_files = [f for f in python_files if "node_modules" not in str(f)]

    for filepath in python_files:
        check_file(filepath, CHECKS)

    if not ISSUES:
        print("\n✅ No security issues found!")
        return 0

    print(f"\n⚠️  Found {len(ISSUES)} potential issues:\n")
    for filepath, line, issue in ISSUES:
        rel = filepath.relative_to(REPO_ROOT)
        print(f"  {rel}:{line} — {issue}")

    print(f"\nTotal: {len(ISSUES)} issues")
    return 1


if __name__ == "__main__":
    sys.exit(main())
