"""Arcam FMJ select entities."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from arcam.fmj import (
    APIVERSION_AVR_SERIES,
    APIVERSION_DIRECT_MODE_SERIES,
    APIVERSION_IMAX_SERIES,
    CompressionMode,
    DecodeMode2CH,
    DecodeModeMCH,
    DolbyAudioMode,
    ImaxEnhancedMode,
    IntOrTypeEnum,
    RoomEqMode,
)
from arcam.fmj.state import State

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import ArcamFmjConfigEntry, ArcamFmjCoordinator
from .entity import (
    ArcamFmjDescriptionEntity,
    convert_exception,
    unsupported_command_error,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ArcamFmjSelectEntityDescription[E: IntOrTypeEnum](SelectEntityDescription):
    """Describes an Arcam FMJ select entity backed by a library enum."""

    api_versions: set[str]
    zones: frozenset[int] = frozenset({1, 2})
    enum_type: type[E]
    excluded_values: frozenset[str] = field(default_factory=frozenset)
    value_fn: Callable[[State], E | None]
    set_fn: Callable[[State, E], Awaitable[None]]


SELECTS: tuple[ArcamFmjSelectEntityDescription, ...] = (
    ArcamFmjSelectEntityDescription(
        key="decode_mode_2ch",
        translation_key="decode_mode_2ch",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_AVR_SERIES,
        zones=frozenset({1}),
        enum_type=DecodeMode2CH,
        value_fn=lambda state: state.get_decode_mode_2ch(),
        set_fn=lambda state, mode: state.set_decode_mode_2ch(mode),
    ),
    ArcamFmjSelectEntityDescription(
        key="decode_mode_mch",
        translation_key="decode_mode_mch",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_AVR_SERIES,
        zones=frozenset({1}),
        enum_type=DecodeModeMCH,
        value_fn=lambda state: state.get_decode_mode_mch(),
        set_fn=lambda state, mode: state.set_decode_mode_mch(mode),
    ),
    ArcamFmjSelectEntityDescription(
        key="dolby_audio",
        translation_key="dolby_audio",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_AVR_SERIES,
        enum_type=DolbyAudioMode,
        value_fn=lambda state: state.get_dolby_audio(),
        set_fn=lambda state, mode: state.set_dolby_audio(mode),
    ),
    ArcamFmjSelectEntityDescription(
        key="compression",
        translation_key="compression",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_AVR_SERIES,
        enum_type=CompressionMode,
        value_fn=lambda state: state.get_compression(),
        set_fn=lambda state, mode: state.set_compression(mode),
    ),
    ArcamFmjSelectEntityDescription(
        key="room_eq",
        translation_key="room_eq",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_DIRECT_MODE_SERIES,
        enum_type=RoomEqMode,
        excluded_values=frozenset({"NOT_CALCULATED"}),
        value_fn=lambda state: state.get_room_equalization(),
        set_fn=lambda state, mode: state.set_room_equalization(mode),
    ),
    ArcamFmjSelectEntityDescription(
        key="imax_enhanced",
        translation_key="imax_enhanced",
        entity_category=EntityCategory.CONFIG,
        api_versions=APIVERSION_IMAX_SERIES,
        zones=frozenset({1}),
        enum_type=ImaxEnhancedMode,
        value_fn=lambda state: state.get_imax_enhanced(),
        set_fn=lambda state, mode: state.set_imax_enhanced(mode),
    ),
)


def _supported_members(
    description: ArcamFmjSelectEntityDescription,
    model: str,
) -> list[IntOrTypeEnum]:
    """Return enum members the given model can actually use."""
    return [
        m
        for m in description.enum_type
        if not m.name.startswith("CODE_")
        and m.name not in description.excluded_values
        and (m.version is None or model in m.version)
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ArcamFmjConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Arcam FMJ select entities from a config entry."""
    runtime_data = config_entry.runtime_data
    model = runtime_data.model

    entities: list[SelectEntity] = []
    for coordinator in runtime_data.coordinators.values():
        for description in SELECTS:
            if model not in description.api_versions:
                continue
            if coordinator.state.zn not in description.zones:
                continue
            if description.key == "room_eq":
                entities.append(ArcamFmjRoomEqSelect(coordinator, description))
                continue
            members = _supported_members(description, model)
            if not members:
                continue
            entities.append(ArcamFmjSelect(coordinator, description, members))

    async_add_entities(entities)


class ArcamFmjSelect(ArcamFmjDescriptionEntity, SelectEntity):
    """Representation of an Arcam FMJ select entity."""

    entity_description: ArcamFmjSelectEntityDescription[IntOrTypeEnum]

    def __init__(
        self,
        coordinator: ArcamFmjCoordinator,
        description: ArcamFmjSelectEntityDescription,
        members: list[IntOrTypeEnum],
    ) -> None:
        """Initialize the select entity with its model-filtered options."""
        super().__init__(coordinator, description)
        self._attr_options = [m.name.lower() for m in members]
        self._option_to_member: dict[str, IntOrTypeEnum] = {
            m.name.lower(): m for m in members
        }

    @property
    def current_option(self) -> str | None:
        """Return the current selection, or None if unknown / filtered out."""
        value = self.entity_description.value_fn(self.coordinator.state)
        if value is None:
            return None
        name = value.name.lower()
        return name if name in self._option_to_member else None

    @convert_exception
    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        member = self._option_to_member.get(option)
        if member is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_option",
                translation_placeholders={"option": option},
            )

        try:
            await self.entity_description.set_fn(self.coordinator.state, member)
        except ValueError as err:
            raise unsupported_command_error(option) from err

        self.async_write_ha_state()


class ArcamFmjRoomEqSelect(ArcamFmjDescriptionEntity, SelectEntity):
    """Room EQ select with live DIRAC profile names.

    Profile slots 1-3 display under their device-configured names where
    available, falling back to the translated `eq1`/`eq2`/`eq3` labels.
    The names arrive via the listener pipeline like any other state, so
    `options` is computed live rather than cached at construction.
    """

    entity_description: ArcamFmjSelectEntityDescription[RoomEqMode]
    _SLOT_MODES = (RoomEqMode.EQ1, RoomEqMode.EQ2, RoomEqMode.EQ3)
    _SLOT_FALLBACKS = ("eq1", "eq2", "eq3")

    def _slot_labels(self) -> tuple[str, ...]:
        names = self.coordinator.state.get_room_eq_names() or []
        return tuple(
            names[i] if i < len(names) and names[i] else fallback
            for i, fallback in enumerate(self._SLOT_FALLBACKS)
        )

    @property
    def options(self) -> list[str]:
        """Return ["off", <slot 1 label>, <slot 2 label>, <slot 3 label>]."""
        return ["off", *self._slot_labels()]

    @property
    def current_option(self) -> str | None:
        """Map the current RoomEqMode back to a label, or None if not selectable."""
        value = self.coordinator.state.get_room_equalization()
        if value is None:
            return None
        if value == RoomEqMode.OFF:
            return "off"
        try:
            return self._slot_labels()[self._SLOT_MODES.index(value)]
        except ValueError:
            return None

    @convert_exception
    async def async_select_option(self, option: str) -> None:
        """Resolve the label (or "off") back to a RoomEqMode and send it."""
        if option == "off":
            mode = RoomEqMode.OFF
        else:
            try:
                mode = self._SLOT_MODES[self._slot_labels().index(option)]
            except ValueError as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_option",
                    translation_placeholders={"option": option},
                ) from err

        try:
            await self.coordinator.state.set_room_equalization(mode)
        except ValueError as err:
            raise unsupported_command_error(option) from err

        self.async_write_ha_state()
