# GitLab Autobot

CLI and MCP server to create GitLab merge requests and generate MR messages.

## Requirements

- Python 3.10+
- A GitLab personal access token with API access

## Setup

1. Create and activate a virtual environment (optional but recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install the package:

   ```bash
   pip install -e .
   ```

### Using uv without activating a venv

If you want the CLI/MCP commands to be available outside a virtual environment
(e.g. for Cursor or Claude), use `uv` to run or install the tools:

```bash
uv tool run --from . gitlab-autobot-mcp
```

Or install the tools globally for your user:

```bash
uv tool install .
```

### Configure Cursor, Claude Code, or Codex

If your editor/agent needs an MCP server command, point it at the installed
binary (recommended) or use `uv tool run --from .` for a repo checkout.

Example `mcp.json` entry:

```json
{
  "mcpServers": {
    "gitlab-autobot": {
      "command": "gitlab-autobot-mcp",
      "args": []
    }
  }
}
```

If you prefer to run from source without installing:

```json
{
  "mcpServers": {
    "gitlab-autobot": {
      "command": "uv",
      "args": ["tool", "run", "--from", ".", "gitlab-autobot-mcp"]
    }
  }
}
```

You can also point your editor to a helper script that starts the MCP server
from this repo:

```json
{
  "mcpServers": {
    "gitlab-autobot": {
      "command": "./scripts/start-mcp.sh",
      "args": []
    }
  }
}
```

## CLI usage (create-mr)

Create a GitLab merge request. It can be run interactively or with command-line arguments.

### Interactive Mode

Run the `create-mr` command without all the required arguments to be prompted for the missing information:

```bash
gitlab-autobot create-mr
```

You will be asked for any missing details like project path, branches, and title.

### Non-Interactive Mode

Provide all the necessary details as arguments:

```bash
gitlab-autobot create-mr [OPTIONS]
```

**Arguments:**

*   `-b`, `--base-url`: GitLab base URL. If not provided, the saved URL is used.
*   `-p`, `--project-path`: GitLab project path (e.g., 'group/project'). Auto-detected from the git remote if omitted.
*   `-s`, `--source-branch`: Source branch name. Defaults to the current git branch.
*   `-t`, `--target-branch`: **(Required)** Target branch name.
*   `--title`: Merge request title.
*   `-m`, `--message`: Merge request description.
*   `-a`, `--assignee`: Assignee username.
*   `-r`, `--reviewers`: Comma-separated list of reviewer usernames.

Credentials are stored at `~/.config/gitlab_autobot/credentials.json` and will be used for authentication if available. The GitLab token can also be provided via the `GITLAB_TOKEN` environment variable.

## CLI usage (diff-content)

Run the CLI with the `diff-content` subcommand:

```bash
gitlab-autobot diff-content --source-branch <source_branch> --target-branch <target_branch>
```

This command compares the content of two branches. When GitLab credentials are
available (saved config or `GITLAB_TOKEN`), it uses the GitLab compare API and
falls back to local git diffing if not.

The comparison is content-based: it matches commits by patch-id and also detects
when a commit's changed lines are fully contained in a target commit (to treat
squashed commits as synced).

Merge commits are hidden by default; use `--include-merges` to show them.

Optional arguments:

*   `-b`, `--base-url`: GitLab base URL. If not provided, the saved URL is used.
*   `-p`, `--project-path`: GitLab project path (e.g., 'group/project'). Auto-detected from the git remote if omitted.
*   `--include-merges`: Include merge commits in the output (hidden by default).

## CLI usage (branch-cherry-pick)

Run the CLI with the `branch-cherry-pick` subcommand:

```bash
gitlab-autobot branch-cherry-pick --source-branch <source_branch> --target-branch <target_branch>
```

This command cherry-picks commits from the source branch that are missing in the
target branch, then creates a merge request for the new branch. Merge commits
are skipped because cherry-picking merges is not supported.

Optional arguments:

*   `-b`, `--base-url`: GitLab base URL. If not provided, the saved URL is used.
*   `-p`, `--project-path`: GitLab project path (e.g., 'group/project'). Auto-detected from the git remote if omitted.
*   `-s`, `--source-branch`: Source branch name. **(Required)**
*   `-t`, `--target-branch`: Target branch name. **(Required)**
*   `--title`: Merge request title.
*   `-m`, `--message`: Merge request description.
*   `-a`, `--assignee`: Assignee username.
*   `-r`, `--reviewers`: Comma-separated list of reviewer usernames.
*   `--dry-run`: Show planned actions without creating a branch or merge request.

## MCP server usage (MR tooling)

Start the MCP server:

```bash
gitlab-autobot-mcp
```

The server exposes tools for:

- Creating merge requests via the GitLab API (`create_merge_request`).
- Collecting git log and diff information for MR changes (`collect_mr_changes`).
- Accepting an MR message supplied by the LLM (`submit_mr_message`).

### `create_merge_request`

Creates a merge request on GitLab.

**Parameters:**

- `project_path` (str): The GitLab project path (e.g., `group/project`).
- `source_branch` (str): The source branch for the merge request.
- `target_branch` (str): The target branch for the merge request.
- `title` (str): The title of the merge request.
- `description` (str, optional): The merge request description in Markdown.
- `assignee` (str, optional): The GitLab username to assign the merge request to.
- `reviewers` (list[str], optional): A list of GitLab usernames to add as reviewers.
- `base_url` (str, optional): The GitLab base URL. Defaults to the saved credentials.
- `token` (str, optional): The GitLab access token. Defaults to the saved credentials.

**Returns:**

A dictionary containing the new merge request's ID, IID, title, and web URL.

### `collect_mr_changes`

Collects the git log and diff for a merge request.

**Parameters:**

- `base_ref` (str, optional): The git ref for the merge request base. Defaults to `origin/main`.
- `head_ref` (str, optional): The git ref for the merge request head. Defaults to `HEAD`.
- `max_commits` (int, optional): The maximum number of commits to return. Defaults to `50`.
- `repo_path` (str, optional): The path to the repository. Overrides the default repository discovery.

**Returns:**

A dictionary containing the git log and diff.

### `submit_mr_message`

Accepts a merge request message from an LLM.

**Parameters:**

- `message` (str): The prepared merge request message body.

**Returns:**

A dictionary containing the submitted message.
