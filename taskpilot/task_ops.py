"""Task operations: list, create, update, complete — JSON in/out.

Supports multi-project aggregation via config.managed_projects.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from .dida_bridge import DidaBridge, BridgeError
from .config import Config


def _date_range(tz_name: str, date: str = "today") -> tuple[str, str]:
    """Return start/end ISO strings for a date in the given timezone."""
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


def resolve_managed_project_ids(bridge: DidaBridge, config: Config) -> dict[str, str]:
    """Resolve all managed project names to IDs. Returns {name: id}."""
    result = {}
    for pm in config.managed_projects:
        result[pm.name] = _ensure_project(bridge, pm.name)
    return result


def list_tasks(
    bridge: DidaBridge,
    config: Config,
    *,
    date: Optional[str] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    project: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    """List tasks across managed projects. Filter by project name or category (work/life)."""
    # Determine which projects to query
    if project:
        project_names = [project]
    elif category:
        project_names = [p.name for p in config.managed_projects if p.category == category]
    else:
        project_names = config.all_project_names

    all_tasks = []
    project_id_map = {}

    for pname in project_names:
        project_id = _ensure_project(bridge, pname)
        project_id_map[project_id] = pname

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

        # Also get tasks without due date (they'd be missed by date filter)
        if date:
            no_date_kwargs: dict[str, Any] = {"project_ids": [project_id]}
            if status == "pending":
                no_date_kwargs["status"] = [0]
            elif status == "completed":
                no_date_kwargs["status"] = [2]
            all_project_tasks = bridge.filter_tasks(**no_date_kwargs)
            no_due_tasks = [t for t in all_project_tasks if not t.get("dueDate") and t.get("id") not in {x.get("id") for x in tasks}]
            tasks.extend(no_due_tasks)

        for t in tasks:
            # Find category from config
            cat = "unknown"
            for pm in config.managed_projects:
                if pm.name == pname:
                    cat = pm.category
                    break
            all_tasks.append({
                "id": t.get("id", ""),
                "title": t.get("title", ""),
                "status": "completed" if t.get("status") == 2 else "pending",
                "priority": t.get("priority", 0),
                "due_date": t.get("dueDate"),
                "tags": t.get("tags", []),
                "project_id": t.get("projectId", ""),
                "project_name": pname,
                "category": cat,
            })

    return {"count": len(all_tasks), "tasks": all_tasks}


def create_tasks(
    bridge: DidaBridge,
    config: Config,
    tasks_data: list[dict],
    *,
    project_name: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    """Create multiple tasks. Route to project by name or category."""
    if project_name:
        proj = project_name
    elif category:
        projects = [p.name for p in config.managed_projects if p.category == category]
        proj = projects[0] if projects else config.managed_projects[0].name
    else:
        proj = config.managed_projects[0].name if config.managed_projects else "TaskPilot"

    project_id = _ensure_project(bridge, proj)

    created = []
    errors = []
    for item in tasks_data:
        try:
            # Allow per-task category override
            task_proj = proj
            task_project_id = project_id
            if "category" in item:
                cat_projects = [p.name for p in config.managed_projects if p.category == item["category"]]
                if cat_projects:
                    task_proj = cat_projects[0]
                    task_project_id = _ensure_project(bridge, task_proj)

            result = bridge.create_task(
                task_project_id,
                item["title"],
                due_date=item.get("due"),
                priority=item.get("priority", 0),
                tags=item.get("tags"),
                content=item.get("content"),
                start_date=item.get("start"),
                is_all_day=item.get("is_all_day"),
            )
            created.append({"id": result.get("id", ""), "title": item["title"], "project": task_proj})
        except (BridgeError, KeyError) as e:
            errors.append({"title": item.get("title", "?"), "error": str(e)})

    return {"created": len(created), "items": created, "errors": errors}


def complete_task(bridge: DidaBridge, project_id: str, task_id: str) -> dict:
    return bridge.complete_task(project_id, task_id)


def update_task(bridge: DidaBridge, project_id: str, task_id: str, **kwargs) -> dict:
    return bridge.update_task(task_id, project_id, **kwargs)


def delete_task(bridge: DidaBridge, project_id: str, task_id: str) -> dict:
    return bridge.delete_task(project_id, task_id)
