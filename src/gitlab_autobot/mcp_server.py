from __future__ import annotations

import subprocess
from typing import Any

from mcp.server.fastmcp import FastMCP

from gitlab_autobot.config import load_credentials
from gitlab_autobot.gitlab import GitLabClient

mcp = FastMCP("gitlab-autobot")


def _resolve_client(base_url: str | None, token: str | None) -> GitLabClient:
    creds = load_credentials()
    resolved_base_url = base_url or creds.get("base_url") or "https://gitlab.com"
    resolved_token = token or creds.get("token")
    if not resolved_token:
        raise RuntimeError(
            "GitLab token not found. Provide token or run the CLI to save credentials."
        )
    return GitLabClient(base_url=resolved_base_url, token=resolved_token)


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@mcp.tool()
def create_merge_request(
    project_path: str,
    source_branch: str,
    target_branch: str,
    title: str,
    description: str | None = None,
    assignee: str | None = None,
    reviewers: list[str] | None = None,
    base_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Create a merge request via the GitLab API."""
    client = _resolve_client(base_url, token)
    mr = client.create_merge_request(
        project_path=project_path,
        source_branch=source_branch,
        target_branch=target_branch,
        title=title,
        description=description,
        assignee=assignee,
        reviewers=reviewers,
    )
    return {
        "id": mr.get("id"),
        "iid": mr.get("iid"),
        "title": mr.get("title"),
        "web_url": mr.get("web_url"),
    }


@mcp.tool()
def collect_mr_changes(
    base_ref: str = "origin/main",
    head_ref: str = "HEAD",
    max_commits: int = 50,
) -> dict[str, Any]:
    """Collect git log and diff information for an MR range."""
    log_output = _run_git(
        ["log", f"--max-count={max_commits}", "--oneline", f"{base_ref}..{head_ref}"]
    )
    diff_output = _run_git(["diff", f"{base_ref}...{head_ref}"])
    return {
        "log": log_output,
        "diff": diff_output,
    }


@mcp.tool()
def submit_mr_message(message: str) -> dict[str, Any]:
    """Accept a merge request message supplied by an LLM."""
    return {"message": message.strip()}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
