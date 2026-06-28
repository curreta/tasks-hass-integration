"""Sensor platform for the Tasks integration.

Exposes a count sensor per active kanban stage, a "due today" count, and a
"next due" timestamp — useful for dashboards and reminder automations.
"""
import logging
from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ACTIVE_STAGES, DOMAIN

_LOGGER = logging.getLogger(__name__)

_STAGE_LABELS = {
    "someday": "Someday",
    "upcoming": "Upcoming",
    "ready": "Ready",
    "in_progress": "In Progress",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the stage count, due-today, and next-due sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities: list[CoordinatorEntity] = [
        TasksStageSensor(coordinator, config_entry, stage) for stage in ACTIVE_STAGES
    ]
    entities.append(TasksDueTodaySensor(coordinator, config_entry))
    entities.append(TasksNextDueSensor(coordinator, config_entry))
    async_add_entities(entities)


def _due_date(item):
    """Return an item's due as a date (or None)."""
    if item.due is None:
        return None
    return item.due.date() if isinstance(item.due, datetime) else item.due


class _TasksSensorBase(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry

    @property
    def _items(self):
        return self.coordinator.data or []


class TasksStageSensor(_TasksSensorBase):
    """Count of active tasks in one kanban stage."""

    _attr_icon = "mdi:format-list-checks"

    def __init__(self, coordinator, config_entry: ConfigEntry, stage: str) -> None:
        super().__init__(coordinator, config_entry)
        self._stage = stage
        self._attr_unique_id = f"{config_entry.entry_id}_stage_{stage}"
        self._attr_name = f"Tasks {_STAGE_LABELS.get(stage, stage)}"

    def _stage_items(self):
        return [i for i in self._items if i.kanban_stage == self._stage]

    @property
    def native_value(self) -> int:
        return len(self._stage_items())

    @property
    def extra_state_attributes(self):
        return {
            "items": [
                {
                    "id": i.id,
                    "summary": i.summary,
                    "project": i.project,
                    "priority": i.priority,
                    "due": i.due_display or None,
                    "deadline": i.deadline_display or None,
                    "deadline_iso": i.deadline.isoformat() if i.deadline else None,
                    "due_iso": i.due.isoformat() if i.due else None,
                    "duration": i.duration_display or None,
                    "categories": i.categories or None,
                }
                for i in self._stage_items()
            ]
        }


class TasksDueTodaySensor(_TasksSensorBase):
    """Count of active tasks due today or overdue."""

    _attr_icon = "mdi:calendar-today"

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_due_today"
        self._attr_name = "Tasks Due Today"

    def _due_items(self):
        today = dt_util.now().date()
        out = []
        for item in self._items:
            d = _due_date(item)
            if d is not None and d <= today:
                out.append(item)
        return out

    @property
    def native_value(self) -> int:
        return len(self._due_items())

    @property
    def extra_state_attributes(self):
        return {
            "items": [
                {
                    "id": i.id,
                    "summary": i.summary,
                    "due": i.due_display or None,
                    "deadline": i.deadline_display or None,
                    "deadline_iso": i.deadline.isoformat() if i.deadline else None,
                    "due_iso": i.due.isoformat() if i.due else None,
                    "duration": i.duration_display or None,
                    "categories": i.categories or None,
                }
                for i in self._due_items()
            ]
        }


class TasksNextDueSensor(_TasksSensorBase):
    """Timestamp of the soonest upcoming due date."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_next_due"
        self._attr_name = "Tasks Next Due"

    @property
    def native_value(self):
        candidates = [i.due for i in self._items if i.due is not None]
        if not candidates:
            return None
        soonest = min(candidates)
        # Sensors with a timestamp device class must return tz-aware datetimes.
        if soonest.tzinfo is None:
            soonest = dt_util.as_local(soonest)
        return soonest
