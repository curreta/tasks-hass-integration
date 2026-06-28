"""Calendar platform for the Tasks integration.

Projects each task's due (or deadline) date as a one-day event. Tasks are
one-off VTODOs — there is no recurrence to expand.
"""
import logging
from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CALENDAR_DATE_FIELD, DEFAULT_CALENDAR_DATE_FIELD, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tasks calendar entity."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    field = config_entry.data.get(CONF_CALENDAR_DATE_FIELD, DEFAULT_CALENDAR_DATE_FIELD)
    async_add_entities([TasksCalendar(coordinator, config_entry, field)])


def _as_date(value) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


class TasksCalendar(CoordinatorEntity, CalendarEntity):
    """Calendar of task due/deadline dates."""

    _attr_icon = "mdi:calendar-check"

    def __init__(self, coordinator, config_entry: ConfigEntry, field: str) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._field = field
        self._attr_unique_id = f"{config_entry.entry_id}_calendar"
        self._attr_name = "Tasks"

    def _date_for(self, item) -> date | None:
        return _as_date(item.deadline if self._field == "deadline" else item.due)

    def _event_for(self, item) -> CalendarEvent | None:
        day = self._date_for(item)
        if day is None:
            return None
        description = item.description or ""
        if item.project:
            description = f"Project: {item.project}\n{description}".strip()
        return CalendarEvent(
            summary=item.summary,
            start=day,
            end=day + timedelta(days=1),
            description=description,
            uid=f"tasks_{item.id}",
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        today = date.today()
        upcoming = []
        for item in self.coordinator.data or []:
            day = self._date_for(item)
            if day is not None and day >= today:
                upcoming.append(item)
        if not upcoming:
            return None
        upcoming.sort(key=self._date_for)
        return self._event_for(upcoming[0])

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return events that fall within a date range."""
        range_start = start_date.date()
        range_end = end_date.date()
        events: list[CalendarEvent] = []
        for item in self.coordinator.data or []:
            day = self._date_for(item)
            if day is not None and range_start <= day < range_end:
                event = self._event_for(item)
                if event:
                    events.append(event)
        return events
