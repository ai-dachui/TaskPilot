"""Progress tracking: multi-project aggregation, overdue detection, forecast."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .dida_bridge import DidaBridge, BridgeError
from .config import Config
from .task_ops import _ensure_project, _date_range


def check_progress(
    bridge: DidaBridge,
    config: Config,
    *,
    date: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    """Compute progress stats across managed projects."""
    # Determine which projects to query
    if category:
        projects = [(p.name, p.category) for p in config.managed_projects if p.category == category]
    else:
        projects = [(p.name, p.category) for p in config.managed_projects]

    effective_date = date if date else "today"
    start, end = _date_range(config.timezone, effective_date)

    all_pending = []
    all_completed = []
    project_stats = []

    for pname, pcat in projects:
        project_id = _ensure_project(bridge, pname)

        # Pending tasks with due date in range
        pending_kwargs: dict[str, Any] = {
            "project_ids": [project_id], "status": [0],
            "start_date": start, "end_date": end,
        }
        pending_tasks = bridge.filter_tasks(**pending_kwargs)

        # Also get pending tasks without due date
        all_pending_kwargs: dict[str, Any] = {"project_ids": [project_id], "status": [0]}
        all_project_pending = bridge.filter_tasks(**all_pending_kwargs)
        no_due_pending = [
            t for t in all_project_pending
            if not t.get("dueDate") and t.get("id") not in {x.get("id") for x in pending_tasks}
        ]
        pending_tasks.extend(no_due_pending)

        # Completed tasks
        completed_kwargs: dict[str, Any] = {
            "project_ids": [project_id],
            "start_date": start, "end_date": end,
        }
        completed_tasks = bridge.list_completed_tasks(**completed_kwargs)

        # Tag each task with project info
        for t in pending_tasks:
            t["_project_name"] = pname
            t["_category"] = pcat
        for t in completed_tasks:
            t["_project_name"] = pname
            t["_category"] = pcat

        all_pending.extend(pending_tasks)
        all_completed.extend(completed_tasks)

        ptotal = len(pending_tasks) + len(completed_tasks)
        project_stats.append({
            "project": pname,
            "category": pcat,
            "total": ptotal,
            "completed": len(completed_tasks),
            "pending": len(pending_tasks),
        })

    total = len(all_pending) + len(all_completed)
    completed_count = len(all_completed)
    rate = f"{(completed_count / total * 100):.1f}" if total > 0 else "0.0"

    # Overdue detection
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo(config.timezone))
    overdue = _find_overdue(all_pending, now)

    # Blockers
    blockers = []
    for item in overdue:
        blockers.append(f"逾期: {item['title']} [{item['project']}] (超期 {item['overdue_hours']}h)")
    for t in all_pending:
        if t.get("priority", 0) >= 5:
            blockers.append(f"高优先级未完成: {t.get('title', '?')} [{t.get('_project_name', '?')}]")

    # Category stats
    work_count = sum(1 for t in (all_pending + all_completed) if t.get("_category") == "work")
    life_count = sum(1 for t in (all_pending + all_completed) if t.get("_category") == "life")

    # No-due-date tasks count
    no_due_count = sum(1 for t in all_pending if not t.get("dueDate"))

    return {
        "total": total,
        "completed": completed_count,
        "pending": len(all_pending),
        "overdue": len(overdue),
        "rate": rate,
        "blockers": blockers,
        "work_count": work_count,
        "life_count": life_count,
        "no_due_count": no_due_count,
        "overdue_tasks": overdue,
        "project_stats": project_stats,
        "_pending_tasks": all_pending,
        "_completed_tasks": all_completed,
    }


def forecast(
    bridge: DidaBridge,
    config: Config,
    *,
    days: int = 7,
) -> dict:
    """Look ahead N days: deadline clusters, workload distribution, risk alerts."""
    from zoneinfo import ZoneInfo
    from datetime import timedelta

    tz = ZoneInfo(config.timezone)
    now = datetime.now(tz)
    alerts = []
    daily_load = {}

    for pname, pcat in [(p.name, p.category) for p in config.managed_projects]:
        project_id = _ensure_project(bridge, pname)
        start = now.strftime("%Y-%m-%dT%H:%M:%S%z")
        end_dt = now + timedelta(days=days)
        end = end_dt.strftime("%Y-%m-%dT%H:%M:%S%z")

        tasks = bridge.filter_tasks(project_ids=[project_id], status=[0], start_date=start, end_date=end)

        for t in tasks:
            due = t.get("dueDate")
            if due and isinstance(due, str):
                try:
                    normalized = due
                    if len(due) >= 5 and due[-5] in "+-" and ":" not in due[-5:]:
                        normalized = due[:-2] + ":" + due[-2:]
                    due_dt = datetime.fromisoformat(normalized)
                    day_key = due_dt.strftime("%Y-%m-%d")
                    if day_key not in daily_load:
                        daily_load[day_key] = []
                    daily_load[day_key].append({
                        "title": t.get("title", "?"),
                        "priority": t.get("priority", 0),
                        "project": pname,
                        "category": pcat,
                    })
                except (ValueError, TypeError):
                    pass

    # Detect deadline clusters (3+ tasks on same day)
    for day, tasks in daily_load.items():
        if len(tasks) >= 3:
            alerts.append({
                "type": "deadline_cluster",
                "date": day,
                "count": len(tasks),
                "tasks": [t["title"] for t in tasks],
            })

    # Detect high-priority concentration
    for day, tasks in daily_load.items():
        high_pri = [t for t in tasks if t["priority"] >= 5]
        if len(high_pri) >= 2:
            alerts.append({
                "type": "high_priority_cluster",
                "date": day,
                "count": len(high_pri),
                "tasks": [t["title"] for t in high_pri],
            })

    return {
        "forecast_days": days,
        "daily_load": {k: len(v) for k, v in daily_load.items()},
        "daily_detail": daily_load,
        "alerts": alerts,
        "total_upcoming": sum(len(v) for v in daily_load.values()),
    }


def _find_overdue(pending_tasks: list[dict], now: datetime) -> list[dict]:
    """Find overdue tasks from a list of pending tasks."""
    overdue = []
    for t in pending_tasks:
        due = t.get("dueDate")
        if due and isinstance(due, str):
            try:
                normalized = due
                if len(due) >= 5 and due[-5] in "+-" and ":" not in due[-5:]:
                    normalized = due[:-2] + ":" + due[-2:]
                due_dt = datetime.fromisoformat(normalized)
                if due_dt < now:
                    overdue.append({
                        "id": t.get("id", ""),
                        "title": t.get("title", ""),
                        "project": t.get("_project_name", "?"),
                        "due_date": due,
                        "overdue_hours": round((now - due_dt).total_seconds() / 3600, 1),
                    })
            except (ValueError, TypeError):
                pass
    return overdue
