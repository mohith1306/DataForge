"""GitHub MCP tools — query GitHub API for commits, PRs, and file changes."""

import httpx

GITHUB_API = "https://api.github.com"
REPO = "mohith1306/DataForge"


async def get_recent_commits(
    repo: str = REPO, branch: str = "main", limit: int = 20
) -> dict:
    """Get recent commits from a repository."""
    url = f"{GITHUB_API}/repos/{repo}/commits"
    params = {"sha": branch, "per_page": limit}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
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
        resp = await client.get(url)
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
    params = {"state": state, "per_page": limit, "sort": "updated"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
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


async def get_changed_files(repo: str = REPO, pr_number: int = 0) -> dict:
    """Get files changed in a pull request."""
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/files"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
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


async def search_commits(
    repo: str = REPO, keyword: str = "", limit: int = 10
) -> dict:
    """Search commits by message keyword."""
    url = f"{GITHUB_API}/repos/{repo}/commits"
    params = {"per_page": 100}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
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
