"""Bridge to dida365-openapi library with error handling and retry."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.error import URLError

# Resolve vendor path: support DIDA365_LIB_PATH env var, or fall back to vendor/
_VENDOR_DIR = os.environ.get(
    "DIDA365_LIB_PATH",
    str(Path(__file__).resolve().parent.parent / "vendor" / "dida365-openapi" / "scripts"),
)
if _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)

from dida365_lib.client import Dida365Client
from dida365_lib.config import RuntimeSettings, resolve_runtime_settings
from dida365_lib.errors import ApiError, UserFacingError
from dida365_lib.http import HttpResponse


MAX_RETRIES = 2
RETRY_DELAY = 1.0


class BridgeError(Exception):
    """Structured error from the bridge layer."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        result = {"error": self.message}
        if self.details:
            result["details"] = self.details
        return result


class DidaBridge:
    """Wraps Dida365Client with retry, error handling, and JSON output."""

    def __init__(self, config_dir: Optional[str] = None):
        overrides = {}
        if config_dir:
            overrides["config_dir"] = config_dir
        self._settings = resolve_runtime_settings(overrides or None)
        self._client = Dida365Client(self._settings)

    def _call(self, fn, *args, **kwargs) -> Any:
        """Call a client method with retry on network errors."""
        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response: HttpResponse = fn(*args, **kwargs)
                return response.data
            except ApiError as e:
                if e.status_code == 401:
                    raise BridgeError("token_expired", {"status": 401, "hint": "Run auth login-local to refresh"})
                if e.status_code >= 500 and attempt < MAX_RETRIES:
                    last_error = e
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                raise BridgeError(f"api_error_{e.status_code}", {
                    "status": e.status_code, "method": e.method, "body": e.response_body
                })
            except UserFacingError as e:
                raise BridgeError(e.message, e.details)
            except (OSError, URLError) as e:
                if attempt < MAX_RETRIES:
                    last_error = e
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                raise BridgeError("network_error", {"error": str(e)})
        raise BridgeError("max_retries_exceeded", {"last_error": str(last_error)})

    # --- Token check ---

    def token_check(self) -> dict:
        """Check if the current token is valid by making a lightweight API call."""
        try:
            self._call(self._client.list_projects)
            return {"valid": True}
        except BridgeError as e:
            return {"valid": False, "error": e.message, "details": e.details}

    # --- Project operations ---

    def list_projects(self) -> list[dict]:
        data = self._call(self._client.list_projects)
        return data if isinstance(data, list) else []

    def create_project(self, name: str, **kwargs) -> dict:
        payload = {"name": name}
        if "kind" in kwargs:
            payload["kind"] = kwargs["kind"]
        if "view_mode" in kwargs:
            payload["viewMode"] = kwargs["view_mode"]
        data = self._call(self._client.create_project, payload)
        return data if isinstance(data, dict) else {"ok": True}

    def resolve_project_id(self, project_name: str) -> str:
        try:
            return self._client.resolve_project_id(project_name=project_name)
        except UserFacingError as e:
            raise BridgeError(e.message, e.details)
        except Exception as e:
            raise BridgeError("resolve_project_failed", {"project_name": project_name, "error": str(e)})

    def get_project_data(self, project_id: str) -> dict:
        data = self._call(self._client.get_project_data, project_id)
        return data if isinstance(data, dict) else {}

    # --- Task operations ---

    def create_task(self, project_id: str, title: str, **kwargs) -> dict:
        payload: dict[str, Any] = {"projectId": project_id, "title": title}
        field_map = {
            "content": "content",
            "due_date": "dueDate",
            "start_date": "startDate",
            "priority": "priority",
            "tags": "tags",
            "kind": "kind",
            "is_all_day": "isAllDay",
            "time_zone": "timeZone",
            "reminders": "reminders",
            "items": "items",
        }
        for py_key, api_key in field_map.items():
            if py_key in kwargs and kwargs[py_key] is not None:
                payload[api_key] = kwargs[py_key]
        data = self._call(self._client.create_task, payload)
        return data if isinstance(data, dict) else {"ok": True}

    def update_task(self, task_id: str, project_id: str, **kwargs) -> dict:
        payload: dict[str, Any] = {"id": task_id, "projectId": project_id}
        field_map = {
            "title": "title",
            "content": "content",
            "due_date": "dueDate",
            "start_date": "startDate",
            "priority": "priority",
            "tags": "tags",
        }
        for py_key, api_key in field_map.items():
            if py_key in kwargs and kwargs[py_key] is not None:
                payload[api_key] = kwargs[py_key]
        data = self._call(self._client.update_task, task_id, payload)
        return data if isinstance(data, dict) else {"ok": True}

    def complete_task(self, project_id: str, task_id: str) -> dict:
        data = self._call(self._client.complete_task, project_id, task_id)
        return {"ok": True} if data is None else (data if isinstance(data, dict) else {"ok": True})

    def delete_task(self, project_id: str, task_id: str) -> dict:
        data = self._call(self._client.delete_task, project_id, task_id)
        return {"ok": True} if data is None else (data if isinstance(data, dict) else {"ok": True})

    def get_task(self, project_id: str, task_id: str) -> dict:
        data = self._call(self._client.get_task, project_id, task_id)
        return data if isinstance(data, dict) else {}

    def filter_tasks(self, **kwargs) -> list[dict]:
        payload: dict[str, Any] = {}
        if "project_ids" in kwargs:
            payload["projectIds"] = kwargs["project_ids"]
        if "status" in kwargs:
            payload["status"] = kwargs["status"]
        if "start_date" in kwargs:
            payload["startDate"] = kwargs["start_date"]
        if "end_date" in kwargs:
            payload["endDate"] = kwargs["end_date"]
        if "priority" in kwargs:
            payload["priority"] = kwargs["priority"]
        if "tag" in kwargs:
            payload["tag"] = kwargs["tag"]
        data = self._call(self._client.filter_tasks, payload)
        return data if isinstance(data, list) else []

    def list_completed_tasks(self, **kwargs) -> list[dict]:
        payload: dict[str, Any] = {}
        if "project_ids" in kwargs:
            payload["projectIds"] = kwargs["project_ids"]
        if "start_date" in kwargs:
            payload["startDate"] = kwargs["start_date"]
        if "end_date" in kwargs:
            payload["endDate"] = kwargs["end_date"]
        data = self._call(self._client.list_completed_tasks, payload)
        return data if isinstance(data, list) else []
