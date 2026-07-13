"""The Tasks integration."""
import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import TasksApiClient
from .const import (
    CONF_REFRESH_INTERVAL,
    CONF_URL,
    DEFAULT_REFRESH_INTERVAL,
    DEFAULT_STAGE,
    DOMAIN,
    STAGES,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.TODO, Platform.SENSOR, Platform.CALENDAR]

SERVICE_CREATE_TASK = "create_task"
SERVICE_UPDATE_TASK = "update_task"
SERVICE_COMPLETE_TASK = "complete_task"
SERVICE_DELETE_TASK = "delete_task"
SERVICE_MOVE_TASK = "move_task"

CREATE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("summary"): cv.string,
        vol.Optional("stage", default=DEFAULT_STAGE): vol.In(STAGES),
        vol.Optional("project"): cv.string,
        vol.Optional("description"): cv.string,
        vol.Optional("priority"): vol.All(vol.Coerce(int), vol.Range(min=1, max=9)),
        vol.Optional("categories"): cv.string,
        vol.Optional("due"): cv.string,
        vol.Optional("deadline"): cv.string,
        vol.Optional("config_entry_id"): cv.string,
    }
)

UPDATE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("task_id"): vol.Coerce(int),
        vol.Optional("summary"): cv.string,
        vol.Optional("description"): cv.string,
        vol.Optional("project"): cv.string,
        vol.Optional("priority"): vol.All(vol.Coerce(int), vol.Range(min=1, max=9)),
        vol.Optional("categories"): cv.string,
        vol.Optional("due"): cv.string,
        vol.Optional("deadline"): cv.string,
        vol.Optional("config_entry_id"): cv.string,
    }
)

COMPLETE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("task_id"): vol.Coerce(int),
        vol.Optional("config_entry_id"): cv.string,
    }
)

DELETE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("task_id"): vol.Coerce(int),
        vol.Optional("config_entry_id"): cv.string,
    }
)

MOVE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("task_id"): vol.Coerce(int),
        vol.Required("stage"): vol.In(STAGES),
        vol.Optional("config_entry_id"): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tasks from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    client = TasksApiClient(entry.data[CONF_URL], session)

    refresh_seconds = entry.data.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL)
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="tasks_board",
        update_method=client.async_get_board,
        update_interval=timedelta(seconds=refresh_seconds),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    _register_services(hass)

    # Must run BEFORE forwarding platforms so the platforms find the migrated
    # unique_ids and reuse the existing entities instead of creating new ones
    # alongside now-orphaned old-format entries.
    _migrate_project_unique_ids(hass, entry, coordinator.data or [])

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


def _legacy_project_slug(project: str) -> str:
    """The old lossy slug per-project unique_ids used before the switch to the
    raw project string. Kept solely to locate existing entities for migration."""
    return project.lower().replace(" ", "_")


@callback
def _migrate_project_unique_ids(hass: HomeAssistant, entry: ConfigEntry, items) -> None:
    """Migrate per-project calendar/todo entities to raw-project-string unique_ids.

    The old scheme (`project.lower().replace(" ", "_")`) was not injective, so
    two project names differing only by case or spaces collided into one
    unique_id and HA silently dropped the second entity. The raw project string
    is injective. This one-time, idempotent rewrite preserves each existing
    entity (its entity_id, area, and customisations) across the change instead
    of orphaning it and spawning a "_2" duplicate.
    """
    registry = er.async_get(hass)
    projects = sorted({i.project for i in items if i.project})
    # (platform domain, unique_id prefix) for each per-project entity type
    platforms = (
        ("calendar", f"{entry.entry_id}_calendar_project_"),
        ("todo", f"{entry.entry_id}_project_"),
    )
    for domain, prefix in platforms:
        for project in projects:
            old_uid = f"{prefix}{_legacy_project_slug(project)}"
            new_uid = f"{prefix}{project}"
            if old_uid == new_uid:
                continue  # slug == raw (e.g. already lowercase, no spaces)
            old_entity = registry.async_get_entity_id(domain, DOMAIN, old_uid)
            if old_entity is None:
                continue  # nothing registered under the old id (already migrated / never existed)
            if registry.async_get_entity_id(domain, DOMAIN, new_uid) is not None:
                continue  # target id already taken — don't clobber
            _LOGGER.debug("Migrating %s unique_id %s -> %s", domain, old_uid, new_uid)
            registry.async_update_entity(old_entity, new_unique_id=new_uid)


def _resolve(hass: HomeAssistant, call: ServiceCall):
    """Resolve (client, coordinator) for a service call."""
    config_entry_id = call.data.get("config_entry_id")
    entry = None
    if config_entry_id:
        entry = hass.config_entries.async_get_entry(config_entry_id)
        if not entry and config_entry_id.startswith(("todo.", "sensor.", "calendar.")):
            registry = er_async_get(hass)
            ent = registry.async_get(config_entry_id)
            if ent:
                entry = hass.config_entries.async_get_entry(ent.config_entry_id)
        if not entry:
            _LOGGER.error("Config entry not found for: %s", config_entry_id)
            return None, None
    else:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            _LOGGER.error("No Tasks integration configured")
            return None, None
        entry = entries[0]

    store = hass.data[DOMAIN][entry.entry_id]
    return store["client"], store["coordinator"]


def er_async_get(hass: HomeAssistant):
    """Lazy import to avoid a hard dependency at module load."""
    from homeassistant.helpers import entity_registry as er

    return er.async_get(hass)


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_CREATE_TASK):
        return

    async def create_task(call: ServiceCall) -> None:
        client, coordinator = _resolve(hass, call)
        if not client:
            return
        payload = {"summary": call.data["summary"], "kanban_stage": call.data["stage"]}
        for key in ("project", "description", "priority", "categories", "due", "deadline"):
            if key in call.data:
                payload[key] = call.data[key]
        await client.async_create(payload)
        await coordinator.async_request_refresh()

    async def update_task(call: ServiceCall) -> None:
        client, coordinator = _resolve(hass, call)
        if not client:
            return
        payload = {}
        for key in ("summary", "description", "project", "priority", "categories", "due", "deadline"):
            if key in call.data:
                payload[key] = call.data[key]
        if not payload:
            _LOGGER.warning("update_task called with nothing to update")
            return
        await client.async_update(call.data["task_id"], payload)
        await coordinator.async_request_refresh()

    async def complete_task(call: ServiceCall) -> None:
        client, coordinator = _resolve(hass, call)
        if not client:
            return
        await client.async_complete(call.data["task_id"])
        await coordinator.async_request_refresh()

    async def delete_task(call: ServiceCall) -> None:
        client, coordinator = _resolve(hass, call)
        if not client:
            return
        await client.async_delete(call.data["task_id"])
        await coordinator.async_request_refresh()

    async def move_task(call: ServiceCall) -> None:
        client, coordinator = _resolve(hass, call)
        if not client:
            return
        await client.async_move(call.data["task_id"], call.data["stage"])
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_CREATE_TASK, create_task, schema=CREATE_TASK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_TASK, update_task, schema=UPDATE_TASK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_COMPLETE_TASK, complete_task, schema=COMPLETE_TASK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_TASK, delete_task, schema=DELETE_TASK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_MOVE_TASK, move_task, schema=MOVE_TASK_SCHEMA)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            for service in (
                SERVICE_CREATE_TASK,
                SERVICE_UPDATE_TASK,
                SERVICE_COMPLETE_TASK,
                SERVICE_DELETE_TASK,
                SERVICE_MOVE_TASK,
            ):
                if hass.services.has_service(DOMAIN, service):
                    hass.services.async_remove(DOMAIN, service)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
