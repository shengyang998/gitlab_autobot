from __future__ import annotations

import getpass

from gitlab_autobot.config import load_credentials, save_credentials
from gitlab_autobot.gitlab import AuthError, GitLabClient, GitLabError


def prompt(text: str, default: str | None = None) -> str:
    if default:
        value = input(f"{text} [{default}]: ").strip()
        return value or default
    return input(f"{text}: ").strip()


def prompt_token() -> str:
    return getpass.getpass("GitLab personal access token: ").strip()


def ensure_authenticated(client: GitLabClient) -> dict[str, str]:
    try:
        user = client.get_current_user()
    except AuthError as exc:
        raise exc
    return {
        "username": user.get("username", ""),
        "name": user.get("name", ""),
    }


def main() -> None:
    creds = load_credentials()
    base_url = prompt("GitLab base URL", creds.get("base_url", "https://gitlab.com"))
    token = creds.get("token")
    if not token:
        token = prompt_token()

    client = GitLabClient(base_url=base_url, token=token)

    try:
        user_info = ensure_authenticated(client)
    except AuthError:
        print("Authentication failed. Please provide a new token.")
        token = prompt_token()
        client = GitLabClient(base_url=base_url, token=token)
        user_info = ensure_authenticated(client)

    project_path = prompt("GitLab project path (group/project)")
    source_branch = prompt("Source branch")
    target_branch = prompt("Target branch")
    assignee = prompt("Assignee username (optional)", "").strip() or None
    reviewers_raw = prompt("Reviewer usernames (comma-separated, optional)", "").strip()
    reviewers = [name.strip() for name in reviewers_raw.split(",") if name.strip()]

    title = f"Merge {source_branch} into {target_branch}"

    try:
        mr = client.create_merge_request(
            project_path=project_path,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            assignee=assignee,
            reviewers=reviewers,
        )
    except AuthError:
        print("Authentication failed. Please provide a new token.")
        token = prompt_token()
        client = GitLabClient(base_url=base_url, token=token)
        mr = client.create_merge_request(
            project_path=project_path,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            assignee=assignee,
            reviewers=reviewers,
        )
    except GitLabError as exc:
        raise SystemExit(str(exc))

    save_credentials(
        {
            "base_url": base_url,
            "token": token,
            "user": user_info,
        }
    )

    print("Merge request created:")
    print(f"  Title: {mr.get('title')}")
    print(f"  URL: {mr.get('web_url')}")


if __name__ == "__main__":
    main()
