"""Task operations: list, create, update, complete — JSON in/out."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from .dida_bridge import DidaBridge, BridgeError
from .config import Config


def _date_range(tz_name: str, date: str = "today") -> tuple[str, str]:
    """Return start/end ISO strings for a date in the given timezone.

    ``date`` may be ``"today"`` or an ISO date string like ``"2026-04-10"``.
    The end boundary is the start of the *next* day (exclusive upper bound).
    """
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tz_name)
    if date == "today":
        day = datetime.now(tz).date()
    else:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    from datetime import timedelta
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    end = start + timedelta(days=1)
    fmt = "%Y-%m-%dT%H:%M:%S%z"
    return start.strftime(fmt), end.strftime(fmt)


def _ensure_project(bridge: DidaBridge, project_name: str) -> str:
    """Resolve project by name, create if not found."""
    try:
        return bridge.resolve_project_id(project_name)
    except BridgeError:
        result = bridge.create_project(project_name, kind="TASK", view_mode="list")
        pid = result.get("id", "")
        if not pid:
            raise BridgeError(f"Failed to create project '{project_name}': no id returned")
        return pid


def list_tasks(
    bridge: DidaBridge,
    config: Config,
    *,
    date: Optional[str] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
) -> dict:
    """List tasks, output structured JSON."""
    project_id = _ensure_project(bridge, config.dida365.project_name)

    kwargs: dict[str, Any] = {"project_ids": [project_id]}

    if status == "pending":
        kwargs["status"] = [0]
    elif status == "completed":
        kwargs["status"] = [2]

    if tag:
        kwargs["tag"] = [tag]

    if date:
        start, end = _date_range(config.timezone, date)
        kwargs["start_date"] = start
        kwargs["end_date"] = end

    tasks = bridge.filter_tasks(**kwargs)
    return {
        "count": len(tasks),
        "tasks": [
            {
                "id": t.get("id", ""),
                "title": t.get("title", ""),
                "status": "completed" if t.get("status") == 2 else "pending",
                "priority": t.get("priority", 0),
                "due_date": t.get("dueDate"),
                "tags": t.get("tags", []),
                "project_id": t.get("projectId", ""),
            }
            for t in tasks
        ],
    }


def create_tasks(
    bridge: DidaBridge,
    config: Config,
    tasks_data: list[dict],
    *,
    project_name: Optional[str] = None,
) -> dict:
    """Create multiple tasks from a JSON array. Returns created IDs."""
    proj = project_name or config.dida365.project_name
    project_id = _ensure_project(bridge, proj)

    created = []
    errors = []
    for item in tasks_data:
        try:
            result = bridge.create_task(
                project_id,
                item["title"],
                due_date=item.get("due"),
                priority=item.get("priority", 0),
                tags=item.get("tags"),
                content=item.get("content"),
                start_date=item.get("start"),
                is_all_day=item.get("is_all_day"),
            )
            created.append({"id": result.get("id", ""), "title": item["title"]})
        except (BridgeError, KeyError) as e:
            errors.append({"title": item.get("title", "?"), "error": str(e)})

    return {"created": len(created), "items": created, "errors": errors}


def complete_task(bridge: DidaBridge, project_id: str, task_id: str) -> dict:
    """Complete a single task."""
    return bridge.complete_task(project_id, task_id)


def update_task(
    bridge: DidaBridge,
    project_id: str,
    task_id: str,
    **kwargs,
) -> dict:
    """Update a single task. Accepts title, content, due_date, priority, tags."""
    return bridge.update_task(task_id, project_id, **kwargs)


def delete_task(bridge: DidaBridge, project_id: str, task_id: str) -> dict:
    """Delete a single task."""
    return bridge.delete_task(project_id, task_id)
