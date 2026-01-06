from __future__ import annotations

import subprocess
from typing import Annotated, Any

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
    project_path: Annotated[str, "GitLab project path (e.g. group/project)."],
    source_branch: Annotated[str, "Source branch name for the merge request."],
    target_branch: Annotated[str, "Target branch name for the merge request."],
    title: Annotated[str, "Title for the merge request."],
    description: Annotated[
        str | None, "Optional merge request description in Markdown."
    ] = None,
    assignee: Annotated[
        str | None,
        "Optional GitLab username to assign the merge request to.",
    ] = None,
    reviewers: Annotated[
        list[str] | None,
        "Optional list of GitLab usernames to add as reviewers.",
    ] = None,
    base_url: Annotated[
        str | None, "Optional GitLab base URL override (defaults to saved credentials)."
    ] = None,
    token: Annotated[
        str | None,
        "Optional GitLab access token override (defaults to saved credentials).",
    ] = None,
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
    base_ref: Annotated[
        str, "Git ref for the merge request base (defaults to origin/main)."
    ] = "origin/main",
    head_ref: Annotated[
        str, "Git ref for the merge request head (defaults to HEAD)."
    ] = "HEAD",
    max_commits: Annotated[
        int, "Maximum number of commits to return from git log."
    ] = 50,
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
def submit_mr_message(
    message: Annotated[str, "Prepared merge request message body."]
) -> dict[str, Any]:
    """Accept a merge request message supplied by an LLM."""
    return {"message": message.strip()}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
