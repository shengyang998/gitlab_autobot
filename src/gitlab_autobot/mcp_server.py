from __future__ import annotations

import os
from typing import Any

from openai import OpenAI
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gitlab-autobot")


def _openai_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Provide an API key to generate MR messages."
        )
    return OpenAI(api_key=api_key)


@mcp.tool()
def generate_mr_message(
    title: str,
    summary: str,
    changes: list[str] | None = None,
    tests: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a merge request message using an LLM."""
    client = _openai_client()
    change_lines = "\n".join(f"- {item}" for item in (changes or [])) or "- None"
    test_lines = "\n".join(f"- {item}" for item in (tests or [])) or "- Not run"
    prompt = (
        "Write a merge request message in markdown with Summary and Testing sections.\n"
        f"Title: {title}\n"
        f"Summary: {summary}\n"
        "Changes:\n"
        f"{change_lines}\n"
        "Tests:\n"
        f"{test_lines}\n"
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    content = response.choices[0].message.content or ""
    return {"message": content.strip()}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
