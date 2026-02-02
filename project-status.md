# Project Status

Date: 2026-02-03
Status: On track

## Current Status
- Working branch: cursor/branch-rebase-necessity-check-4e3a
- Focus: Validate branch refs and sync local branches for branch-cherry-pick.

## Decisions
- Keep diff-content output based on patch-id comparisons without merge message parsing, since that logic is no longer used.
- Synced commit display now uses "source->target" to reflect cherry-picked hashes.
- diff-content now prefers the GitLab compare API when credentials are available and falls back to local git otherwise.
- Patch-id matching uses GitLab commit diff results to keep synced/missing/new output consistent.
- Squash detection uses diff-line containment (with file context) to mark commits as synced.
- Branch-cherry-pick hides merge commits because the tool cannot cherry-pick merges without manual intervention.
- Branch-cherry-pick temporary branches use a cherry-pick/ prefix with sanitized
  branch names and a 5-character alphanumeric suffix to avoid collisions.
- diff-content hides merge commits by default with an include flag for audits.
- Renamed CLI command to branch-cherry-pick for clarity.
- Use compare parent_ids to identify merge commits when diff-content uses GitLab API.
- Validate branch refs before local diff/cherry-pick to avoid ambiguous rev errors.
- Branch-cherry-pick now fast-forwards local branches from origin and errors on divergence.

## Changes
- Removed dead code in cli.py for unused merge source extraction.
- Synced commit output shows both source and target hashes.
- Added GitLab client support for commit diff retrieval and compare with cached project id usage.
- Updated diff-content CLI arguments for base URL and project path.
- Updated README documentation for diff-content usage.
- Added diff-line based matching to detect squashed commits for diff-content.
- Branch-cherry-pick now filters merge commits from dry-run and execution lists.
- diff-content filters merge commits by default and adds --include-merges.
- Updated CLI messages and subcommand name to branch-cherry-pick.
- Documented branch-cherry-pick CLI usage in README.
- Filter diff-content merge commits using compare metadata with local fallback.
- Updated branch-cherry-pick temporary branch naming format and suffix.
- Added branch ref resolution with fetch guidance for local comparisons.
- Added local branch sync to origin before branch-cherry-pick diffs and checkout.
