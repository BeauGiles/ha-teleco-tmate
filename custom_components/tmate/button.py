"""Buttons to tell Home Assistant where the roof really is, without moving it."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_RC, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            TMateSyncButton(entry, "Set as fully open", "open", 100),
            TMateSyncButton(entry, "Set as fully closed", "closed", 0),
        ]
    )


class TMateSyncButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, name: str, key: str, position: int) -> None:
        self._entry_id = entry.entry_id
        self._position = position
        address = entry.data[CONF_ADDRESS]
        self._attr_name = name
        self._attr_icon = "mdi:arrow-collapse-up" if position else "mdi:arrow-collapse-down"
        self._attr_unique_id = f"{address}_{entry.data[CONF_RC]}_sync_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, address)})

    async def async_press(self) -> None:
        if (cover := self.hass.data.get(DOMAIN, {}).get(self._entry_id)) is not None:
            cover.async_sync_position(self._position)
