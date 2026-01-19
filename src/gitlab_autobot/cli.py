from __future__ import annotations

import argparse
import os
import re
import subprocess

from gitlab_autobot.config import load_credentials, save_credentials
from gitlab_autobot.gitlab import AuthError, GitLabClient, GitLabError


def get_project_path_from_git() -> str | None:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip()
        match = re.search(r"(?:git@|https://)[^:/]+[:/](.+?)(?:\.git)?$", url)
        if match:
            return match.group(1)
        return None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_current_branch() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


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
    saved_base_url = creds.get("base_url")
    epilog = """
    Saved credentials will be used for authentication if available.
    The GitLab token can also be provided via the GITLAB_TOKEN environment variable.
    """
    parser = argparse.ArgumentParser(
        description="Create a GitLab merge request without interactive prompts.",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-b",
        "--base-url",
        default=saved_base_url,
        required=saved_base_url is None,
        help=f"GitLab base URL. (saved: {saved_base_url})",
    )
    parser.add_argument(
        "-p",
        "--project-path",
        help="GitLab project path (e.g. 'group/project'). If not provided, it will be auto-detected from the git remote URL.",
    )
    parser.add_argument(
        "-s",
        "--source-branch",
        help="Source branch name. Defaults to the current git branch.",
    )
    parser.add_argument(
        "-t",
        "--target-branch",
        required=True,
        help="Target branch name.",
    )
    parser.add_argument("--title", help="Merge request title.")
    parser.add_argument("-m", "--message", help="Merge request message (description).")
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
    creds = load_credentials()
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
    if not project_path:
        project_path = get_project_path_from_git()
        if not project_path:
            raise SystemExit(
                "Could not auto-detect project path from git remote 'origin'. "
                "Please provide it using the --project-path argument."
            )

    source_branch = args.source_branch
    if not source_branch:
        source_branch = get_current_branch()
        if not source_branch:
            raise SystemExit(
                "Could not auto-detect current git branch. "
                "Please provide it using the --source-branch argument."
            )

    target_branch = args.target_branch

    if source_branch == target_branch:
        raise SystemExit("Source and target branches cannot be the same.")

    assignee = args.assignee
    reviewers = parse_reviewers(args.reviewers)

    title = args.title if args.title else f"Merge {source_branch} into {target_branch}"
    description = args.message

    try:
        mr = client.create_merge_request(
            project_path=project_path,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            description=description,
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
