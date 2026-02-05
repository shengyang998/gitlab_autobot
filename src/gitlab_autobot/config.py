from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "gitlab_autobot"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"


def load_credentials() -> dict[str, Any]:
    """Load credentials from the saved config file."""
    if not CREDENTIALS_PATH.exists():
        return {}
    try:
        return json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_credentials(data: dict[str, Any]) -> None:
    """Save credentials to the config file with secure permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    tmp_path = CREDENTIALS_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp_path.chmod(0o600)
    tmp_path.replace(CREDENTIALS_PATH)
    CREDENTIALS_PATH.chmod(0o600)


def get_credentials() -> tuple[str | None, str | None]:
    """Get GitLab credentials with priority: env vars > saved config.
    
    Environment variables (for Jenkins CI):
        - GITLAB_TOKEN: GitLab API token
        - GITLAB_BASE_URL: GitLab server URL
    
    Returns:
        Tuple of (base_url, token)
    """
    # Priority 1: Environment variables (Jenkins CI)
    token = os.getenv("GITLAB_TOKEN")
    base_url = os.getenv("GITLAB_BASE_URL")
    
    # Priority 2: Saved credentials file
    if not token or not base_url:
        saved = load_credentials()
        token = token or saved.get("token")
        base_url = base_url or saved.get("base_url")
    
    return base_url, token
