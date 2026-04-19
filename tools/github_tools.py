"""GitHub API integration tool."""

import logging
import os

import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubTools:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self._session = requests.Session()
        if self.token:
            self._session.headers["Authorization"] = f"token {self.token}"
        self._session.headers["Accept"] = "application/vnd.github.v3+json"
        self._session.headers["User-Agent"] = "AI-Agent/1.0"

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        r = self._session.get(f"{GITHUB_API}{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> dict:
        r = self._session.post(f"{GITHUB_API}{path}", json=body, timeout=15)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, body: dict) -> dict:
        r = self._session.patch(f"{GITHUB_API}{path}", json=body, timeout=15)
        r.raise_for_status()
        return r.json()

    # ── Repos ────────────────────────────────────────────────────────────────

    def get_repo(self, owner: str, repo: str) -> str:
        data = self._get(f"/repos/{owner}/{repo}")
        return (
            f"**{data['full_name']}** ⭐{data['stargazers_count']} 🍴{data['forks_count']}\n"
            f"{data.get('description', '')}\n"
            f"Language: {data.get('language', 'N/A')} | Open issues: {data['open_issues_count']}\n"
            f"URL: {data['html_url']}"
        )

    def list_repos(self, username: str) -> str:
        data = self._get(f"/users/{username}/repos", {"per_page": 20, "sort": "updated"})
        return "\n".join(f"- {r['full_name']} ({r.get('language','?')}) ⭐{r['stargazers_count']}" for r in data)

    # ── Files ────────────────────────────────────────────────────────────────

    def get_file(self, owner: str, repo: str, path: str, ref: str = "HEAD") -> str:
        import base64
        data = self._get(f"/repos/{owner}/{repo}/contents/{path}", {"ref": ref})
        if isinstance(data, list):
            return "\n".join(f"{'📁' if i['type']=='dir' else '📄'} {i['name']}" for i in data)
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return f"```\n{content[:6000]}\n```"

    def list_files(self, owner: str, repo: str, path: str = "", ref: str = "HEAD") -> str:
        data = self._get(f"/repos/{owner}/{repo}/contents/{path}", {"ref": ref})
        if isinstance(data, list):
            return "\n".join(f"{'📁' if i['type']=='dir' else '📄'} {i['path']}" for i in data)
        return data.get("name", "")

    # ── Issues ───────────────────────────────────────────────────────────────

    def list_issues(self, owner: str, repo: str, state: str = "open") -> str:
        data = self._get(f"/repos/{owner}/{repo}/issues", {"state": state, "per_page": 20})
        if not data:
            return f"No {state} issues."
        return "\n".join(f"#{i['number']} {i['title']} [{', '.join(l['name'] for l in i['labels'])}]" for i in data if "pull_request" not in i)

    def create_issue(self, owner: str, repo: str, title: str, body: str = "", labels: list[str] | None = None) -> str:
        payload: dict = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        data = self._post(f"/repos/{owner}/{repo}/issues", payload)
        return f"Created issue #{data['number']}: {data['html_url']}"

    def comment_on_issue(self, owner: str, repo: str, number: int, comment: str) -> str:
        data = self._post(f"/repos/{owner}/{repo}/issues/{number}/comments", {"body": comment})
        return f"Commented: {data['html_url']}"

    # ── Pull Requests ─────────────────────────────────────────────────────────

    def list_prs(self, owner: str, repo: str, state: str = "open") -> str:
        data = self._get(f"/repos/{owner}/{repo}/pulls", {"state": state, "per_page": 20})
        if not data:
            return f"No {state} PRs."
        return "\n".join(f"#{p['number']} {p['title']} ({p['head']['ref']} → {p['base']['ref']})" for p in data)

    def create_pr(self, owner: str, repo: str, title: str, head: str, base: str, body: str = "") -> str:
        data = self._post(f"/repos/{owner}/{repo}/pulls", {"title": title, "head": head, "base": base, "body": body})
        return f"Created PR #{data['number']}: {data['html_url']}"

    # ── Search ────────────────────────────────────────────────────────────────

    def search_code(self, query: str, repo: str | None = None) -> str:
        q = f"{query} repo:{repo}" if repo else query
        data = self._get("/search/code", {"q": q, "per_page": 10})
        items = data.get("items", [])
        if not items:
            return "No results found."
        return "\n".join(f"- {i['repository']['full_name']}/{i['path']}" for i in items)

    # ── Dispatch (used by orchestrator) ──────────────────────────────────────

    def dispatch(self, action: str, **kwargs) -> str:
        actions = {
            "get_repo": self.get_repo,
            "list_repos": self.list_repos,
            "get_file": self.get_file,
            "list_files": self.list_files,
            "list_issues": self.list_issues,
            "create_issue": self.create_issue,
            "comment_on_issue": self.comment_on_issue,
            "list_prs": self.list_prs,
            "create_pr": self.create_pr,
            "search_code": self.search_code,
        }
        fn = actions.get(action)
        if not fn:
            return f"Unknown GitHub action: {action}"
        try:
            return fn(**kwargs)
        except Exception as exc:
            return f"GitHub error ({action}): {exc}"
