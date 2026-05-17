"""Arcam component."""

import asyncio
from asyncio import timeout
from contextlib import AsyncExitStack
import logging

from arcam.fmj import APIVERSION_ZONE2_SERIES, AmxDuetRequest, ConnectionFailed
from arcam.fmj.client import Client, ClientContext

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DEFAULT_SCAN_INTERVAL, SETUP_TIMEOUT
from .coordinator import ArcamFmjConfigEntry, ArcamFmjCoordinator, ArcamFmjRuntimeData

_LOGGER = logging.getLogger(__name__)


PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.MEDIA_PLAYER,
    Platform.REMOTE,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ArcamFmjConfigEntry) -> bool:
    """Set up config entry."""
    client = Client(entry.data[CONF_HOST], entry.data[CONF_PORT])

    try:
        async with timeout(SETUP_TIMEOUT), ClientContext(client):
            response = await client.request_raw(AmxDuetRequest())
    except (ConnectionFailed, TimeoutError, OSError) as err:
        raise ConfigEntryNotReady(
            f"Unable to connect to Arcam FMJ at {client.peer}"
        ) from err

    model = response.device_model
    if model is None:
        raise ConfigEntryNotReady(
            f"Arcam FMJ at {client.peer} did not return a model identifier"
        )

    coordinators: dict[int, ArcamFmjCoordinator] = {
        zone: ArcamFmjCoordinator(hass, entry, client, zone, model)
        for zone in _supported_zones(model)
    }

    entry.runtime_data = ArcamFmjRuntimeData(client, coordinators, model)

    entry.async_create_background_task(
        hass,
        _run_client(hass, entry.runtime_data, DEFAULT_SCAN_INTERVAL),
        "arcam_fmj",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ArcamFmjConfigEntry) -> bool:
    """Cleanup before removing config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _supported_zones(model: str) -> tuple[int, ...]:
    """Return the zones the given Arcam model exposes."""
    if model in APIVERSION_ZONE2_SERIES:
        return (1, 2)
    return (1,)


async def _run_client(
    hass: HomeAssistant,
    runtime_data: ArcamFmjRuntimeData,
    interval: float,
) -> None:
    client = runtime_data.client
    coordinators = runtime_data.coordinators
    connected = True

    while True:
        try:
            async with AsyncExitStack() as stack:
                async with timeout(interval):
                    await client.start()
                stack.push_async_callback(client.stop)

                if not connected:
                    _LOGGER.info("Reconnected to Arcam FMJ at %s", client.host)
                    connected = True

                try:
                    for coordinator in coordinators.values():
                        await stack.enter_async_context(
                            coordinator.async_monitor_client()
                        )

                    await client.process()
                finally:
                    if connected:
                        _LOGGER.warning(
                            "Lost connection to Arcam FMJ at %s", client.host
                        )
                        connected = False

        except ConnectionFailed:
            if connected:
                _LOGGER.warning("Connection to Arcam FMJ at %s failed", client.host)
                connected = False
        except TimeoutError:
            if connected:
                _LOGGER.warning("Connection to Arcam FMJ at %s timed out", client.host)
                connected = False
            continue
        except Exception:
            _LOGGER.exception("Unexpected exception, aborting arcam client")
            return

        await asyncio.sleep(interval)
