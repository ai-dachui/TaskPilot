"""Progress tracking: completion rate, overdue items, blocker analysis."""

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
) -> dict:
    """Compute progress stats for a given date (default: today)."""
    project_id = _ensure_project(bridge, config.dida365.project_name)

    # Get pending tasks
    pending_kwargs: dict[str, Any] = {"project_ids": [project_id], "status": [0]}
    effective_date = date if date else "today"
    start, end = _date_range(config.timezone, effective_date)
    pending_kwargs["start_date"] = start
    pending_kwargs["end_date"] = end

    pending_tasks = bridge.filter_tasks(**pending_kwargs)

    # Get completed tasks
    completed_kwargs: dict[str, Any] = {"project_ids": [project_id]}
    completed_kwargs["start_date"] = start
    completed_kwargs["end_date"] = end

    completed_tasks = bridge.list_completed_tasks(**completed_kwargs)

    total = len(pending_tasks) + len(completed_tasks)
    completed_count = len(completed_tasks)
    rate = f"{(completed_count / total * 100):.1f}" if total > 0 else "0.0"

    # Find overdue tasks
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo(config.timezone))
    overdue = []
    for t in pending_tasks:
        due = t.get("dueDate")
        if due and isinstance(due, str):
            try:
                # dida365 returns formats like "2026-04-09T18:00:00+0800"
                # Python's fromisoformat needs ":" in tz offset before 3.11
                normalized = due
                if len(due) >= 5 and due[-5] in "+-" and ":" not in due[-5:]:
                    normalized = due[:-2] + ":" + due[-2:]
                due_dt = datetime.fromisoformat(normalized)
                if due_dt < now:
                    overdue.append({
                        "id": t.get("id", ""),
                        "title": t.get("title", ""),
                        "due_date": due,
                        "overdue_hours": round((now - due_dt).total_seconds() / 3600, 1),
                    })
            except (ValueError, TypeError):
                pass

    # Blockers: overdue + high priority pending
    blockers = []
    for item in overdue:
        blockers.append(f"逾期: {item['title']} (超期 {item['overdue_hours']}h)")
    for t in pending_tasks:
        if t.get("priority", 0) >= 5:
            blockers.append(f"高优先级未完成: {t.get('title', '?')}")

    # Tag stats
    all_tasks = pending_tasks + completed_tasks
    work_count = sum(1 for t in all_tasks if "work" in (t.get("tags") or []))
    life_count = sum(1 for t in all_tasks if "life" in (t.get("tags") or []))
    untagged_count = total - work_count - life_count

    return {
        "total": total,
        "completed": completed_count,
        "pending": len(pending_tasks),
        "overdue": len(overdue),
        "rate": rate,
        "blockers": blockers,
        "work_count": work_count,
        "life_count": life_count,
        "untagged_count": untagged_count,
        "overdue_tasks": overdue,
        "_pending_tasks": pending_tasks,
        "_completed_tasks": completed_tasks,
    }
