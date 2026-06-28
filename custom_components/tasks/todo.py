"""Todo platform for the Tasks integration."""
import logging

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import (
    CONF_CREATE_PROJECT_LISTS,
    DEFAULT_STAGE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up todo lists: one unified list plus optional per-project lists."""
    store = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = store["coordinator"]
    client = store["client"]

    entities: list[TasksTodoListBase] = [TasksUnifiedList(coordinator, client, config_entry)]

    if config_entry.data.get(CONF_CREATE_PROJECT_LISTS, False):
        projects = sorted({item.project for item in (coordinator.data or []) if item.project})
        for project in projects:
            entities.append(TasksProjectList(coordinator, client, config_entry, project))

    async_add_entities(entities)


class TasksTodoListBase(CoordinatorEntity, TodoListEntity):
    """Base for Tasks todo lists."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DUE_DATETIME_ON_ITEM
    )

    def __init__(self, coordinator: DataUpdateCoordinator, client, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._client = client
        self._config_entry = config_entry

    def _filter(self, items):
        """Filter the coordinator's items for this list. Override in subclasses."""
        return [i for i in items if not i.is_done]

    @property
    def todo_items(self) -> list[TodoItem] | None:
        if self.coordinator.data is None:
            return None
        return [
            TodoItem(
                summary=item.summary,
                uid=str(item.id),
                status=(
                    TodoItemStatus.COMPLETED if item.is_done else TodoItemStatus.NEEDS_ACTION
                ),
                due=item.due_value(),
                description=item.description or "",
            )
            for item in self._filter(self.coordinator.data)
        ]

    @property
    def extra_state_attributes(self):
        return {"config_entry_id": self._config_entry.entry_id}

    def _new_item_extras(self) -> dict:
        """Extra fields applied to items created from this list."""
        return {}

    async def async_create_todo_item(self, item: TodoItem) -> None:
        payload = {
            "summary": item.summary,
            "kanban_stage": DEFAULT_STAGE,
            **self._new_item_extras(),
        }
        if item.description:
            payload["description"] = item.description
        if item.due:
            payload["due"] = item.due.isoformat()
        await self._client.async_create(payload)
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        task_id = int(item.uid)
        if item.status == TodoItemStatus.COMPLETED:
            await self._client.async_complete(task_id)
        else:
            payload = {"summary": item.summary, "description": item.description or ""}
            payload["due"] = item.due.isoformat() if item.due else None
            await self._client.async_update(task_id, payload)
        await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            await self._client.async_delete(int(uid))
        await self.coordinator.async_request_refresh()


class TasksUnifiedList(TasksTodoListBase):
    """All active tasks across every project and stage."""

    def __init__(self, coordinator, client, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, client, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_all"
        self._attr_name = "Tasks"

    def _filter(self, items):
        return [i for i in items if not i.is_done]


class TasksProjectList(TasksTodoListBase):
    """Active tasks for a single project."""

    def __init__(self, coordinator, client, config_entry: ConfigEntry, project: str) -> None:
        super().__init__(coordinator, client, config_entry)
        self._project = project
        slug = project.lower().replace(" ", "_")
        self._attr_unique_id = f"{config_entry.entry_id}_project_{slug}"
        self._attr_name = f"Tasks: {project}"

    def _filter(self, items):
        return [i for i in items if not i.is_done and i.project == self._project]

    def _new_item_extras(self) -> dict:
        return {"project": self._project}
