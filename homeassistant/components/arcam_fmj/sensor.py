"""Arcam FMJ sensor entities."""

from collections.abc import Callable
from dataclasses import dataclass
import logging

from arcam.fmj import (
    APIVERSION_AVR_SERIES,
    APIVERSION_CLASS_G_SERIES,
    APIVERSION_THERMAL_DIAGNOSTICS_SERIES,
    IncomingVideoAspectRatio,
    IncomingVideoColorspace,
    IntOrTypeEnum,
)
from arcam.fmj.state import IncomingAudioConfig, IncomingAudioFormat, State

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ArcamFmjConfigEntry
from .entity import ArcamFmjDescriptionEntity

_LOGGER = logging.getLogger(__name__)

# Read-only, coordinator-driven entities; no per-entity I/O to bound.
PARALLEL_UPDATES = 0


def _enum_options(value: type[IntOrTypeEnum]) -> list[str]:
    return [
        member.name.lower() for member in value if not member.name.startswith("CODE_")
    ]


def _enum_value(value: IntOrTypeEnum | None) -> str | None:
    if value is None:
        return None

    if value.name.startswith("CODE_"):
        _LOGGER.debug("Undefined enum value %s ignored", value)
        return None

    return value.name.lower()


@dataclass(frozen=True, kw_only=True)
class ArcamFmjSensorEntityDescription(SensorEntityDescription):
    """Describes an Arcam FMJ sensor entity."""

    api_versions: set[str]
    zones: frozenset[int] = frozenset({1, 2})
    value_fn: Callable[[State], int | float | str | None]


SENSORS: tuple[ArcamFmjSensorEntityDescription, ...] = (
    ArcamFmjSensorEntityDescription(
        key="incoming_video_horizontal_resolution",
        translation_key="incoming_video_horizontal_resolution",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="px",
        suggested_display_precision=0,
        api_versions=APIVERSION_AVR_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: (
            vp.horizontal_resolution
            if (vp := state.get_incoming_video_parameters()) is not None
            else None
        ),
    ),
    ArcamFmjSensorEntityDescription(
        key="incoming_video_vertical_resolution",
        translation_key="incoming_video_vertical_resolution",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="px",
        suggested_display_precision=0,
        api_versions=APIVERSION_AVR_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: (
            vp.vertical_resolution
            if (vp := state.get_incoming_video_parameters()) is not None
            else None
        ),
    ),
    ArcamFmjSensorEntityDescription(
        key="incoming_video_refresh_rate",
        translation_key="incoming_video_refresh_rate",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=0,
        api_versions=APIVERSION_AVR_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: (
            vp.refresh_rate
            if (vp := state.get_incoming_video_parameters()) is not None
            else None
        ),
    ),
    ArcamFmjSensorEntityDescription(
        key="incoming_video_aspect_ratio",
        translation_key="incoming_video_aspect_ratio",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(IncomingVideoAspectRatio),
        api_versions=APIVERSION_AVR_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: (
            _enum_value(vp.aspect_ratio)
            if (vp := state.get_incoming_video_parameters()) is not None
            else None
        ),
    ),
    ArcamFmjSensorEntityDescription(
        key="incoming_video_colorspace",
        translation_key="incoming_video_colorspace",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(IncomingVideoColorspace),
        api_versions=APIVERSION_AVR_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: (
            _enum_value(vp.colorspace)
            if (vp := state.get_incoming_video_parameters()) is not None
            else None
        ),
    ),
    ArcamFmjSensorEntityDescription(
        key="incoming_audio_format",
        translation_key="incoming_audio_format",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(IncomingAudioFormat),
        api_versions=APIVERSION_AVR_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: _enum_value(state.get_incoming_audio_format()[0]),
    ),
    ArcamFmjSensorEntityDescription(
        key="incoming_audio_config",
        translation_key="incoming_audio_config",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(IncomingAudioConfig),
        api_versions=APIVERSION_AVR_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: _enum_value(state.get_incoming_audio_format()[1]),
    ),
    ArcamFmjSensorEntityDescription(
        key="incoming_audio_sample_rate",
        translation_key="incoming_audio_sample_rate",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=0,
        api_versions=APIVERSION_AVR_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: (
            None
            if (sample_rate := state.get_incoming_audio_sample_rate()) == 0
            else sample_rate
        ),
    ),
    ArcamFmjSensorEntityDescription(
        key="software_version",
        translation_key="software_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        api_versions=set(),  # SOFTWARE_VERSION has no API version gate
        zones=frozenset({1}),
        value_fn=lambda state: state.get_software_version(),
    ),
    ArcamFmjSensorEntityDescription(
        key="lifter_temperature",
        translation_key="lifter_temperature",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        api_versions=APIVERSION_CLASS_G_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: state.get_lifter_temperature(),
    ),
    ArcamFmjSensorEntityDescription(
        key="output_temperature",
        translation_key="output_temperature",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        api_versions=APIVERSION_THERMAL_DIAGNOSTICS_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: state.get_output_temperature(),
    ),
    ArcamFmjSensorEntityDescription(
        key="dc_offset",
        translation_key="dc_offset",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        api_versions=APIVERSION_THERMAL_DIAGNOSTICS_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: state.get_dc_offset(),
    ),
    ArcamFmjSensorEntityDescription(
        key="short_circuit_status",
        translation_key="short_circuit_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        api_versions=APIVERSION_CLASS_G_SERIES,
        zones=frozenset({1}),
        value_fn=lambda state: state.get_short_circuit_status(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ArcamFmjConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Arcam FMJ sensors from a config entry."""
    runtime_data = config_entry.runtime_data
    model = runtime_data.model

    async_add_entities(
        ArcamFmjSensorEntity(coordinator, description)
        for coordinator in runtime_data.coordinators.values()
        for description in SENSORS
        if (not description.api_versions or model in description.api_versions)
        and coordinator.state.zn in description.zones
    )


class ArcamFmjSensorEntity(ArcamFmjDescriptionEntity, SensorEntity):
    """Representation of an Arcam FMJ sensor."""

    entity_description: ArcamFmjSensorEntityDescription

    @property
    def native_value(self) -> int | float | str | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.state)
