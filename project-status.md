# Project Status

Date: 2026-02-02
Status: On track

## Current Status
- Working branch: cursor/cherry-pick-merge-commits-visibility-b02c
- Focus: Hiding merge commits in diff-content by default.

## Decisions
- Keep diff-content output based on patch-id comparisons without merge message parsing, since that logic is no longer used.
- Synced commit display now uses "source->target" to reflect cherry-picked hashes.
- diff-content now prefers the GitLab compare API when credentials are available and falls back to local git otherwise.
- Patch-id matching uses GitLab commit diff results to keep synced/missing/new output consistent.
- Squash detection uses diff-line containment (with file context) to mark commits as synced.
- Auto-cherry-pick hides merge commits because the tool cannot cherry-pick merges without manual intervention.
- diff-content hides merge commits by default with an include flag for audits.

## Changes
- Removed dead code in cli.py for unused merge source extraction.
- Synced commit output shows both source and target hashes.
- Added GitLab client support for commit diff retrieval and compare with cached project id usage.
- Updated diff-content CLI arguments for base URL and project path.
- Updated README documentation for diff-content usage.
- Added diff-line based matching to detect squashed commits for diff-content.
- Auto-cherry-pick now filters merge commits from dry-run and execution lists.
- diff-content filters merge commits by default and adds --include-merges.
