"""Calendar platform for the Tasks integration.

Todoist-style: one unified "All Tasks" calendar plus optional per-project
calendars, all keyed to each task's *do-date* (``due``). Tasks are one-off
VTODOs — there is no recurrence to expand.

All-day dues produce an all-day event (so HA fires at local midnight); timed
dues produce a timed event running ``due`` → ``due + duration`` (or +1h), so
HA's native calendar triggers fire at the do-date/time.
"""
import logging
from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_CREATE_PROJECT_LISTS, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up calendars: one unified calendar plus optional per-project ones.

    The legacy ``calendar_date_field`` option (due vs deadline) is intentionally
    ignored — calendars now always key on ``due`` (the do-date). Existing config
    entries that still carry the key load fine; the key is simply unused.
    """
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities: list[TasksCalendarBase] = [TasksUnifiedCalendar(coordinator, config_entry)]

    if config_entry.data.get(CONF_CREATE_PROJECT_LISTS, False):
        projects = sorted({item.project for item in (coordinator.data or []) if item.project})
        for project in projects:
            entities.append(TasksProjectCalendar(coordinator, config_entry, project))

    async_add_entities(entities)


def _priority_label(priority: int | None) -> str | None:
    """Map an int priority to a Todoist-style Pn label (1→P1 … ≥5→P4)."""
    if not priority or priority < 1:
        return None
    return f"P{min(priority, 4)}"


def _duration_delta(item) -> timedelta | None:
    """Return a task's duration as a timedelta, honouring its unit."""
    if not item.duration:
        return None
    unit = (item.duration_unit or "minute").lower()
    if unit.startswith("hour"):
        return timedelta(hours=item.duration)
    if unit.startswith("day"):
        return timedelta(days=item.duration)
    return timedelta(minutes=item.duration)


def _to_dt(value) -> datetime:
    """Normalize a date or (possibly naive) datetime to an aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else dt_util.as_local(value)
    return dt_util.start_of_local_day(value)


class TasksCalendarBase(CoordinatorEntity, CalendarEntity):
    """Base calendar of task do-dates (``due``)."""

    _attr_icon = "mdi:calendar-check"

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry

    def _filter(self, items):
        """Active tasks visible on this calendar. Override in subclasses."""
        return [i for i in items if not i.is_done]

    def _items(self):
        """Items with a ``due`` that belong on this calendar."""
        return [i for i in self._filter(self.coordinator.data or []) if i.due is not None]

    def _event_for(self, item) -> CalendarEvent | None:
        if item.due is None:
            return None

        summary = item.summary
        label = _priority_label(item.priority)
        if label:
            summary = f"{label} · {summary}"

        description = item.description or ""
        if item.project:
            description = f"Project: {item.project}\n{description}".strip()

        if item.due_all_day:
            day = item.due.date() if isinstance(item.due, datetime) else item.due
            start: date | datetime = day
            end: date | datetime = day + timedelta(days=1)
        else:
            start = _to_dt(item.due)
            end = start + (_duration_delta(item) or timedelta(hours=1))

        return CalendarEvent(
            summary=summary,
            start=start,
            end=end,
            description=description,
            uid=f"tasks_{item.id}",
        )

    def _sorted_events(self):
        """All (event, item) pairs on this calendar, sorted by start."""
        pairs = []
        for item in self._items():
            event = self._event_for(item)
            if event is not None:
                pairs.append((event, item))
        pairs.sort(key=lambda p: _to_dt(p[0].start))
        return pairs

    def _upcoming(self):
        """(event, item) pairs whose event hasn't ended yet, soonest first."""
        now = dt_util.now()
        return [p for p in self._sorted_events() if _to_dt(p[0].end) > now]

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        upcoming = self._upcoming()
        return upcoming[0][0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return events that overlap the requested range."""
        events: list[CalendarEvent] = []
        for event, _item in self._sorted_events():
            start = _to_dt(event.start)
            end = _to_dt(event.end)
            if start < end_date and end > start_date:
                events.append(event)
        return events

    @property
    def extra_state_attributes(self):
        """Todoist-style attributes reflecting the current/next event."""
        now = dt_util.now()
        today = now.date()
        upcoming = self._upcoming()
        attrs = {
            "config_entry_id": self._config_entry.entry_id,
            "all_tasks": [event.summary for event, _ in upcoming],
            "priority": None,
            "overdue": False,
            "due_today": False,
        }
        if upcoming:
            _event, item = upcoming[0]
            start = _to_dt(_event.start)
            attrs["priority"] = item.priority
            attrs["overdue"] = start < now
            attrs["due_today"] = start.date() == today
        return attrs


class TasksUnifiedCalendar(TasksCalendarBase):
    """All active tasks with a do-date, across every project."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_calendar"
        self._attr_name = "Tasks"

    def _filter(self, items):
        return [i for i in items if not i.is_done]


class TasksProjectCalendar(TasksCalendarBase):
    """Active tasks with a do-date for a single project."""

    def __init__(self, coordinator, config_entry: ConfigEntry, project: str) -> None:
        super().__init__(coordinator, config_entry)
        self._project = project
        slug = project.lower().replace(" ", "_")
        self._attr_unique_id = f"{config_entry.entry_id}_calendar_project_{slug}"
        self._attr_name = f"Tasks: {project}"

    def _filter(self, items):
        return [i for i in items if not i.is_done and i.project == self._project]
