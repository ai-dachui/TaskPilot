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
    result = list_tasks(
        bridge, config,
        date=args.date, status=args.status, tag=args.tag,
        project=args.project, category=args.category,
    )
    _json_out(result)


def cmd_tasks_create(args, bridge, config):
    from .task_ops import create_tasks
    raw = sys.stdin.read()
    try:
        tasks_data = json.loads(raw)
    except json.JSONDecodeError as e:
        _error_out("invalid_json", {"error": str(e)})
        sys.exit(1)
    if not isinstance(tasks_data, list):
        _error_out("expected_array", {"got": type(tasks_data).__name__})
        sys.exit(1)
    result = create_tasks(
        bridge, config, tasks_data,
        project_name=args.project, category=args.category,
    )
    _json_out(result)


def cmd_tasks_complete(args, bridge, config):
    from .task_ops import complete_task, _ensure_project
    if args.project_id:
        project_id = args.project_id
    else:
        project_name = args.project or config.managed_projects[0].name
        project_id = _ensure_project(bridge, project_name)
    result = complete_task(bridge, project_id, args.id)
    _json_out(result)


def cmd_tasks_update(args, bridge, config):
    from .task_ops import update_task, _ensure_project
    if args.project_id:
        project_id = args.project_id
    else:
        project_name = args.project or config.managed_projects[0].name
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
        project_name = args.project or config.managed_projects[0].name
        project_id = _ensure_project(bridge, project_name)
    result = delete_task(bridge, project_id, args.id)
    _json_out(result)


def cmd_progress(args, bridge, config):
    from .progress import check_progress
    result = check_progress(bridge, config, date=args.date, category=args.category)
    _json_out(result)


def cmd_forecast(args, bridge, config):
    from .progress import forecast
    result = forecast(bridge, config, days=args.days)
    _json_out(result)


def cmd_report(args, bridge, config):
    from .reporter import generate_report
    result = generate_report(
        bridge, config,
        date=args.date, base_dir=args.base_dir,
        data_only=args.data_only,
    )
    _json_out(result)


def cmd_state(args, bridge, config):
    from .state import load_state
    state = load_state(config)
    _json_out(state.to_dict())


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
    tl.add_argument("--date", default="today")
    tl.add_argument("--status", default=None)
    tl.add_argument("--tag", default=None)
    tl.add_argument("--project", default=None, help="Filter by project name")
    tl.add_argument("--category", default=None, help="Filter by category: work or life")
    tl.set_defaults(handler=cmd_tasks_list)

    # tasks create
    tcr = tasks_sub.add_parser("create", help="Create tasks from JSON stdin")
    tcr.add_argument("--project", default=None, help="Target project name")
    tcr.add_argument("--category", default=None, help="Target category: work or life")
    tcr.set_defaults(handler=cmd_tasks_create)

    # tasks complete
    tco = tasks_sub.add_parser("complete", help="Complete a task")
    tco.add_argument("--id", required=True)
    tco.add_argument("--project", default=None)
    tco.add_argument("--project-id", default=None)
    tco.set_defaults(handler=cmd_tasks_complete)

    # tasks update
    tu = tasks_sub.add_parser("update", help="Update a task")
    tu.add_argument("--id", required=True)
    tu.add_argument("--project", default=None)
    tu.add_argument("--project-id", default=None)
    tu.add_argument("--title", default=None)
    tu.add_argument("--priority", type=int, default=None)
    tu.add_argument("--due", default=None)
    tu.add_argument("--tags", nargs="*", default=None)
    tu.add_argument("--content", default=None)
    tu.set_defaults(handler=cmd_tasks_update)

    # tasks delete
    td = tasks_sub.add_parser("delete", help="Delete a task")
    td.add_argument("--id", required=True)
    td.add_argument("--project", default=None)
    td.add_argument("--project-id", default=None)
    td.set_defaults(handler=cmd_tasks_delete)

    # progress
    pg = sub.add_parser("progress", help="Check progress stats")
    pg.add_argument("--date", default="today")
    pg.add_argument("--category", default=None, help="Filter: work or life")
    pg.set_defaults(handler=cmd_progress)

    # forecast
    fc = sub.add_parser("forecast", help="Look-ahead risk alerts")
    fc.add_argument("--days", type=int, default=7)
    fc.set_defaults(handler=cmd_forecast)

    # report
    rp = sub.add_parser("report", help="Generate daily report")
    rp.add_argument("--date", default=None)
    rp.add_argument("--base-dir", default=".")
    rp.add_argument("--data-only", action="store_true", help="Output raw data JSON for Agent rendering")
    rp.set_defaults(handler=cmd_report)

    # state
    st = sub.add_parser("state", help="Show current state")
    st.set_defaults(handler=cmd_state)

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
