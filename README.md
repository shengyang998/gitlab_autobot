# GitLab Autobot

CLI and MCP server to create GitLab merge requests and generate MR messages.

## Requirements

- Python 3.10+
- A GitLab personal access token with API access
- (For MCP usage) an OpenAI API key

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

3. (Optional) Export your OpenAI API key for the MCP server:

   ```bash
   export OPENAI_API_KEY="your-key"
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

## MCP server usage (MR message generation)

Start the MCP server:

```bash
gitlab-autobot-mcp
```

The server exposes a `generate_mr_message` tool that accepts:

- `title` (string)
- `summary` (string)
- `changes` (list of strings, optional)
- `tests` (list of strings, optional)

Make sure `OPENAI_API_KEY` is set before running the server.
