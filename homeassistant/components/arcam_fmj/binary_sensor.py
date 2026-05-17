"""Arcam binary sensors."""

from collections.abc import Callable
from dataclasses import dataclass

from arcam.fmj import APIVERSION_AVR_AND_SA_SERIES, APIVERSION_AVR_SERIES
from arcam.fmj.state import State

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ArcamFmjConfigEntry
from .entity import ArcamFmjDescriptionEntity

# Read-only, coordinator-driven entities; no per-entity I/O to bound.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ArcamFmjBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an Arcam FMJ binary sensor entity."""

    api_versions: set[str]
    zones: frozenset[int] = frozenset({1, 2})
    value_fn: Callable[[State], bool | None]


BINARY_SENSORS: tuple[ArcamFmjBinarySensorEntityDescription, ...] = (
    ArcamFmjBinarySensorEntityDescription(
        key="incoming_video_interlaced",
        translation_key="incoming_video_interlaced",
        entity_category=EntityCategory.DIAGNOSTIC,
        api_versions=APIVERSION_AVR_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: (
            vp.interlaced
            if (vp := state.get_incoming_video_parameters()) is not None
            else None
        ),
    ),
    ArcamFmjBinarySensorEntityDescription(
        key="headphones",
        translation_key="headphones",
        api_versions=APIVERSION_AVR_AND_SA_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: state.get_headphones(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ArcamFmjConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Arcam FMJ binary sensors from a config entry."""
    runtime_data = config_entry.runtime_data
    model = runtime_data.model

    async_add_entities(
        ArcamFmjBinarySensorEntity(coordinator, description)
        for coordinator in runtime_data.coordinators.values()
        for description in BINARY_SENSORS
        if model in description.api_versions
        and coordinator.state.zn in description.zones
    )


class ArcamFmjBinarySensorEntity(ArcamFmjDescriptionEntity, BinarySensorEntity):
    """Representation of an Arcam FMJ binary sensor."""

    entity_description: ArcamFmjBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return the binary sensor value."""
        return self.entity_description.value_fn(self.coordinator.state)
