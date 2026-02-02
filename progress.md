# Progress

## 2026-02-02
- Removed unused extract_source_branch_from_merge from cli.py.
- Added project status tracking files.
- Investigated synced commits display issue in CLI diff output.
- Updated synced output to show source and target commit hashes.
- Verified diff-content used local git only; compare API was unused.
- Updated diff-content to use GitLab compare and commit diff APIs when credentials are available, with local fallback.
- Documented diff-content CLI options and behavior in README.
