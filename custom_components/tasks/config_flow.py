"""Config flow for the Tasks integration."""
from datetime import timedelta
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    DurationSelector,
    DurationSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
)

from .api import TasksApiClient
from .const import (
    CONF_CALENDAR_DATE_FIELD,
    CONF_CREATE_PROJECT_LISTS,
    CONF_REFRESH_INTERVAL,
    CONF_SHOW_DUE_IN,
    CONF_URL,
    DEFAULT_CALENDAR_DATE_FIELD,
    DEFAULT_REFRESH_INTERVAL,
    DEFAULT_SHOW_DUE_IN,
    DOMAIN,
)


def _seconds_to_duration(total_seconds: int) -> dict[str, int]:
    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return {"hours": hours, "minutes": minutes, "seconds": seconds}


def _duration_to_seconds(config: dict[str, int]) -> int:
    return int(
        timedelta(
            hours=config.get("hours", 0),
            minutes=config.get("minutes", 0),
            seconds=config.get("seconds", 0),
        ).total_seconds()
    )


_DATE_FIELD_SELECTOR = SelectSelector(
    SelectSelectorConfig(options=["due", "deadline"], translation_key="calendar_date_field")
)


def _options_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_CREATE_PROJECT_LISTS,
                default=defaults.get(CONF_CREATE_PROJECT_LISTS, False),
            ): bool,
            vol.Optional(
                CONF_SHOW_DUE_IN,
                default=defaults.get(CONF_SHOW_DUE_IN, DEFAULT_SHOW_DUE_IN),
            ): vol.Coerce(int),
            vol.Optional(
                CONF_CALENDAR_DATE_FIELD,
                default=defaults.get(CONF_CALENDAR_DATE_FIELD, DEFAULT_CALENDAR_DATE_FIELD),
            ): _DATE_FIELD_SELECTOR,
            vol.Optional(
                CONF_REFRESH_INTERVAL,
                default=_seconds_to_duration(
                    defaults.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL)
                ),
            ): DurationSelector(DurationSelectorConfig(enable_day=False, allow_negative=False)),
        }
    )


class TasksConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tasks."""

    VERSION = 1

    def __init__(self) -> None:
        self._server_data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect the server URL and validate connectivity."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                session = async_get_clientsession(self.hass)
                client = TasksApiClient(user_input[CONF_URL], session)
                await client.async_get_board()
                self._server_data = user_input
                return await self.async_step_options()
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_URL): str}),
            errors=errors,
        )

    async def async_step_options(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect display options."""
        if user_input is not None:
            data = {
                **self._server_data,
                CONF_CREATE_PROJECT_LISTS: user_input.get(CONF_CREATE_PROJECT_LISTS, False),
                CONF_SHOW_DUE_IN: user_input.get(CONF_SHOW_DUE_IN, DEFAULT_SHOW_DUE_IN),
                CONF_CALENDAR_DATE_FIELD: user_input.get(
                    CONF_CALENDAR_DATE_FIELD, DEFAULT_CALENDAR_DATE_FIELD
                ),
                CONF_REFRESH_INTERVAL: _duration_to_seconds(
                    user_input.get(
                        CONF_REFRESH_INTERVAL, _seconds_to_duration(DEFAULT_REFRESH_INTERVAL)
                    )
                ),
            }
            return self.async_create_entry(title="Tasks", data=data)

        return self.async_show_form(step_id="options", data_schema=_options_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TasksOptionsFlowHandler(config_entry)


class TasksOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Tasks options after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            data = {
                CONF_URL: self.entry.data.get(CONF_URL),
                CONF_CREATE_PROJECT_LISTS: user_input.get(CONF_CREATE_PROJECT_LISTS, False),
                CONF_SHOW_DUE_IN: user_input.get(CONF_SHOW_DUE_IN, DEFAULT_SHOW_DUE_IN),
                CONF_CALENDAR_DATE_FIELD: user_input.get(
                    CONF_CALENDAR_DATE_FIELD, DEFAULT_CALENDAR_DATE_FIELD
                ),
                CONF_REFRESH_INTERVAL: _duration_to_seconds(
                    user_input.get(
                        CONF_REFRESH_INTERVAL, _seconds_to_duration(DEFAULT_REFRESH_INTERVAL)
                    )
                ),
            }
            self.hass.config_entries.async_update_entry(
                self.entry, data=data, options=self.entry.options
            )
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.entry.entry_id)
            )
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init", data_schema=_options_schema(dict(self.entry.data))
        )
