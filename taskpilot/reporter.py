"""Daily report generation: multi-project aggregation, data-only mode for Agent."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from .dida_bridge import DidaBridge, BridgeError
from .config import Config
from .progress import check_progress
from .task_ops import _ensure_project


WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def generate_report(
    bridge: DidaBridge,
    config: Config,
    *,
    date: Optional[str] = None,
    base_dir: Optional[str] = None,
    data_only: bool = False,
) -> dict:
    """Generate daily report.

    If data_only=True, return raw data JSON for Agent to render with intelligence.
    Otherwise, render Markdown + sync to Dida365.
    """
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(config.timezone))
    if date:
        target = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=ZoneInfo(config.timezone))
    else:
        target = now
    date_str = target.strftime("%Y-%m-%d")
    weekday = WEEKDAY_NAMES[target.weekday()]

    # Gather progress data across all managed projects
    progress = check_progress(bridge, config, date="today" if date is None else date)

    pending_tasks = progress.pop("_pending_tasks", [])
    completed_tasks = progress.pop("_completed_tasks", [])

    if data_only:
        # Return structured data for Agent to render with intelligent analysis
        return {
            "date": date_str,
            "weekday": weekday,
            "progress": progress,
            "pending_tasks": [
                {
                    "title": t.get("title", "?"),
                    "priority": t.get("priority", 0),
                    "due_date": t.get("dueDate"),
                    "project": t.get("_project_name", "?"),
                    "category": t.get("_category", "?"),
                    "tags": t.get("tags", []),
                }
                for t in pending_tasks
            ],
            "completed_tasks": [
                {
                    "title": t.get("title", "?"),
                    "priority": t.get("priority", 0),
                    "project": t.get("_project_name", "?"),
                    "category": t.get("_category", "?"),
                    "tags": t.get("tags", []),
                }
                for t in completed_tasks
            ],
        }

    # Full render mode: Markdown + sync
    completed_lines = _render_task_list(completed_tasks) or "- (无)"
    in_progress = [t for t in pending_tasks if t.get("priority", 0) >= 3]
    in_progress_lines = _render_task_list(in_progress) or "- (无)"
    pending_other = [t for t in pending_tasks if t.get("priority", 0) < 3]
    pending_lines = _render_task_list(pending_other) or "- (无)"

    blockers_text = "\n".join(f"- {b}" for b in progress["blockers"]) if progress["blockers"] else "- 无阻塞"

    # Per-project breakdown
    project_breakdown = "\n".join(
        f"- {ps['project']}({ps['category']}): {ps['completed']}/{ps['total']}"
        for ps in progress.get("project_stats", [])
    ) or "- (无项目数据)"

    md = _build_markdown(
        date=date_str,
        weekday=weekday,
        completed_count=progress["completed"],
        total_count=progress["total"],
        completed_tasks=completed_lines,
        in_progress_tasks=in_progress_lines,
        pending_tasks=pending_lines,
        completion_rate=progress["rate"],
        overdue_count=progress["overdue"],
        work_count=progress["work_count"],
        life_count=progress["life_count"],
        no_due_count=progress.get("no_due_count", 0),
        project_breakdown=project_breakdown,
        blockers_analysis=blockers_text,
        tomorrow_suggestions="(由 Agent 根据以上数据生成)",
    )

    # Save to file
    reports_dir = Path(base_dir or ".") / config.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{date_str}.md"
    report_path.write_text(md, encoding="utf-8")

    # Sync to Dida365
    sync_result = _sync_to_dida(bridge, config, date_str, md)

    return {
        "report_path": str(report_path),
        "date": date_str,
        "synced": sync_result.get("ok", False),
        "progress": progress,
    }


def _render_task_list(tasks: list[dict]) -> str:
    lines = []
    for t in tasks:
        title = t.get("title", "?")
        priority = t.get("priority", 0)
        project = t.get("_project_name", "")
        tags = t.get("tags") or []
        tag_str = " ".join(f"#{tag}" for tag in tags) if tags else ""
        pri_str = {5: "[高]", 3: "[中]", 1: "[低]"}.get(priority, "")
        proj_str = f"[{project}]" if project else ""
        line = f"- {pri_str} {title} {proj_str}"
        if tag_str:
            line += f" {tag_str}"
        lines.append(line.strip())
    return "\n".join(lines)


def _build_markdown(**kwargs) -> str:
    return f"""# 日报: {kwargs['date']} ({kwargs['weekday']})

## 完成 ({kwargs['completed_count']}/{kwargs['total_count']})
{kwargs['completed_tasks']}

## 进行中（优先级≥3）
{kwargs['in_progress_tasks']}

## 未开始/低优先级
{kwargs['pending_tasks']}

## 各项目进度
{kwargs['project_breakdown']}

## 数据分析
- 完成率: {kwargs['completion_rate']}%
- 逾期任务: {kwargs['overdue_count']} 个
- 工作任务: {kwargs['work_count']} | 生活任务: {kwargs['life_count']}
- 无截止日期: {kwargs['no_due_count']} 个

## 问题与阻塞
{kwargs['blockers_analysis']}

## 明日建议
{kwargs['tomorrow_suggestions']}
"""


def _sync_to_dida(bridge: DidaBridge, config: Config, date_str: str, content: str) -> dict:
    try:
        report_project_id = _ensure_project(bridge, config.dida365.report_project)
        title = f"日报: {date_str}"

        existing = bridge.filter_tasks(project_ids=[report_project_id])
        for task in existing:
            if task.get("title") == title:
                bridge.update_task(task["id"], report_project_id, content=content)
                return {"ok": True, "id": task["id"], "updated": True}

        result = bridge.create_task(
            report_project_id,
            title,
            content=content,
            kind="NOTE",
        )
        return {"ok": True, "id": result.get("id", "")}
    except BridgeError as e:
        return {"ok": False, "error": e.message}
