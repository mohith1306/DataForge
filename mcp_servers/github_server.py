"""GitHub MCP Server — exposes GitHub API tools via MCP protocol.

Run with: python -m mcp_servers.github_server

This server provides GitHub commit, PR, and code change tools.
"""

import os

import httpx
from fastmcp import FastMCP

logger = __import__("logging").getLogger(__name__)

GITHUB_API = "https://api.github.com"
REPO = os.getenv("GITHUB_REPO", "mohith1306/DataForge")

mcp = FastMCP(
    "dataforge-github",
    description="GitHub investigation tools for DataForge",
)


def _get_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@mcp.tool()
async def get_recent_commits(branch: str = "main", limit: int = 20) -> dict:
    """Get recent commits from the repository."""
    url = f"{GITHUB_API}/repos/{REPO}/commits"
    params = {"sha": branch, "per_page": min(limit, 100)}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers=_get_headers())
        if resp.status_code != 200:
            return {"commits": [], "error": resp.text}
        data = resp.json()
        commits = []
        for c in data:
            commits.append({
                "sha": c["sha"][:7],
                "message": c["commit"]["message"].split("\n")[0],
                "author": c["commit"]["author"]["name"],
                "date": c["commit"]["author"]["date"],
            })
        return {"commits": commits, "count": len(commits)}


@mcp.tool()
async def get_commit(sha: str) -> dict:
    """Get detailed commit information."""
    url = f"{GITHUB_API}/repos/{REPO}/commits/{sha}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_get_headers())
        if resp.status_code != 200:
            return {"error": resp.text}
        c = resp.json()
        files = []
        for f in c.get("files", []):
            files.append({
                "filename": f["filename"],
                "status": f["status"],
                "additions": f["additions"],
                "deletions": f["deletions"],
                "patch": f.get("patch", "")[:500],
            })
        return {
            "sha": c["sha"][:7],
            "message": c["commit"]["message"].split("\n")[0],
            "author": c["commit"]["author"]["name"],
            "date": c["commit"]["author"]["date"],
            "files": files,
            "stats": c.get("stats", {}),
        }


@mcp.tool()
async def get_pull_requests(state: str = "all", limit: int = 20) -> dict:
    """Get pull requests."""
    url = f"{GITHUB_API}/repos/{REPO}/pulls"
    params = {"state": state, "per_page": min(limit, 100), "sort": "updated"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers=_get_headers())
        if resp.status_code != 200:
            return {"pull_requests": [], "error": resp.text}
        data = resp.json()
        prs = []
        for pr in data:
            prs.append({
                "number": pr["number"],
                "title": pr["title"],
                "state": pr["state"],
                "merged": pr.get("merged_at") is not None,
                "user": pr["user"]["login"],
                "created_at": pr["created_at"],
                "merged_at": pr.get("merged_at"),
                "head_sha": pr["head"]["sha"][:7],
            })
        return {"pull_requests": prs, "count": len(prs)}


@mcp.tool()
async def get_changed_files(pr_number: int) -> dict:
    """Get files changed in a pull request."""
    url = f"{GITHUB_API}/repos/{REPO}/pulls/{pr_number}/files"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params={"per_page": 100}, headers=_get_headers())
        if resp.status_code != 200:
            return {"files": [], "error": resp.text}
        data = resp.json()
        files = []
        for f in data:
            files.append({
                "filename": f["filename"],
                "status": f["status"],
                "additions": f["additions"],
                "deletions": f["deletions"],
                "changes": f["changes"],
            })
        return {"files": files, "count": len(files), "pr_number": pr_number}


@mcp.tool()
async def search_commits(keyword: str, limit: int = 10) -> dict:
    """Search commits by message keyword."""
    url = f"{GITHUB_API}/repos/{REPO}/commits"
    params = {"per_page": 100}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers=_get_headers())
        if resp.status_code != 200:
            return {"commits": [], "error": resp.text}
        data = resp.json()
        matched = []
        for c in data:
            msg = c["commit"]["message"].lower()
            if keyword.lower() in msg:
                matched.append({
                    "sha": c["sha"][:7],
                    "message": c["commit"]["message"].split("\n")[0],
                    "author": c["commit"]["author"]["name"],
                    "date": c["commit"]["author"]["date"],
                })
                if len(matched) >= limit:
                    break
        return {"commits": matched, "count": len(matched), "keyword": keyword}


if __name__ == "__main__":
    mcp.run(transport="stdio")
