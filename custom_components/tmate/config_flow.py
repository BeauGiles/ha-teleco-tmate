"""Config flow for Teleco T-Mate."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from .const import (
    CONF_CLOSE_TIME,
    CONF_OPEN_TIME,
    CONF_RC,
    DEFAULT_RC,
    DEFAULT_TRAVEL_SECONDS,
    DOMAIN,
    SERVICE_UUID,
)


class TMateConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TMateOptionsFlow()

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery is not None
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_ADDRESS: self._discovery.address,
                    CONF_RC: user_input[CONF_RC],
                },
            )
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default="Patio"): str,
                    vol.Required(CONF_RC, default=DEFAULT_RC): vol.All(
                        int, vol.Range(min=1, max=63)
                    ),
                }
            ),
            description_placeholders={"address": self._discovery.address},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={CONF_ADDRESS: address, CONF_RC: user_input[CONF_RC]},
            )

        current = self._async_current_ids()
        self._discovered = {
            info.address: f"{info.name} ({info.address})"
            for info in async_discovered_service_info(self.hass)
            if SERVICE_UUID in info.service_uuids and info.address not in current
        }
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(self._discovered),
                    vol.Required(CONF_NAME, default="Patio"): str,
                    vol.Required(CONF_RC, default=DEFAULT_RC): vol.All(
                        int, vol.Range(min=1, max=63)
                    ),
                }
            ),
        )


class TMateOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        seconds = vol.All(vol.Coerce(float), vol.Range(min=3, max=300))
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_OPEN_TIME, default=opts.get(CONF_OPEN_TIME, DEFAULT_TRAVEL_SECONDS)
                    ): seconds,
                    vol.Required(
                        CONF_CLOSE_TIME, default=opts.get(CONF_CLOSE_TIME, DEFAULT_TRAVEL_SECONDS)
                    ): seconds,
                }
            ),
        )
