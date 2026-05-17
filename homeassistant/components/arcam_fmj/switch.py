"""Arcam FMJ switch entities."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from arcam.fmj import APIVERSION_450_SERIES, APIVERSION_DIRECT_MODE_SERIES
from arcam.fmj.state import State

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ArcamFmjConfigEntry
from .entity import ArcamFmjDescriptionEntity, convert_exception

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ArcamFmjSwitchEntityDescription(SwitchEntityDescription):
    """Describes an Arcam FMJ switch entity."""

    api_versions: set[str]
    zones: frozenset[int] = frozenset({1, 2})
    value_fn: Callable[[State], bool | None]
    set_fn: Callable[[State, bool], Awaitable[None]]


SWITCHES: tuple[ArcamFmjSwitchEntityDescription, ...] = (
    ArcamFmjSwitchEntityDescription(
        key="direct_mode",
        translation_key="direct_mode",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_DIRECT_MODE_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: state.get_direct_mode(),
        set_fn=lambda state, on: state.set_direct_mode(on),
    ),
    ArcamFmjSwitchEntityDescription(
        key="dolby_pliix_panorama",
        translation_key="dolby_pliix_panorama",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_450_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: state.get_dolby_pliix_panorama(),
        set_fn=lambda state, on: state.set_dolby_pliix_panorama(on),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ArcamFmjConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Arcam FMJ switch entities from a config entry."""
    runtime_data = config_entry.runtime_data
    model = runtime_data.model

    async_add_entities(
        ArcamFmjSwitch(coordinator, description)
        for coordinator in runtime_data.coordinators.values()
        for description in SWITCHES
        if model in description.api_versions
        and coordinator.state.zn in description.zones
    )


class ArcamFmjSwitch(ArcamFmjDescriptionEntity, SwitchEntity):
    """Representation of an Arcam FMJ switch."""

    entity_description: ArcamFmjSwitchEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return whether the switch is on."""
        return self.entity_description.value_fn(self.coordinator.state)

    @convert_exception
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.entity_description.set_fn(self.coordinator.state, True)
        self.async_write_ha_state()

    @convert_exception
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.entity_description.set_fn(self.coordinator.state, False)
        self.async_write_ha_state()
