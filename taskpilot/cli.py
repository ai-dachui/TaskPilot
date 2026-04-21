"""TaskPilot CLI — unified entry point for all operations."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from .config import load_config
from .dida_bridge import DidaBridge, BridgeError


def _json_out(data, file=sys.stdout):
    file.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _error_out(message: str, details=None):
    _json_out({"error": message, **({"details": details} if details else {})}, file=sys.stderr)


def cmd_token_check(args, bridge, config):
    _json_out(bridge.token_check())


def cmd_tasks_list(args, bridge, config):
    from .task_ops import list_tasks
    result = list_tasks(bridge, config, date=args.date, status=args.status, tag=args.tag)
    _json_out(result)


def cmd_tasks_create(args, bridge, config):
    from .task_ops import create_tasks
    # Read JSON from stdin
    raw = sys.stdin.read()
    try:
        tasks_data = json.loads(raw)
    except json.JSONDecodeError as e:
        _error_out("invalid_json", {"error": str(e)})
        sys.exit(1)
    if not isinstance(tasks_data, list):
        _error_out("expected_array", {"got": type(tasks_data).__name__})
        sys.exit(1)
    result = create_tasks(bridge, config, tasks_data, project_name=args.project)
    _json_out(result)


def cmd_tasks_complete(args, bridge, config):
    from .task_ops import complete_task, _ensure_project
    if args.project_id:
        project_id = args.project_id
    else:
        project_name = args.project or config.dida365.project_name
        project_id = _ensure_project(bridge, project_name)
    result = complete_task(bridge, project_id, args.id)
    _json_out(result)


def cmd_tasks_update(args, bridge, config):
    from .task_ops import update_task, _ensure_project
    if args.project_id:
        project_id = args.project_id
    else:
        project_name = args.project or config.dida365.project_name
        project_id = _ensure_project(bridge, project_name)
    kwargs = {}
    if args.title is not None:
        kwargs["title"] = args.title
    if args.priority is not None:
        kwargs["priority"] = args.priority
    if args.due is not None:
        kwargs["due_date"] = args.due
    if args.tags is not None:
        kwargs["tags"] = args.tags
    if args.content is not None:
        kwargs["content"] = args.content
    result = update_task(bridge, project_id, args.id, **kwargs)
    _json_out(result)


def cmd_tasks_delete(args, bridge, config):
    from .task_ops import delete_task, _ensure_project
    if args.project_id:
        project_id = args.project_id
    else:
        project_name = args.project or config.dida365.project_name
        project_id = _ensure_project(bridge, project_name)
    result = delete_task(bridge, project_id, args.id)
    _json_out(result)


def cmd_progress(args, bridge, config):
    from .progress import check_progress
    result = check_progress(bridge, config, date=args.date)
    _json_out(result)


def cmd_report(args, bridge, config):
    from .reporter import generate_report
    result = generate_report(bridge, config, date=args.date, base_dir=args.base_dir)
    _json_out(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="taskpilot", description="TaskPilot CLI")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--dida-config-dir", default=None, help="dida365-openapi config dir")

    sub = parser.add_subparsers(dest="command", required=True)

    # token-check
    tc = sub.add_parser("token-check", help="Check OAuth token validity")
    tc.set_defaults(handler=cmd_token_check)

    # tasks
    tasks_parser = sub.add_parser("tasks", help="Task operations")
    tasks_sub = tasks_parser.add_subparsers(dest="tasks_command", required=True)

    # tasks list
    tl = tasks_sub.add_parser("list", help="List tasks")
    tl.add_argument("--date", default="today", help="Date filter: today or YYYY-MM-DD")
    tl.add_argument("--status", default=None, help="Status filter: pending or completed")
    tl.add_argument("--tag", default=None, help="Tag filter")
    tl.set_defaults(handler=cmd_tasks_list)

    # tasks create
    tcr = tasks_sub.add_parser("create", help="Create tasks from JSON stdin")
    tcr.add_argument("--project", default=None, help="Project name override")
    tcr.set_defaults(handler=cmd_tasks_create)

    # tasks complete
    tco = tasks_sub.add_parser("complete", help="Complete a task")
    tco.add_argument("--id", required=True, help="Task ID")
    tco.add_argument("--project", default=None, help="Project name (resolved automatically)")
    tco.add_argument("--project-id", default=None, help="Project ID (shortcut, skips resolution)")
    tco.set_defaults(handler=cmd_tasks_complete)

    # tasks update
    tu = tasks_sub.add_parser("update", help="Update a task")
    tu.add_argument("--id", required=True, help="Task ID")
    tu.add_argument("--project", default=None, help="Project name")
    tu.add_argument("--project-id", default=None, help="Project ID (shortcut)")
    tu.add_argument("--title", default=None, help="New title")
    tu.add_argument("--priority", type=int, default=None, help="New priority (0-5)")
    tu.add_argument("--due", default=None, help="New due date (ISO format)")
    tu.add_argument("--tags", nargs="*", default=None, help="New tags")
    tu.add_argument("--content", default=None, help="New description")
    tu.set_defaults(handler=cmd_tasks_update)

    # tasks delete
    td = tasks_sub.add_parser("delete", help="Delete a task")
    td.add_argument("--id", required=True, help="Task ID")
    td.add_argument("--project", default=None, help="Project name")
    td.add_argument("--project-id", default=None, help="Project ID (shortcut)")
    td.set_defaults(handler=cmd_tasks_delete)

    # progress
    pg = sub.add_parser("progress", help="Check progress stats")
    pg.add_argument("--date", default="today", help="Date: today or YYYY-MM-DD")
    pg.set_defaults(handler=cmd_progress)

    # report
    rp = sub.add_parser("report", help="Generate daily report")
    rp.add_argument("--date", default=None, help="Date: YYYY-MM-DD (default: today)")
    rp.add_argument("--base-dir", default=".", help="Base directory for reports")
    rp.set_defaults(handler=cmd_report)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        bridge = DidaBridge(config_dir=args.dida_config_dir)
        args.handler(args, bridge, config)
        return 0
    except BridgeError as e:
        _error_out(e.message, e.details)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        _error_out("internal_error", {"type": type(e).__name__, "error": str(e)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
