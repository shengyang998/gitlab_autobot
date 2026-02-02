from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import textwrap
from collections import defaultdict

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


def get_commit_count(target_branch: str, source_branch: str) -> int:
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{target_branch}..{source_branch}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return int(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return 0


def get_last_commit_info(commit_hash: str = "HEAD") -> dict[str, str] | None:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%s%n%b", commit_hash],
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout.strip()
        parts = output.split('\n', 1)
        title = parts[0]
        message = parts[1] if len(parts) > 1 else ""
        return {"title": title, "message": message}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def extract_source_branch_from_merge(message: str) -> str | None:
    match = re.search(r"Merge branch '(.+?)'", message)
    if match:
        return match.group(1)
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


def parse_reviewers(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [name.strip() for name in raw.split(",") if name.strip()]


def get_commits(branch: str) -> list[dict[str, str]]:
    fmt = "%H|%h|%an|%s"
    result = subprocess.run(
        ["git", "log", f"origin/{branch}", f"--pretty={fmt}"],
        capture_output=True,
        text=True,
        check=True,
    )
    commits = []
    for line in result.stdout.strip().split('\n'):
        parts = line.strip().split("|", 3)
        commits.append({
            "hash": parts[0],
            "abbrev_hash": parts[1],
            "author": parts[2],
            "subject": parts[3],
        })
    return commits


def get_patch_id(commit_hash: str) -> str | None:
    try:
        p1 = subprocess.Popen(["git", "show", commit_hash], stdout=subprocess.PIPE)
        p2 = subprocess.Popen(
            ["git", "patch-id"],
            stdin=p1.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        p1.stdout.close()
        stdout, _ = p2.communicate()
        if p2.returncode == 0 and stdout:
            return stdout.strip().split(" ")[0]
        return None
    except (subprocess.CalledProcessError, FileNotFoundError, IndexError):
        return None


def get_diff(commit_hash: str) -> str:
    result = subprocess.run(
        ["git", "show", commit_hash], capture_output=True, text=True, check=True
    )
    return result.stdout


def parse_diff_hunks(diff: str) -> set[str]:
    hunks = set()
    current_hunk = []
    for line in diff.split('\n'):
        if line.startswith("@@"):
            if current_hunk:
                hunks.add("".join(current_hunk))
            current_hunk = []
        elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            current_hunk.append(line[1:])
    if current_hunk:
        hunks.add("".join(current_hunk))
    return hunks


def get_diff_commits(
    source_branch: str, target_branch: str
) -> tuple[list[tuple], list[tuple], list[tuple]]:
    source_commits_rev = f"{target_branch}..{source_branch}"
    target_commits_rev = f"{source_branch}..{target_branch}"

    source_hashes = set(
        subprocess.check_output(["git", "rev-list", source_commits_rev])
        .decode()
        .split()
    )
    target_hashes = set(
        subprocess.check_output(["git", "rev-list", target_commits_rev])
        .decode()
        .split()
    )

    source_commits = {
        h: {"patch_id": get_patch_id(h), "info": get_last_commit_info(h)}
        for h in source_hashes
    }
    target_commits = {
        h: {"patch_id": get_patch_id(h), "info": get_last_commit_info(h)}
        for h in target_hashes
    }

    source_by_patch = {c["patch_id"]: h for h, c in source_commits.items() if c["patch_id"]}
    target_by_patch = {c["patch_id"]: h for h, c in target_commits.items() if c["patch_id"]}

    synced = []
    missing = []
    new = []

    for patch_id, commit_hash in source_by_patch.items():
        if patch_id in target_by_patch:
            synced.append(
                (
                    commit_hash,
                    target_by_patch[patch_id],
                    source_commits[commit_hash]["info"]["title"],
                )
            )
            del target_by_patch[patch_id]
        else:
            missing.append((commit_hash, source_commits[commit_hash]["info"]["title"]))

    for patch_id, commit_hash in target_by_patch.items():
        new.append((commit_hash, target_commits[commit_hash]["info"]["title"]))

    return synced, missing, new


def create_mr_main(args: argparse.Namespace) -> None:
    creds = load_credentials()
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

    title = args.title
    description = args.message

    commit_count = get_commit_count(target_branch, source_branch)
    if commit_count == 1:
        last_commit = get_last_commit_info()
        if last_commit:
            if not title:
                title = last_commit["title"]
            if not description:
                description = last_commit["message"]

    if not title:
        title = f"Merge {source_branch} into {target_branch}"

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


def diff_content_main(args: argparse.Namespace) -> None:
    creds = load_credentials()
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
    target_branch = args.target_branch

    comparison = client.compare(project_path, target_branch, source_branch)
    commits = comparison.get("commits", [])

    print(f"Comparison between {source_branch} and {target_branch}")
    print("-" * 80)
    print("{:<12} {:<15} {}".format("Status", "Commit", "Message"))
    print("-" * 80)

    for commit in commits:
        short_id = commit['short_id']
        title = commit['title']
        print(f"???? UNKNOWN     {short_id}           {title}")


def auto_cherry_pick_main(args: argparse.Namespace) -> None:
    source_branch = args.source_branch
    target_branch = args.target_branch

    _, missing, _ = get_diff_commits(source_branch, target_branch)

    if not missing:
        print("No commits to cherry-pick.")
        return

    commit_hashes = [m[0] for m in missing]

    if args.dry_run:
        print("Dry run enabled. The following actions will be performed:")
        print("\n1. Commits to be cherry-picked:")
        for commit_hash, title in missing:
            print(f"  - {commit_hash[:7]} {title}")

        new_branch_name = f"cherry-pick-{source_branch}-to-{target_branch}"
        print(f"\n2. A new branch will be created: {new_branch_name}")

        print("\n3. The new branch will be pushed to origin.")

        title = args.title or f"Cherry-pick {source_branch} to {target_branch}"
        description = (
            args.message
            or f"Cherry-picking commits from {source_branch} to {target_branch}."
        )
        print("\n4. A merge request will be created with the following details:")
        print(f"  - Title: {title}")
        print(f"  - Description: {description}")
        return

    # Create a new branch
    new_branch_name = f"cherry-pick-{source_branch}-to-{target_branch}"
    try:
        subprocess.check_call(["git", "checkout", target_branch])
        subprocess.check_call(["git", "checkout", "-b", new_branch_name])
    except subprocess.CalledProcessError:
        raise SystemExit(f"Could not create a new branch from {target_branch}.")

    # Cherry-pick the commits in reverse order
    for commit_hash in reversed(commit_hashes):
        try:
            subprocess.check_call(["git", "cherry-pick", commit_hash])
        except subprocess.CalledProcessError:
            subprocess.check_call(["git", "cherry-pick", "--abort"])
            subprocess.check_call(["git", "checkout", target_branch])
            subprocess.check_call(["git", "branch", "-D", new_branch_name])
            raise SystemExit(
                f"Cherry-pick failed for commit {commit_hash}. Conflicts detected."
            )

    # Push the new branch
    try:
        subprocess.check_call(["git", "push", "origin", new_branch_name])
    except subprocess.CalledProcessError:
        raise SystemExit(f"Could not push the new branch {new_branch_name} to origin.")

    # Create a merge request
    args.source_branch = new_branch_name
    if not args.title:
        args.title = f"Cherry-pick {source_branch} to {target_branch}"
    if not args.message:
        args.message = f"Cherry-picking commits from {source_branch} to {target_branch}."
    create_mr_main(args)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GitLab Autobot CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-mr command
    creds = load_credentials()
    saved_base_url = creds.get("base_url")
    parser_create_mr = subparsers.add_parser(
        "create-mr",
        help="Create a GitLab merge request.",
        epilog=textwrap.dedent(
            '''
            Saved credentials will be used for authentication if available.
            The GitLab token can also be provided via the GITLAB_TOKEN environment variable.
            '''
        ),
    )
    parser_create_mr.add_argument(
        "-b",
        "--base-url",
        default=saved_base_url,
        required=saved_base_url is None,
        help=f"GitLab base URL. (saved: {saved_base_url})",
    )
    parser_create_mr.add_argument(
        "-p",
        "--project-path",
        help="GitLab project path (e.g. 'group/project'). If not provided, it will be auto-detected from the git remote URL.",
    )
    parser_create_mr.add_argument(
        "-s",
        "--source-branch",
        help="Source branch name. Defaults to the current git branch.",
    )
    parser_create_mr.add_argument(
        "-t",
        "--target-branch",
        required=True,
        help="Target branch name.",
    )
    parser_create_mr.add_argument("--title", help="Merge request title.")
    parser_create_mr.add_argument("-m", "--message", help="Merge request message (description).")
    parser_create_mr.add_argument("-a", "--assignee", help="Assignee username.")
    parser_create_mr.add_argument(
        "-r",
        "--reviewers",
        help="Comma-separated reviewer usernames (e.g. alice,bob).",
    )
    parser_create_mr.set_defaults(func=create_mr_main)

    # diff-content command
    parser_diff = subparsers.add_parser(
        "diff-content", help="Compare two branches based on diff content."
    )
    parser_diff.add_argument(
        "-s",
        "--source-branch",
        required=True,
        help="Source branch name.",
    )
    parser_diff.add_argument(
        "-t",
        "--target-branch",
        required=True,
        help="Target branch name.",
    )
    parser_diff.set_defaults(func=diff_content_main)

    # auto-cherry-pick command
    parser_auto_cherry_pick = subparsers.add_parser(
        "auto-cherry-pick", help="Automate cherry-picking commits and creating a merge request."
    )
    parser_auto_cherry_pick.add_argument(
        "-b",
        "--base-url",
        default=saved_base_url,
        required=saved_base_url is None,
        help=f"GitLab base URL. (saved: {saved_base_url})",
    )
    parser_auto_cherry_pick.add_argument(
        "-p",
        "--project-path",
        help="GitLab project path (e.g. 'group/project'). If not provided, it will be auto-detected from the git remote URL.",
    )
    parser_auto_cherry_pick.add_argument(
        "-s",
        "--source-branch",
        required=True,
        help="Source branch name.",
    )
    parser_auto_cherry_pick.add_argument(
        "-t",
        "--target-branch",
        required=True,
        help="Target branch name.",
    )
    parser_auto_cherry_pick.add_argument("--title", help="Merge request title.")
    parser_auto_cherry_pick.add_argument(
        "-m", "--message", help="Merge request message (description)."
    )
    parser_auto_cherry_pick.add_argument("-a", "--assignee", help="Assignee username.")
    parser_auto_cherry_pick.add_argument(
        "-r",
        "--reviewers",
        help="Comma-separated reviewer usernames (e.g. alice,bob).",
    )
    parser_auto_cherry_pick.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without creating branches or merge requests.",
    )
    parser_auto_cherry_pick.set_defaults(func=auto_cherry_pick_main)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
