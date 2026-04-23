"""State persistence: checkpoint tracking, interaction history, trends."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import Config


class DailyState:
    """Tracks what happened today: checkpoints, interactions, completions."""

    def __init__(self):
        self.date: str = ""
        self.checkpoints_done: list[str] = []  # e.g. ["morning", "afternoon"]
        self.last_interaction: Optional[str] = None  # ISO timestamp
        self.tasks_created: int = 0
        self.tasks_completed: int = 0
        self.report_generated: bool = False

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "checkpoints_done": self.checkpoints_done,
            "last_interaction": self.last_interaction,
            "tasks_created": self.tasks_created,
            "tasks_completed": self.tasks_completed,
            "report_generated": self.report_generated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DailyState":
        s = cls()
        s.date = data.get("date", "")
        s.checkpoints_done = data.get("checkpoints_done", [])
        s.last_interaction = data.get("last_interaction")
        s.tasks_created = data.get("tasks_created", 0)
        s.tasks_completed = data.get("tasks_completed", 0)
        s.report_generated = data.get("report_generated", False)
        return s


class AppState:
    """Persistent state across days."""

    def __init__(self):
        self.today: DailyState = DailyState()
        self.recent_rates: list[dict] = []  # [{date, rate, total, completed}] last 7 days
        self.streak: int = 0  # consecutive days with >50% completion

    def to_dict(self) -> dict:
        return {
            "today": self.today.to_dict(),
            "recent_rates": self.recent_rates,
            "streak": self.streak,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppState":
        s = cls()
        s.today = DailyState.from_dict(data.get("today", {}))
        s.recent_rates = data.get("recent_rates", [])
        s.streak = data.get("streak", 0)
        return s


def _state_path(config: Config) -> Path:
    return Path(config.state_file)


def load_state(config: Config) -> AppState:
    """Load state from disk. Reset daily state if date changed."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo(config.timezone))
    today_str = now.strftime("%Y-%m-%d")

    path = _state_path(config)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            state = AppState.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            state = AppState()
    else:
        state = AppState()

    # Day rollover: archive yesterday, reset today
    if state.today.date and state.today.date != today_str:
        # Archive yesterday's rate
        state.recent_rates.append({
            "date": state.today.date,
            "checkpoints_done": len(state.today.checkpoints_done),
            "tasks_created": state.today.tasks_created,
            "tasks_completed": state.today.tasks_completed,
            "report_generated": state.today.report_generated,
        })
        # Keep only last 7 days
        state.recent_rates = state.recent_rates[-7:]
        # Reset daily
        state.today = DailyState()

    state.today.date = today_str
    return state


def save_state(config: Config, state: AppState) -> None:
    """Persist state to disk."""
    path = _state_path(config)
    path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def mark_checkpoint(config: Config, checkpoint_name: str) -> None:
    """Mark a checkpoint as done for today."""
    state = load_state(config)
    if checkpoint_name not in state.today.checkpoints_done:
        state.today.checkpoints_done.append(checkpoint_name)
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo(config.timezone))
    state.today.last_interaction = now.isoformat()
    save_state(config, state)


def mark_interaction(config: Config) -> None:
    """Record a user interaction timestamp."""
    state = load_state(config)
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo(config.timezone))
    state.today.last_interaction = now.isoformat()
    save_state(config, state)


def get_missed_checkpoints(config: Config) -> list[str]:
    """Return checkpoints that should have run by now but haven't."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo(config.timezone))
    current_time = now.strftime("%H:%M")

    state = load_state(config)
    missed = []

    checkpoint_map = {
        "morning": config.checkpoint_morning,
        "afternoon": config.checkpoint_afternoon,
        "evening": config.checkpoint_evening,
        "summary": config.checkpoint_summary,
    }

    for name, scheduled_time in checkpoint_map.items():
        if current_time > scheduled_time and name not in state.today.checkpoints_done:
            missed.append(name)

    return missed
