"""Configuration loader for TaskPilot."""

from __future__ import annotations

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


DEFAULTS = {
    "timezone": "Asia/Shanghai",
    "work_hours": {"start": "09:00", "end": "18:00"},
    "checkpoints": {"morning": "08:30", "afternoon": "14:00", "evening": "20:00"},
    "dida365": {
        "project_name": "TaskPilot",
        "report_project": "Reports",
        "tags": {"work": "work", "life": "life"},
    },
    "reports_dir": "reports",
    "token_budget": {"checkpoint_max_tokens": 2000},
}


@dataclass
class Dida365Config:
    project_name: str = "TaskPilot"
    report_project: str = "Reports"
    tags: dict = field(default_factory=lambda: {"work": "work", "life": "life"})
    client_id: str = ""
    client_secret: str = ""
    token_path: str = ""


@dataclass
class Config:
    timezone: str = "Asia/Shanghai"
    work_hours_start: str = "09:00"
    work_hours_end: str = "18:00"
    checkpoint_morning: str = "08:30"
    checkpoint_afternoon: str = "14:00"
    checkpoint_evening: str = "20:00"
    reports_dir: str = "reports"
    checkpoint_max_tokens: int = 2000
    dida365: Dida365Config = field(default_factory=Dida365Config)


def load_config(config_path: Optional[str] = None) -> Config:
    """Load config from yaml file, falling back to defaults."""
    if config_path is None:
        config_path = os.environ.get("TASKPILOT_CONFIG", "config.yaml")

    path = Path(config_path)
    raw = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    # Merge with defaults (deep merge for nested dicts)
    merged = {**DEFAULTS, **raw}
    for key in ("work_hours", "checkpoints", "dida365", "token_budget"):
        if key in DEFAULTS:
            merged[key] = {**DEFAULTS[key], **(raw.get(key) or {})}

    wh = merged.get("work_hours", {})
    cp = merged.get("checkpoints", {})
    tb = merged.get("token_budget", {})
    d365 = merged.get("dida365", {})

    dida_cfg = Dida365Config(
        project_name=d365.get("project_name", "TaskPilot"),
        report_project=d365.get("report_project", "Reports"),
        tags=d365.get("tags", {"work": "work", "life": "life"}),
        client_id=d365.get("client_id", os.environ.get("DIDA365_CLIENT_ID", "")),
        client_secret=d365.get("client_secret", os.environ.get("DIDA365_CLIENT_SECRET", "")),
        token_path=d365.get("token_path", os.environ.get("DIDA365_TOKEN_PATH", "")),
    )

    return Config(
        timezone=merged.get("timezone", "Asia/Shanghai"),
        work_hours_start=wh.get("start", "09:00"),
        work_hours_end=wh.get("end", "18:00"),
        checkpoint_morning=cp.get("morning", "08:30"),
        checkpoint_afternoon=cp.get("afternoon", "14:00"),
        checkpoint_evening=cp.get("evening", "20:00"),
        reports_dir=merged.get("reports_dir", "reports"),
        checkpoint_max_tokens=tb.get("checkpoint_max_tokens", 2000),
        dida365=dida_cfg,
    )
