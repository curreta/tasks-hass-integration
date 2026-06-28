"""Data model for the Tasks integration.

Mirrors the VTODO-based ``Item`` struct served by the tasks_go backend.
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

_LOGGER = logging.getLogger(__name__)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an RFC3339/ISO timestamp (with trailing Z) into a datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        _LOGGER.debug("Could not parse datetime: %r", value)
        return None


@dataclass
class TaskItem:
    """A single kanban task as returned by the tasks_go API."""

    id: int
    summary: str
    kanban_stage: str
    uid: Optional[str] = None
    description: str = ""
    status: str = "needs_action"
    priority: Optional[int] = None
    due: Optional[datetime] = None
    due_all_day: bool = True
    deadline: Optional[datetime] = None
    duration: Optional[int] = None
    duration_unit: str = "minute"
    completed_at: Optional[datetime] = None
    categories: str = ""
    project: str = ""
    kanban_position: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Computed display strings from the server (best-effort).
    due_display: str = ""
    deadline_display: str = ""
    duration_display: str = ""

    @property
    def is_done(self) -> bool:
        """Whether the task sits in the done stage / is completed."""
        return self.kanban_stage == "done" or self.status == "completed"

    @property
    def tags(self) -> List[str]:
        """Categories split into a clean list."""
        return [t.strip() for t in self.categories.split(",") if t.strip()]

    def due_value(self) -> Optional[object]:
        """Return the due value shaped for HA: a date for all-day, else datetime."""
        if self.due is None:
            return None
        if self.due_all_day:
            return self.due.date()
        return self.due

    def deadline_date(self) -> Optional[date]:
        """Return the deadline as a plain date, if set."""
        if self.deadline is None:
            return None
        return self.deadline.date() if isinstance(self.deadline, datetime) else self.deadline

    @classmethod
    def from_json(cls, data: dict) -> "TaskItem":
        """Build a TaskItem from a tasks_go JSON item."""
        return cls(
            id=data["id"],
            summary=data.get("summary", ""),
            kanban_stage=data.get("kanban_stage", "someday"),
            uid=data.get("uid"),
            description=data.get("description", "") or "",
            status=data.get("status", "needs_action"),
            priority=data.get("priority"),
            due=_parse_dt(data.get("due")),
            due_all_day=data.get("due_all_day", True),
            deadline=_parse_dt(data.get("deadline")),
            duration=data.get("duration"),
            duration_unit=data.get("duration_unit", "minute"),
            completed_at=_parse_dt(data.get("completed_at")),
            categories=data.get("categories", "") or "",
            project=data.get("project", "") or "",
            kanban_position=data.get("kanban_position", 0.0),
            created_at=_parse_dt(data.get("created_at")),
            updated_at=_parse_dt(data.get("updated_at")),
            due_display=data.get("due_display", "") or "",
            deadline_display=data.get("deadline_display", "") or "",
            duration_display=data.get("duration_display", "") or "",
        )

    @classmethod
    def from_json_list(cls, data: List[dict]) -> List["TaskItem"]:
        """Build a list of TaskItems from JSON."""
        return [cls.from_json(item) for item in data]
