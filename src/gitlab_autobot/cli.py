from __future__ import annotations

import argparse
import os

from gitlab_autobot.config import load_credentials, save_credentials
from gitlab_autobot.gitlab import AuthError, GitLabClient, GitLabError


def ensure_authenticated(client: GitLabClient) -> dict[str, str]:
    try:
        user = client.get_current_user()
    except AuthError as exc:
        raise exc
    return {
        "username": user.get("username", ""),
        "name": user.get("name", ""),
    }

def parse_args() -> argparse.Namespace:
    creds = load_credentials()
    parser = argparse.ArgumentParser(
        description="Create a GitLab merge request without interactive prompts."
    )
    parser.add_argument(
        "-b",
        "--base-url",
        default=creds.get("base_url"),
        required=creds.get("base_url") is None,
        help="GitLab base URL.",
    )
    parser.add_argument(
        "-p",
        "--project-path",
        required=True,
        help="GitLab project path.",
    )
    parser.add_argument(
        "-s",
        "--source-branch",
        required=True,
        help="Source branch name.",
    )
    parser.add_argument(
        "-t",
        "--target-branch",
        required=True,
        help="Target branch name.",
    )
    parser.add_argument("-a", "--assignee", help="Assignee username.")
    parser.add_argument(
        "-r",
        "--reviewers",
        help="Comma-separated reviewer usernames (e.g. alice,bob).",
    )
    return parser.parse_args()


def parse_reviewers(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [name.strip() for name in raw.split(",") if name.strip()]


def main() -> None:
    args = parse_args()
    token = creds.get("token") or os.getenv("GITLAB_TOKEN")
    if not token:
        raise SystemExit("Missing token. Set GITLAB_TOKEN or save credentials.")

    base_url = args.base_url
    if not base_url:
        raise SystemExit("Missing base URL. Provide --base-url or save credentials.")

    client = GitLabClient(base_url=base_url, token=token)

    try:
        user_info = ensure_authenticated(client)
    except AuthError:
        raise SystemExit("Authentication failed. Provide a valid token.")

    project_path = args.project_path
    source_branch = args.source_branch
    target_branch = args.target_branch
    assignee = args.assignee
    reviewers = parse_reviewers(args.reviewers)

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
        raise SystemExit("Authentication failed. Provide a valid token.")
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
