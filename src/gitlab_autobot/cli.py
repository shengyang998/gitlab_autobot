from __future__ import annotations

import argparse
import collections
import os
import re
import secrets
import string
import subprocess
import textwrap
from typing import Any, Iterable
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


def git_ref_exists(ref: str) -> bool:
    assert ref
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def has_git_remote(remote: str) -> bool:
    assert remote
    result = subprocess.run(
        ["git", "remote", "get-url", remote],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def normalize_fetch_branch(branch: str, remote: str) -> str:
    assert branch
    assert remote
    remote_prefix = f"{remote}/"
    if branch.startswith(remote_prefix):
        return branch[len(remote_prefix) :]
    if branch.startswith("refs/heads/"):
        return branch[len("refs/heads/") :]
    remote_ref_prefix = f"refs/remotes/{remote}/"
    if branch.startswith(remote_ref_prefix):
        return branch[len(remote_ref_prefix) :]
    return branch


def resolve_branch_ref(branch: str, remote: str = "origin") -> str | None:
    assert branch
    assert remote
    if git_ref_exists(branch):
        return branch
    remote_ref = f"{remote}/{branch}"
    if git_ref_exists(remote_ref):
        return remote_ref
    return None


def ensure_branch_refs(
    source_branch: str, target_branch: str, remote: str = "origin"
) -> tuple[str, str]:
    assert source_branch
    assert target_branch
    assert remote
    source_ref = resolve_branch_ref(source_branch, remote=remote)
    target_ref = resolve_branch_ref(target_branch, remote=remote)
    missing: list[str] = []
    if not source_ref:
        missing.append(source_branch)
    if not target_ref:
        missing.append(target_branch)
    if missing:
        missing_text = ", ".join(missing)
        fetch_hint = ""
        if has_git_remote(remote):
            fetch_branches = [normalize_fetch_branch(branch, remote) for branch in missing]
            fetch_cmd = f"git fetch {remote} " + " ".join(fetch_branches)
            fetch_hint = f" Run `{fetch_cmd}` and try again."
        else:
            fetch_hint = " Add a git remote or create the branch locally."
        raise SystemExit(
            "Branch not found locally: "
            f"{missing_text}.{fetch_hint}"
        )
    assert source_ref
    assert target_ref
    return source_ref, target_ref


def _git_fetch_branch(branch: str, remote: str = "origin") -> None:
    assert branch
    assert remote
    try:
        subprocess.check_call(["git", "fetch", remote, branch])
    except subprocess.CalledProcessError:
        raise SystemExit(f"Could not fetch {remote}/{branch}.")
    except FileNotFoundError:
        raise SystemExit("Git is not available in PATH.")


def _git_ahead_behind(local_ref: str, remote_ref: str) -> tuple[int, int]:
    try:
        result = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", f"{local_ref}...{remote_ref}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise SystemExit(f"Could not compare {local_ref} with {remote_ref}.")
    output = result.stdout.strip()
    parts = output.split()
    assert len(parts) == 2
    ahead, behind = int(parts[0]), int(parts[1])
    return ahead, behind


def ensure_local_branch_up_to_date(branch: str, remote: str = "origin") -> None:
    assert branch
    assert remote
    normalized_branch = normalize_fetch_branch(branch, remote)
    _git_fetch_branch(normalized_branch, remote=remote)
    remote_ref = f"refs/remotes/{remote}/{normalized_branch}"
    if not git_ref_exists(remote_ref):
        raise SystemExit(f"Remote branch {remote}/{normalized_branch} not found.")

    local_ref = f"refs/heads/{normalized_branch}"
    if not git_ref_exists(local_ref):
        try:
            subprocess.check_call(
                ["git", "branch", normalized_branch, f"{remote}/{normalized_branch}"]
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise SystemExit(f"Could not create local branch {normalized_branch}.")
        return

    ahead, behind = _git_ahead_behind(normalized_branch, f"{remote}/{normalized_branch}")
    assert ahead >= 0
    assert behind >= 0
    if behind == 0:
        return
    if ahead > 0:
        raise SystemExit(
            f"Local branch {normalized_branch} has diverged from {remote}/"
            f"{normalized_branch}. Please sync manually."
        )

    current_branch = get_current_branch()
    if current_branch is None:
        raise SystemExit("Could not determine current git branch.")
    try:
        if current_branch == normalized_branch:
            subprocess.check_call(
                ["git", "merge", "--ff-only", f"{remote}/{normalized_branch}"]
            )
        else:
            subprocess.check_call(["git", "update-ref", local_ref, remote_ref])
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise SystemExit(
            f"Could not fast-forward local branch {normalized_branch} to "
            f"{remote}/{normalized_branch}."
        )


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


def build_cherry_pick_branch_name(source_branch: str, target_branch: str) -> str:
    safe_source = source_branch.replace("/", "-")
    safe_target = target_branch.replace("/", "-")
    suffix = "".join(
        secrets.choice(string.ascii_lowercase + string.digits) for _ in range(5)
    )
    assert safe_source
    assert safe_target
    assert len(suffix) == 5
    assert suffix.isalnum()
    return f"cherry-pick/{safe_source}-to-{safe_target}-{suffix}"


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


def flatten_diff_entries(diff_entries: Iterable[dict[str, Any]]) -> str:
    parts = []
    for entry in diff_entries:
        diff_text = entry.get("diff")
        if diff_text:
            parts.append(diff_text.rstrip("\n"))
    if not parts:
        return ""
    return "\n".join(parts) + "\n"


def get_patch_id_from_diff(diff_text: str) -> str | None:
    if not diff_text.strip():
        return None
    try:
        result = subprocess.run(
            ["git", "patch-id"],
            input=diff_text,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        return result.stdout.strip().split(" ")[0]
    except FileNotFoundError:
        return None


def parse_diff_lines(diff_text: str) -> collections.Counter[str]:
    lines = collections.Counter()
    current_file = ""
    for line in diff_text.split("\n"):
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3]
                if current_file.startswith("b/"):
                    current_file = current_file[2:]
        elif line.startswith("+++ "):
            path = line[4:].strip()
            if path.startswith("b/"):
                current_file = path[2:]
        elif line.startswith("--- "):
            path = line[4:].strip()
            if not current_file and path.startswith("a/"):
                current_file = path[2:]
        elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            prefix = f"{current_file}:" if current_file else ""
            lines[f"{prefix}{line[0]}{line[1:]}"] += 1
    return lines


def classify_diff_commits(
    source_commits: dict[str, dict[str, Any]],
    target_commits: dict[str, dict[str, Any]],
) -> tuple[list[tuple], list[tuple], list[tuple]]:
    source_by_patch = {
        c["patch_id"]: h for h, c in source_commits.items() if c["patch_id"]
    }
    target_by_patch = {
        c["patch_id"]: h for h, c in target_commits.items() if c["patch_id"]
    }

    synced = []
    missing = []
    new = []
    matched_source: set[str] = set()
    matched_target: set[str] = set()

    for patch_id, commit_hash in source_by_patch.items():
        target_hash = target_by_patch.get(patch_id)
        if target_hash:
            synced.append(
                (
                    commit_hash,
                    target_hash,
                    source_commits[commit_hash]["info"]["title"],
                )
            )
            matched_source.add(commit_hash)
            matched_target.add(target_hash)

    for commit_hash, source_data in source_commits.items():
        if commit_hash in matched_source:
            continue
        source_lines = source_data["diff_lines"]
        if not source_lines:
            continue
        best_target = None
        best_extra = None
        for target_hash, target_data in target_commits.items():
            target_lines = target_data["diff_lines"]
            if not target_lines:
                continue
            if any(
                target_lines[key] < count for key, count in source_lines.items()
            ):
                continue
            extra = sum((target_lines - source_lines).values())
            if best_target is None or extra < best_extra:
                best_target = target_hash
                best_extra = extra
        if best_target:
            synced.append(
                (commit_hash, best_target, source_data["info"]["title"])
            )
            matched_source.add(commit_hash)
            matched_target.add(best_target)

    for commit_hash, source_data in source_commits.items():
        if commit_hash not in matched_source:
            missing.append((commit_hash, source_data["info"]["title"]))

    for commit_hash, target_data in target_commits.items():
        if commit_hash not in matched_target:
            new.append((commit_hash, target_data["info"]["title"]))

    return synced, missing, new


def extract_merge_commits_from_compare(
    commits_raw: list[dict[str, Any]]
) -> set[str] | None:
    merges: set[str] = set()
    saw_parent_ids = False
    for commit in commits_raw:
        parent_ids = commit.get("parent_ids")
        if parent_ids is None:
            continue
        saw_parent_ids = True
        assert isinstance(parent_ids, list)
        if len(parent_ids) <= 1:
            continue
        commit_hash = commit.get("id") or commit.get("sha")
        if commit_hash:
            merges.add(commit_hash)
    if not saw_parent_ids:
        return None
    return merges


def get_remote_diff_commits(
    client: GitLabClient,
    project_path: str,
    source_branch: str,
    target_branch: str,
) -> tuple[
    list[tuple],
    list[tuple],
    list[tuple],
    set[str] | None,
    set[str] | None,
]:
    project_id = client.get_project_id(project_path)
    source_compare = client.compare(
        project_path=project_path,
        from_ref=target_branch,
        to_ref=source_branch,
        project_id=project_id,
    )
    target_compare = client.compare(
        project_path=project_path,
        from_ref=source_branch,
        to_ref=target_branch,
        project_id=project_id,
    )
    source_commits_raw = source_compare.get("commits", [])
    target_commits_raw = target_compare.get("commits", [])
    assert isinstance(source_commits_raw, list)
    assert isinstance(target_commits_raw, list)
    source_merge_commits = extract_merge_commits_from_compare(source_commits_raw)
    target_merge_commits = extract_merge_commits_from_compare(target_commits_raw)

    diff_cache: dict[str, str] = {}
    patch_id_cache: dict[str, str | None] = {}
    diff_lines_cache: dict[str, collections.Counter[str]] = {}

    def commit_diff_text(commit_hash: str) -> str:
        if commit_hash in diff_cache:
            return diff_cache[commit_hash]
        diff_entries = client.get_commit_diff(
            project_path=project_path,
            commit_sha=commit_hash,
            project_id=project_id,
        )
        assert isinstance(diff_entries, list)
        diff_text = flatten_diff_entries(diff_entries)
        diff_cache[commit_hash] = diff_text
        return diff_text

    def commit_patch_id(commit_hash: str) -> str | None:
        if commit_hash in patch_id_cache:
            return patch_id_cache[commit_hash]
        diff_text = commit_diff_text(commit_hash)
        patch_id = get_patch_id_from_diff(diff_text)
        patch_id_cache[commit_hash] = patch_id
        return patch_id

    def commit_diff_lines(commit_hash: str) -> collections.Counter[str]:
        if commit_hash in diff_lines_cache:
            return diff_lines_cache[commit_hash]
        diff_text = commit_diff_text(commit_hash)
        diff_lines = parse_diff_lines(diff_text)
        diff_lines_cache[commit_hash] = diff_lines
        return diff_lines

    def build_commit_map(
        commits_raw: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        commit_map: dict[str, dict[str, Any]] = {}
        for commit in commits_raw:
            commit_hash = commit.get("id") or commit.get("sha")
            if not commit_hash:
                continue
            patch_id = commit_patch_id(commit_hash)
            diff_lines = commit_diff_lines(commit_hash)
            title = commit.get("title") or commit.get("message") or ""
            commit_map[commit_hash] = {
                "patch_id": patch_id,
                "diff_lines": diff_lines,
                "info": {"title": title},
            }
        return commit_map

    source_commits = build_commit_map(source_commits_raw)
    target_commits = build_commit_map(target_commits_raw)
    synced, missing, new = classify_diff_commits(source_commits, target_commits)
    return synced, missing, new, source_merge_commits, target_merge_commits


def get_diff(commit_hash: str) -> str:
    result = subprocess.run(
        ["git", "show", "--pretty=format:", commit_hash],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def get_diff_commits(
    source_branch: str, target_branch: str
) -> tuple[list[tuple], list[tuple], list[tuple]]:
    source_ref, target_ref = ensure_branch_refs(source_branch, target_branch)
    source_commits_rev = f"{target_ref}..{source_ref}"
    target_commits_rev = f"{source_ref}..{target_ref}"

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

    def build_commit_map(commit_hashes: set[str]) -> dict[str, dict[str, Any]]:
        commit_map: dict[str, dict[str, Any]] = {}
        for commit_hash in commit_hashes:
            diff_text = get_diff(commit_hash)
            patch_id = get_patch_id_from_diff(diff_text)
            diff_lines = parse_diff_lines(diff_text)
            info = get_last_commit_info(commit_hash) or {}
            commit_map[commit_hash] = {
                "patch_id": patch_id,
                "diff_lines": diff_lines,
                "info": {"title": info.get("title", "")},
            }
        return commit_map

    source_commits = build_commit_map(source_hashes)
    target_commits = build_commit_map(target_hashes)
    return classify_diff_commits(source_commits, target_commits)


def get_merge_commits(source_branch: str, target_branch: str) -> set[str]:
    source_ref, target_ref = ensure_branch_refs(source_branch, target_branch)
    source_commits_rev = f"{target_ref}..{source_ref}"
    try:
        output = subprocess.check_output(
            ["git", "rev-list", "--merges", source_commits_rev],
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()
    return set(output.split())


def filter_merge_commits(
    synced: list[tuple],
    missing: list[tuple],
    new: list[tuple],
    source_branch: str,
    target_branch: str,
    include_merges: bool,
    source_merges: set[str] | None = None,
    target_merges: set[str] | None = None,
) -> tuple[list[tuple], list[tuple], list[tuple], dict[str, int]]:
    assert isinstance(synced, list)
    assert isinstance(missing, list)
    assert isinstance(new, list)
    assert source_merges is None or isinstance(source_merges, set)
    assert target_merges is None or isinstance(target_merges, set)
    if include_merges:
        return synced, missing, new, {"synced": 0, "missing": 0, "new": 0}

    if source_merges is None:
        source_merges = get_merge_commits(source_branch, target_branch)
    if target_merges is None:
        target_merges = get_merge_commits(target_branch, source_branch)

    synced_filtered = [
        entry
        for entry in synced
        if entry[0] not in source_merges and entry[1] not in target_merges
    ]
    missing_filtered = [
        entry for entry in missing if entry[0] not in source_merges
    ]
    new_filtered = [entry for entry in new if entry[0] not in target_merges]

    return (
        synced_filtered,
        missing_filtered,
        new_filtered,
        {
            "synced": len(synced) - len(synced_filtered),
            "missing": len(missing) - len(missing_filtered),
            "new": len(new) - len(new_filtered),
        },
    )


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
    source_branch = args.source_branch
    target_branch = args.target_branch

    creds = load_credentials()
    token = creds.get("token") or os.getenv("GITLAB_TOKEN")
    base_url = args.base_url or creds.get("base_url")
    project_path = args.project_path or get_project_path_from_git()
    source_merges = None
    target_merges = None

    if token and base_url and project_path:
        client = GitLabClient(base_url=base_url, token=token)
        try:
            synced, missing, new, source_merges, target_merges = get_remote_diff_commits(
                client=client,
                project_path=project_path,
                source_branch=source_branch,
                target_branch=target_branch,
            )
        except AuthError:
            raise SystemExit("Authentication failed. Provide a valid token.")
        except GitLabError as exc:
            raise SystemExit(str(exc))
    else:
        # Use local git to compare branches with patch-id detection
        synced, missing, new = get_diff_commits(source_branch, target_branch)

    synced, missing, new, merge_counts = filter_merge_commits(
        synced,
        missing,
        new,
        source_branch=source_branch,
        target_branch=target_branch,
        include_merges=args.include_merges,
        source_merges=source_merges,
        target_merges=target_merges,
    )

    print(f"Comparison between {source_branch} and {target_branch}")
    print("-" * 80)
    if not args.include_merges:
        skipped_merges = sum(merge_counts.values())
        if skipped_merges:
            details = []
            if merge_counts["missing"]:
                details.append(f"{merge_counts['missing']} missing")
            if merge_counts["synced"]:
                details.append(f"{merge_counts['synced']} synced")
            if merge_counts["new"]:
                details.append(f"{merge_counts['new']} new")
            detail_text = ", ".join(details)
            print(
                "Note: Skipping merge commits "
                f"({detail_text}). Use --include-merges to show them."
            )
    print("{:<12} {:<12} {}".format("Status", "Commit", "Message"))
    print("-" * 80)

    # Show synced commits (cherry-picked to target)
    for source_hash, target_hash, title in synced:
        print(
            "{:<12} {:<12} {}".format(
                "SYNCED", f"{source_hash[:7]}->{target_hash[:7]}", title
            )
        )

    # Show missing commits (need to be cherry-picked)
    for commit_hash, title in missing:
        print("{:<12} {:<12} {}".format("MISSING", commit_hash[:7], title))

    # Show new commits (only in target, not in source)
    for commit_hash, title in new:
        print("{:<12} {:<12} {}".format("NEW", commit_hash[:7], title))

    # Print summary
    print("-" * 80)
    print(f"Summary: {len(synced)} synced, {len(missing)} missing, {len(new)} new in target")


def auto_cherry_pick_main(args: argparse.Namespace) -> None:
    source_branch = args.source_branch
    target_branch = args.target_branch

    if not args.dry_run:
        ensure_local_branch_up_to_date(source_branch)
        ensure_local_branch_up_to_date(target_branch)

    _, missing, _ = get_diff_commits(source_branch, target_branch)
    _, missing_non_merge, _, merge_counts = filter_merge_commits(
        [],
        missing,
        [],
        source_branch=source_branch,
        target_branch=target_branch,
        include_merges=False,
    )
    skipped_merges = merge_counts["missing"]

    if not missing_non_merge:
        if skipped_merges:
            print(
                "No non-merge commits to cherry-pick. "
                "Branch-cherry-pick skips merge commits."
            )
        else:
            print("No commits to cherry-pick.")
        return

    if skipped_merges and not args.dry_run:
        print(
            f"Note: Skipping {skipped_merges} merge commit(s) because "
            "branch-cherry-pick does not support cherry-picking merges."
        )

    commit_hashes = [m[0] for m in missing_non_merge]

    if args.dry_run:
        print("Dry run enabled. The following actions will be performed:")
        print("\n1. Commits to be cherry-picked:")
        for commit_hash, title in missing_non_merge:
            print(f"  - {commit_hash[:7]} {title}")
        if skipped_merges:
            print(
                f"  (skipped {skipped_merges} merge commit(s) "
                "not supported by branch-cherry-pick)"
            )

        new_branch_name = build_cherry_pick_branch_name(source_branch, target_branch)
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
    new_branch_name = build_cherry_pick_branch_name(source_branch, target_branch)
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
        "diff-content",
        help="Compare two branches based on diff content.",
        description=(
            "Compares branches using GitLab's compare API when credentials are "
            "available, with a local git fallback. Merge commits are hidden by "
            "default; use --include-merges to show them."
        ),
    )
    parser_diff.add_argument(
        "-b",
        "--base-url",
        default=saved_base_url,
        help=f"GitLab base URL. (saved: {saved_base_url})",
    )
    parser_diff.add_argument(
        "-p",
        "--project-path",
        help=(
            "GitLab project path (e.g. 'group/project'). If not provided, it will "
            "be auto-detected from the git remote URL."
        ),
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
    parser_diff.add_argument(
        "--include-merges",
        action="store_true",
        help="Include merge commits in the output (hidden by default).",
    )
    parser_diff.set_defaults(func=diff_content_main)

    # branch-cherry-pick command
    parser_auto_cherry_pick = subparsers.add_parser(
        "branch-cherry-pick",
        help="Automate cherry-picking commits and creating a merge request.",
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
