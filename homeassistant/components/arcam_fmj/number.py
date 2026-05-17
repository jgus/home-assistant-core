"""Arcam FMJ number entities for audio trim levels."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from arcam.fmj import APIVERSION_AVR_AND_SA_SERIES, APIVERSION_AVR_SERIES
from arcam.fmj.state import State

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfSoundPressure, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ArcamFmjConfigEntry, ArcamFmjCoordinator
from .entity import ArcamFmjDescriptionEntity, convert_exception

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ArcamFmjNumberEntityDescription(NumberEntityDescription):
    """Describes an Arcam FMJ number entity backed by a library scalar."""

    api_versions: set[str]
    zones: frozenset[int] = frozenset({1, 2})
    value_fn: Callable[[State], float | None]
    set_fn: Callable[[State, float], Awaitable[None]]


NUMBERS: tuple[ArcamFmjNumberEntityDescription, ...] = (
    ArcamFmjNumberEntityDescription(
        key="bass_equalization",
        translation_key="bass_equalization",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_AVR_SERIES,
        native_min_value=-12,
        native_max_value=12,
        native_step=1,
        native_unit_of_measurement=UnitOfSoundPressure.DECIBEL,
        mode=NumberMode.SLIDER,
        value_fn=lambda state: state.get_bass_equalization(),
        set_fn=lambda state, value: state.set_bass_equalization(value),
    ),
    ArcamFmjNumberEntityDescription(
        key="treble_equalization",
        translation_key="treble_equalization",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_AVR_SERIES,
        native_min_value=-12,
        native_max_value=12,
        native_step=1,
        native_unit_of_measurement=UnitOfSoundPressure.DECIBEL,
        mode=NumberMode.SLIDER,
        value_fn=lambda state: state.get_treble_equalization(),
        set_fn=lambda state, value: state.set_treble_equalization(value),
    ),
    ArcamFmjNumberEntityDescription(
        key="balance",
        translation_key="balance",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_AVR_AND_SA_SERIES,
        native_min_value=-6,
        native_max_value=6,
        native_step=1,
        native_unit_of_measurement=UnitOfSoundPressure.DECIBEL,
        mode=NumberMode.SLIDER,
        value_fn=lambda state: state.get_balance(),
        set_fn=lambda state, value: state.set_balance(value),
    ),
    ArcamFmjNumberEntityDescription(
        key="subwoofer_trim",
        translation_key="subwoofer_trim",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_AVR_SERIES,
        native_min_value=-10,
        native_max_value=10,
        native_step=0.5,
        native_unit_of_measurement=UnitOfSoundPressure.DECIBEL,
        mode=NumberMode.SLIDER,
        value_fn=lambda state: state.get_subwoofer_trim(),
        set_fn=lambda state, value: state.set_subwoofer_trim(value),
    ),
    ArcamFmjNumberEntityDescription(
        key="sub_stereo_trim",
        translation_key="sub_stereo_trim",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_AVR_SERIES,
        zones=frozenset({1}),
        native_min_value=-10,
        native_max_value=0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfSoundPressure.DECIBEL,
        mode=NumberMode.SLIDER,
        value_fn=lambda state: state.get_sub_stereo_trim(),
        set_fn=lambda state, value: state.set_sub_stereo_trim(value),
    ),
    ArcamFmjNumberEntityDescription(
        key="lipsync_delay",
        translation_key="lipsync_delay",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_AVR_SERIES,
        native_min_value=0,
        native_max_value=250,
        native_step=5,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        mode=NumberMode.SLIDER,
        value_fn=lambda state: state.get_lipsync_delay(),
        set_fn=lambda state, value: state.set_lipsync_delay(int(value)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ArcamFmjConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Arcam FMJ number entities from a config entry."""
    runtime_data = config_entry.runtime_data
    model = runtime_data.model

    async_add_entities(
        ArcamFmjNumber(coordinator, description)
        for coordinator in runtime_data.coordinators.values()
        for description in NUMBERS
        if model in description.api_versions
        and coordinator.state.zn in description.zones
    )


class ArcamFmjNumber(ArcamFmjDescriptionEntity, NumberEntity):
    """Representation of an Arcam FMJ trim number."""

    entity_description: ArcamFmjNumberEntityDescription

    def __init__(
        self,
        coordinator: ArcamFmjCoordinator,
        description: ArcamFmjNumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, description)

    @property
    def native_value(self) -> float | None:
        """Return the current trim level."""
        return self.entity_description.value_fn(self.coordinator.state)

    @convert_exception
    async def async_set_native_value(self, value: float) -> None:
        """Set a new trim level."""
        await self.entity_description.set_fn(self.coordinator.state, value)
        self.async_write_ha_state()
