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

## CLI usage (merge requests)

Run the CLI and follow the prompts:

```bash
gitlab-autobot
```

You will be asked for:

- GitLab base URL (defaults to `https://gitlab.com`)
- Personal access token (stored locally)
- Project path (`group/project`)
- Source and target branches
- Optional assignee and reviewer usernames

Credentials are stored at:

```
~/.config/gitlab_autobot/credentials.json
```

## MCP server usage (MR tooling)

Start the MCP server:

```bash
gitlab-autobot-mcp
```

The server exposes tools for:

- Creating merge requests via the GitLab API (`create_merge_request`).
- Collecting git log and diff information for MR changes (`collect_mr_changes`).
- Accepting an MR message supplied by the LLM (`submit_mr_message`).
