"""GitHub MCP tools — query GitHub API for commits, PRs, and file changes."""

import os

import httpx

GITHUB_API = "https://api.github.com"
REPO = "mohith1306/DataForge"


def _get_headers() -> dict:
    """Get GitHub API headers with optional auth token."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def get_recent_commits(
    repo: str = REPO, branch: str = "main", limit: int = 20
) -> dict:
    """Get recent commits from a repository."""
    url = f"{GITHUB_API}/repos/{repo}/commits"
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


async def get_commit(repo: str = REPO, sha: str = "") -> dict:
    """Get detailed commit information."""
    url = f"{GITHUB_API}/repos/{repo}/commits/{sha}"
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


async def get_pull_requests(
    repo: str = REPO, state: str = "all", limit: int = 20
) -> dict:
    """Get pull requests."""
    url = f"{GITHUB_API}/repos/{repo}/pulls"
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


async def get_changed_files(
    repo: str = REPO, pr_number: int = 0, max_pages: int = 3
) -> dict:
    """Get files changed in a pull request, with pagination."""
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/files"
    all_files = []
    page = 1
    async with httpx.AsyncClient(timeout=30) as client:
        while page <= max_pages:
            resp = await client.get(
                url, params={"per_page": 100, "page": page}, headers=_get_headers()
            )
            if resp.status_code != 200:
                if not all_files:
                    return {"files": [], "error": resp.text}
                break
            data = resp.json()
            if not data:
                break
            for f in data:
                all_files.append({
                    "filename": f["filename"],
                    "status": f["status"],
                    "additions": f["additions"],
                    "deletions": f["deletions"],
                    "changes": f["changes"],
                })
            if len(data) < 100:
                break
            page += 1
    return {"files": all_files, "count": len(all_files), "pr_number": pr_number}


async def search_commits(
    repo: str = REPO, keyword: str = "", limit: int = 10
) -> dict:
    """Search commits by message keyword."""
    url = f"{GITHUB_API}/repos/{repo}/commits"
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
