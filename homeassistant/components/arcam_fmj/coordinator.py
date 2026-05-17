"""Coordinator for Arcam FMJ integration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging

from arcam.fmj.client import AmxDuetResponse, Client, ResponsePacket
from arcam.fmj.state import State

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class ArcamFmjRuntimeData:
    """Runtime data for Arcam FMJ integration."""

    client: Client
    coordinators: dict[int, ArcamFmjCoordinator]
    model: str


type ArcamFmjConfigEntry = ConfigEntry[ArcamFmjRuntimeData]


class ArcamFmjCoordinator(DataUpdateCoordinator[None]):
    """Coordinator for a single Arcam FMJ zone.

    The library drives state via its listener pipeline; this coordinator only
    relays per-zone packet notifications and connect/disconnect transitions
    to subscribed entities. There is no polling.
    """

    config_entry: ArcamFmjConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ArcamFmjConfigEntry,
        client: Client,
        zone: int,
        model: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"Arcam FMJ zone {zone}",
        )
        self.client = client
        self.state = State(client, zone)

        device_name = config_entry.title
        unique_id = config_entry.unique_id or config_entry.entry_id
        unique_id_device = unique_id
        if zone != 1:
            unique_id_device += f"-{zone}"
            device_name += f" Zone {zone}"

        self.device_name = device_name
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id_device)},
            manufacturer="Arcam",
            model=model,
            name=device_name,
        )
        self.zone_unique_id = f"{unique_id}-{zone}"

        if zone != 1:
            self.device_info["via_device"] = (DOMAIN, unique_id)

    async def _async_update_data(self) -> None:
        """Manual refresh is a no-op; updates are pushed by the library."""

    @callback
    def _async_notify_packet(self, packet: ResponsePacket | AmxDuetResponse) -> None:
        """Packet callback to detect changes to state."""
        if not isinstance(packet, ResponsePacket) or packet.zn != self.state.zn:
            return

        self.async_update_listeners()

    @asynccontextmanager
    async def async_monitor_client(self) -> AsyncGenerator[None]:
        """Wire up listeners for the duration of an active client connection."""
        async with self.state:
            try:
                with self.client.listen(self._async_notify_packet):
                    self.async_update_listeners()
                    yield
            finally:
                self.async_update_listeners()
