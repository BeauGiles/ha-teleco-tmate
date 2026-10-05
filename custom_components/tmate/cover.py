"""Cover platform for Teleco T-Mate (open / stop / close, time-based position)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import time
from typing import Any

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HassJob, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    CHANNEL_CLOSE,
    CHANNEL_OPEN,
    CHANNEL_STOP,
    CONF_CLOSE_TIME,
    CONF_OPEN_TIME,
    CONF_RC,
    DEFAULT_TRAVEL_SECONDS,
    DOMAIN,
    HOLD_SECONDS,
    KEEPALIVE_SECONDS,
    RETRY_DELAY,
    STOP_LEAD_SECONDS,
    TX_CHAR,
)

_LOGGER = logging.getLogger(__name__)


def press_frame(rc: int, channel: int, release: bool = False, time_ms: int = 350) -> bytes:
    """16-byte frame from the T-Mate app's pressButton(); release sets 0xC0 on rc."""
    frame = bytearray(16)
    frame[0] = 0x01
    frame[1] = (rc | 0xC0) if release else rc
    frame[2] = channel
    frame[3] = (time_ms >> 8) & 0xFF
    frame[4] = time_ms & 0xFF
    frame[5] = 0x01
    return bytes(frame)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    cover = TMateCover(entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = cover
    async_add_entities([cover])


class TMateCover(CoverEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_assumed_state = True
    _attr_device_class = CoverDeviceClass.AWNING
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, entry: ConfigEntry) -> None:
        self._address: str = entry.data[CONF_ADDRESS]
        self._rc: int = entry.data[CONF_RC]
        self._open_time = float(entry.options.get(CONF_OPEN_TIME, DEFAULT_TRAVEL_SECONDS))
        self._close_time = float(entry.options.get(CONF_CLOSE_TIME, DEFAULT_TRAVEL_SECONDS))
        self._lock = asyncio.Lock()
        self._attr_unique_id = f"{self._address}_{self._rc}"
        # Estimated position, 100 = open, 0 = closed. None until the roof has been
        # driven to an end stop once (the box reports no position).
        self._position: float | None = None
        self._direction = 0  # +1 opening, -1 closing, 0 idle
        self._move_start = 0.0
        self._cancel_end = None
        self._cancel_tick = None
        self._target = 0
        self._last_command: str | None = None
        self._last_command_at: str | None = None
        self._last_command_ok: bool | None = None
        self._last_error: str | None = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._address)},
            connections={(CONNECTION_BLUETOOTH, self._address)},
            name=entry.title,
            manufacturer="Teleco Automation",
            model="T-Mate",
        )

    # --- lifecycle / availability -------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Restore the last position and track whether the box is reachable."""
        if (last := await self.async_get_last_state()) is not None:
            if last.state in ("open", "closed"):
                pos = last.attributes.get("current_position")
                self._position = (
                    float(pos)
                    if pos is not None
                    else (0.0 if last.state == "closed" else 100.0)
                )
        self.async_on_remove(self._cancel_timers)

        self._attr_available = bluetooth.async_address_present(
            self.hass, self._address, connectable=True
        )
        self.async_on_remove(
            bluetooth.async_register_callback(
                self.hass,
                self._async_seen,
                BluetoothCallbackMatcher(address=self._address, connectable=True),
                BluetoothScanningMode.ACTIVE,
            )
        )
        self.async_on_remove(
            bluetooth.async_track_unavailable(
                self.hass, self._async_lost, self._address, connectable=True
            )
        )

    @callback
    def _async_seen(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        if not self._attr_available:
            self._attr_available = True
            self.async_write_ha_state()

    @callback
    def _async_lost(self, service_info: BluetoothServiceInfoBleak) -> None:
        self._attr_available = False
        self.async_write_ha_state()

    # --- BLE ---------------------------------------------------------------

    async def _connect(self) -> BleakClientWithServiceCache:
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self._address, connectable=True
        )
        if ble_device is None:
            raise HomeAssistantError(f"T-Mate {self._address} is not in Bluetooth range")
        try:
            return await establish_connection(
                BleakClientWithServiceCache, ble_device, self._address
            )
        except Exception as err:
            raise HomeAssistantError(f"Could not connect to T-Mate: {err}") from err

    async def _send_once(self, channel: int) -> float:
        client = await self._connect()
        phase = "press"
        try:
            await client.write_gatt_char(TX_CHAR, press_frame(self._rc, channel), response=True)
            started = time.monotonic()
            phase = "hold"
            # The app re-sends the press every 350 ms while a button is held.
            elapsed = 0.0
            while elapsed + KEEPALIVE_SECONDS < HOLD_SECONDS:
                await asyncio.sleep(KEEPALIVE_SECONDS)
                elapsed += KEEPALIVE_SECONDS
                await client.write_gatt_char(
                    TX_CHAR, press_frame(self._rc, channel), response=True
                )
            await asyncio.sleep(max(HOLD_SECONDS - elapsed, 0))
            phase = "release"
            await client.write_gatt_char(
                TX_CHAR, press_frame(self._rc, channel, release=True), response=True
            )
            return started
        except Exception as err:
            raise HomeAssistantError(f"T-Mate command failed during {phase}: {err}") from err
        finally:
            await client.disconnect()

    async def _send(self, channel: int) -> float:
        """Send a command; returns the monotonic time the motor was told to start."""
        # Connect per command and disconnect after, so the phone app still works.
        name = {CHANNEL_OPEN: "open", CHANNEL_STOP: "stop", CHANNEL_CLOSE: "close"}[channel]
        async with self._lock:
            try:
                try:
                    started = await self._send_once(channel)
                except HomeAssistantError as err:
                    _LOGGER.warning("T-Mate command failed, retrying once: %s", err)
                    await asyncio.sleep(RETRY_DELAY)
                    started = await self._send_once(channel)
            except HomeAssistantError as err:
                self._record(name, False, str(err))
                raise
            self._record(name, True, None)
            return started

    @callback
    def _record(self, name: str, ok: bool, error: str | None) -> None:
        self._last_command = name
        self._last_command_at = dt_util.utcnow().isoformat()
        self._last_command_ok = ok
        self._last_error = error

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "last_command": self._last_command,
            "last_command_at": self._last_command_at,
            "last_command_ok": self._last_command_ok,
            "last_error": self._last_error,
        }

    # --- position estimate -------------------------------------------------

    def _estimate(self, at: float | None = None) -> float | None:
        if self._position is None:
            return None
        if self._direction == 0:
            return self._position
        elapsed = (at if at is not None else time.monotonic()) - self._move_start
        travel = self._open_time if self._direction > 0 else self._close_time
        pos = self._position + self._direction * elapsed / travel * 100
        return min(100.0, max(0.0, pos))

    @property
    def current_cover_position(self) -> int | None:
        est = self._estimate()
        return None if est is None else round(est)

    @property
    def is_closed(self) -> bool | None:
        if self._direction != 0:
            return False
        return None if self._position is None else self._position <= 0

    @property
    def is_opening(self) -> bool:
        return self._direction > 0

    @property
    def is_closing(self) -> bool:
        return self._direction < 0

    @callback
    def _cancel_timers(self) -> None:
        for name in ("_cancel_end", "_cancel_tick"):
            if (cancel := getattr(self, name)) is not None:
                cancel()
                setattr(self, name, None)

    @callback
    def _settle(self, at: float | None = None) -> float | None:
        """Freeze the estimate and stop tracking motion."""
        self._position = self._estimate(at)
        self._direction = 0
        self._cancel_timers()
        return self._position

    @callback
    def _begin(self, direction: int, target: int, started: float, partial: bool) -> None:
        """Track a move that the motor started at `started`."""
        self._cancel_timers()
        base = self._position
        self._direction = direction
        self._move_start = started
        travel = self._open_time if direction > 0 else self._close_time
        waited = time.monotonic() - started
        if not partial:
            # Full travel to an end stop; from an unknown start allow the whole travel.
            remaining = travel if base is None else abs(target - base) / 100 * travel
            delay = remaining - waited
            self._target = target
            self._cancel_end = async_call_later(
                self.hass, max(delay, 0), HassJob(self._on_full_timer, cancel_on_shutdown=True)
            )
        else:
            remaining = abs(target - base) / 100 * travel
            delay = remaining - STOP_LEAD_SECONDS - waited
            self._target = target
            self._cancel_end = async_call_later(
                self.hass, max(delay, 0), HassJob(self._on_partial_timer, cancel_on_shutdown=True)
            )
        self._cancel_tick = async_track_time_interval(
            self.hass, self._on_tick, timedelta(seconds=1)
        )
        self.async_write_ha_state()

    @callback
    def _on_tick(self, _now) -> None:
        self.async_write_ha_state()

    @callback
    def _on_full_timer(self, _now) -> None:
        self._arrived(self._target)

    @callback
    def _on_partial_timer(self, _now) -> None:
        self.hass.async_create_task(self._async_stop_at(self._target))

    @callback
    def async_sync_position(self, position: int) -> None:
        """Declare where the roof really is, without moving it."""
        self._cancel_timers()
        self._position = float(position)
        self._direction = 0
        self.async_write_ha_state()

    @callback
    def _arrived(self, target: int) -> None:
        self._cancel_timers()
        self._position = float(target)
        self._direction = 0
        self.async_write_ha_state()

    async def _async_stop_at(self, target: int) -> None:
        self._cancel_timers()
        try:
            await self._send(CHANNEL_STOP)
        except HomeAssistantError as err:
            _LOGGER.error("T-Mate could not stop at target, position now unknown: %s", err)
            self._position = None
        else:
            self._position = float(target)
        self._direction = 0
        self.async_write_ha_state()

    # --- commands ----------------------------------------------------------

    async def _move_to(self, target: int) -> None:
        pos = self._settle()
        partial = 0 < target < 100
        if partial:
            if pos is None:
                self.async_write_ha_state()
                raise HomeAssistantError(
                    "Position is unknown: fully open or close the patio once first"
                )
            if abs(target - pos) < 3:
                self.async_write_ha_state()
                return
            direction = 1 if target > pos else -1
        else:
            direction = 1 if target >= 100 else -1
        try:
            started = await self._send(CHANNEL_OPEN if direction > 0 else CHANNEL_CLOSE)
        except HomeAssistantError:
            self.async_write_ha_state()
            raise
        self._begin(direction, target, started, partial)

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._move_to(100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._move_to(0)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._move_to(int(kwargs[ATTR_POSITION]))

    async def async_stop_cover(self, **kwargs: Any) -> None:
        started = await self._send(CHANNEL_STOP)
        self._settle(started)
        self.async_write_ha_state()
