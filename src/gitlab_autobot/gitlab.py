from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import quote_plus

import requests


class AuthError(RuntimeError):
    pass


class GitLabError(RuntimeError):
    pass


@dataclass
class GitLabClient:
    base_url: str
    token: str

    @property
    def api_base(self) -> str:
        return self.base_url.rstrip("/") + "/api/v4"

    def _headers(self) -> dict[str, str]:
        return {
            "PRIVATE-TOKEN": self.token,
            "Content-Type": "application/json",
        }

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.api_base}/{path.lstrip('/')}"
        response = requests.request(method, url, headers=self._headers(), **kwargs)
        if response.status_code == 401:
            raise AuthError("Authentication failed.")
        if not response.ok:
            raise GitLabError(
                f"GitLab API error {response.status_code}: {response.text}"
            )
        return response

    def get_current_user(self) -> dict[str, Any]:
        return self.request("GET", "/user").json()

    def get_user_id(self, username: str) -> int:
        response = self.request("GET", "/users", params={"username": username}).json()
        if not response:
            raise GitLabError(f"No user found for username '{username}'.")
        return response[0]["id"]

    def get_project_id(self, project_path: str) -> int:
        encoded = quote_plus(project_path)
        response = self.request("GET", f"/projects/{encoded}").json()
        return response["id"]

    def create_merge_request(
        self,
        project_path: str,
        source_branch: str,
        target_branch: str,
        title: str,
        assignee: str | None = None,
        reviewers: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        project_id = self.get_project_id(project_path)
        payload: dict[str, Any] = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
        }
        if assignee:
            payload["assignee_id"] = self.get_user_id(assignee)
        if reviewers:
            reviewer_ids = [self.get_user_id(name) for name in reviewers]
            payload["reviewer_ids"] = reviewer_ids
        return self.request(
            "POST", f"/projects/{project_id}/merge_requests", json=payload
        ).json()
