"""Arcam FMJ remote for RC5 IR command simulation."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from arcam.fmj import RC5CodeColor, RC5CodeNavigation, RC5CodeToggle
from arcam.fmj.state import State

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    RemoteEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import ArcamFmjConfigEntry, ArcamFmjCoordinator
from .entity import ArcamFmjEntity, convert_exception

PARALLEL_UPDATES = 0


type _CommandSender = Callable[[State], Awaitable[None]]


def _navigation(code: RC5CodeNavigation) -> _CommandSender:
    return lambda state: state.send_navigation(code)


def _color(code: RC5CodeColor) -> _CommandSender:
    return lambda state: state.send_color(code)


def _toggle(code: RC5CodeToggle) -> _CommandSender:
    return lambda state: state.send_toggle(code)


def _numeric(digit: int) -> _CommandSender:
    return lambda state: state.send_numeric(digit)


COMMANDS: dict[str, _CommandSender] = {
    **{code.name.lower(): _navigation(code) for code in RC5CodeNavigation},
    **{str(digit): _numeric(digit) for digit in range(10)},
    **{code.name.lower(): _color(code) for code in RC5CodeColor},
    **{code.name.lower(): _toggle(code) for code in RC5CodeToggle},
}


def _resolve(command: str) -> _CommandSender:
    """Look up a command in the dispatch table or raise."""
    sender = COMMANDS.get(command.lower())
    if sender is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_command",
            translation_placeholders={"command": command},
        )
    return sender


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ArcamFmjConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Arcam FMJ remote entities."""
    coordinators = config_entry.runtime_data.coordinators

    async_add_entities(ArcamFmjRemote(coordinators[zone]) for zone in (1, 2))


class ArcamFmjRemote(ArcamFmjEntity, RemoteEntity):
    """Remote that sends RC5 IR commands to an Arcam FMJ zone."""

    _attr_name = None

    def __init__(self, coordinator: ArcamFmjCoordinator) -> None:
        """Initialize the remote."""
        super().__init__(coordinator)
        self._state = coordinator.state
        self._attr_unique_id = f"{coordinator.zone_unique_id}-remote"

    @property
    def is_on(self) -> bool | None:
        """Return whether the underlying zone is powered on."""
        return self._state.get_power()

    @convert_exception
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the zone on."""
        await self._state.set_power(True)

    @convert_exception
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the zone off."""
        await self._state.set_power(False)

    @convert_exception
    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send a sequence of RC5 commands."""
        num_repeats: int = kwargs[ATTR_NUM_REPEATS]
        delay_secs: float = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        resolved = [(name, _resolve(name)) for name in command]
        first = True
        for _ in range(num_repeats):
            for name, sender in resolved:
                if not first:
                    await asyncio.sleep(delay_secs)
                first = False
                try:
                    await sender(self._state)
                except ValueError as err:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key="unsupported_command",
                        translation_placeholders={"command": name},
                    ) from err
