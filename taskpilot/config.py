"""Configuration loader for TaskPilot."""

from __future__ import annotations

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProjectMapping:
    """A managed project: name in Dida365 + category (work/life)."""
    name: str
    category: str  # "work" or "life"


@dataclass
class Dida365Config:
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
    checkpoint_summary: str = "23:30"
    reports_dir: str = "reports"
    state_file: str = "state.json"
    checkpoint_max_tokens: int = 2000
    managed_projects: list[ProjectMapping] = field(default_factory=list)
    dida365: Dida365Config = field(default_factory=Dida365Config)

    @property
    def work_projects(self) -> list[ProjectMapping]:
        return [p for p in self.managed_projects if p.category == "work"]

    @property
    def life_projects(self) -> list[ProjectMapping]:
        return [p for p in self.managed_projects if p.category == "life"]

    @property
    def all_project_names(self) -> list[str]:
        return [p.name for p in self.managed_projects]


DEFAULTS = {
    "timezone": "Asia/Shanghai",
    "work_hours": {"start": "09:00", "end": "18:00"},
    "checkpoints": {"morning": "08:30", "afternoon": "14:00", "evening": "20:00", "summary": "23:30"},
    "managed_projects": [
        {"name": "工作", "category": "work"},
        {"name": "fy", "category": "life"},
    ],
    "dida365": {
        "report_project": "Reports",
        "tags": {"work": "work", "life": "life"},
    },
    "reports_dir": "reports",
    "state_file": "state.json",
    "token_budget": {"checkpoint_max_tokens": 2000},
}


def load_config(config_path: Optional[str] = None) -> Config:
    """Load config from yaml file, falling back to defaults."""
    if config_path is None:
        config_path = os.environ.get("TASKPILOT_CONFIG", "config.yaml")

    path = Path(config_path)
    raw = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    # Merge with defaults
    merged = {**DEFAULTS, **raw}
    for key in ("work_hours", "checkpoints", "dida365", "token_budget"):
        if key in DEFAULTS:
            merged[key] = {**DEFAULTS[key], **(raw.get(key) or {})}

    wh = merged.get("work_hours", {})
    cp = merged.get("checkpoints", {})
    tb = merged.get("token_budget", {})
    d365 = merged.get("dida365", {})

    # Parse managed_projects
    raw_projects = merged.get("managed_projects", DEFAULTS["managed_projects"])
    managed_projects = [
        ProjectMapping(name=p["name"], category=p.get("category", "work"))
        for p in raw_projects
    ]

    dida_cfg = Dida365Config(
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
        checkpoint_summary=cp.get("summary", "23:30"),
        reports_dir=merged.get("reports_dir", "reports"),
        state_file=merged.get("state_file", "state.json"),
        checkpoint_max_tokens=tb.get("checkpoint_max_tokens", 2000),
        managed_projects=managed_projects,
        dida365=dida_cfg,
    )
