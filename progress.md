# Progress

## 2026-02-02
- Removed unused extract_source_branch_from_merge from cli.py.
- Added project status tracking files.
- Investigated synced commits display issue in CLI diff output.
- Updated synced output to show source and target commit hashes.
- Verified diff-content used local git only; compare API was unused.
- Updated diff-content to use GitLab compare and commit diff APIs when credentials are available, with local fallback.
- Documented diff-content CLI options and behavior in README.
- Added squash-aware diff-content matching using diff-line containment.
- Updated diff-content documentation to describe squash-aware comparisons.
- Branch-cherry-pick now skips merge commits in dry-run and execution output.
- diff-content now hides merge commits by default with an include flag.
- Renamed command to branch-cherry-pick.
- Documented branch-cherry-pick usage in README.
- Fixed diff-content merge filtering to use compare parent IDs with local fallback.
- Updated branch-cherry-pick temp branch naming with prefix, sanitization, and suffix.
