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
