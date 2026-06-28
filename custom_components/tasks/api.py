"""API client for the tasks_go backend.

The server requires no authentication (it lives on a private LAN / Tailscale).
All endpoints live under ``/api`` and return the VTODO-based item shape.
"""
import logging
from typing import List, Optional

import aiohttp

from .const import ACTIVE_STAGES, API_TIMEOUT
from .model import TaskItem

_LOGGER = logging.getLogger(__name__)

_HEADERS = {"Content-Type": "application/json"}


class TasksApiClient:
    """Thin async client over the tasks_go HTTP API."""

    def __init__(self, base_url: str, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._base_url = base_url.rstrip("/")
        self._session = session

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    async def async_get_board(self) -> List[TaskItem]:
        """Fetch the full board (all active stages) as a flat list.

        ``GET /api/board`` returns a dict keyed by stage. We flatten it so the
        coordinator holds a single list of active TaskItems.
        """
        try:
            async with self._session.get(
                self._url("/api/board"), headers=_HEADERS, timeout=API_TIMEOUT
            ) as response:
                response.raise_for_status()
                data = await response.json()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching board from tasks server: %s", err)
            raise

        items: List[TaskItem] = []
        if isinstance(data, dict):
            for stage in ACTIVE_STAGES:
                for raw in data.get(stage, []) or []:
                    items.append(TaskItem.from_json(raw))
        elif isinstance(data, list):
            items = TaskItem.from_json_list(data)
        else:
            _LOGGER.error("Unexpected board response shape: %s", type(data))
        return items

    async def async_create(self, payload: dict) -> TaskItem:
        """Create an item via ``POST /api/items``."""
        try:
            async with self._session.post(
                self._url("/api/items"), headers=_HEADERS, json=payload, timeout=API_TIMEOUT
            ) as response:
                response.raise_for_status()
                return TaskItem.from_json(await response.json())
        except aiohttp.ClientError as err:
            _LOGGER.error("Error creating item: %s", err)
            raise

    async def async_update(self, item_id: int, payload: dict) -> TaskItem:
        """Update an item via ``PATCH /api/items/{id}``."""
        try:
            async with self._session.patch(
                self._url(f"/api/items/{item_id}"), headers=_HEADERS, json=payload, timeout=API_TIMEOUT
            ) as response:
                response.raise_for_status()
                return TaskItem.from_json(await response.json())
        except aiohttp.ClientError as err:
            _LOGGER.error("Error updating item %s: %s", item_id, err)
            raise

    async def async_complete(self, item_id: int) -> None:
        """Mark an item complete via ``PUT /api/items/{id}/complete``."""
        try:
            async with self._session.put(
                self._url(f"/api/items/{item_id}/complete"), headers=_HEADERS, timeout=API_TIMEOUT
            ) as response:
                response.raise_for_status()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error completing item %s: %s", item_id, err)
            raise

    async def async_move(self, item_id: int, stage: str, position: float = 999.0) -> None:
        """Move an item to a stage via ``PUT /api/items/{id}/move``."""
        payload = {"stage": stage, "position": position}
        try:
            async with self._session.put(
                self._url(f"/api/items/{item_id}/move"), headers=_HEADERS, json=payload, timeout=API_TIMEOUT
            ) as response:
                response.raise_for_status()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error moving item %s to %s: %s", item_id, stage, err)
            raise

    async def async_delete(self, item_id: int) -> bool:
        """Delete an item via ``DELETE /api/items/{id}``."""
        try:
            async with self._session.delete(
                self._url(f"/api/items/{item_id}"), headers=_HEADERS, timeout=API_TIMEOUT
            ) as response:
                response.raise_for_status()
                return True
        except aiohttp.ClientError as err:
            _LOGGER.error("Error deleting item %s: %s", item_id, err)
            raise

    async def async_projects(self) -> List[str]:
        """List project names via ``GET /api/projects``."""
        try:
            async with self._session.get(
                self._url("/api/projects"), headers=_HEADERS, timeout=API_TIMEOUT
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return [p for p in data if p] if isinstance(data, list) else []
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching projects: %s", err)
            return []
