"""Arcam FMJ remote for RC5 IR command simulation."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from arcam.fmj import (
    DecodeMode2CH,
    DecodeModeMCH,
    DisplayBrightness,
    HdmiOutput,
    RC5CodeColor,
    RC5CodeMenuAccess,
    RC5CodeNavigation,
    RC5CodePlayback,
    RC5CodeToggle,
    SourceCodes,
)
from arcam.fmj.state import State

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    RemoteEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import ArcamFmjConfigEntry, ArcamFmjCoordinator
from .entity import ArcamFmjEntity, convert_exception, unsupported_command_error

PARALLEL_UPDATES = 0


type _CommandSender = Callable[[State], Awaitable[None]]


def _navigation(code: RC5CodeNavigation) -> _CommandSender:
    return lambda state: state.send_navigation(code)


def _color(code: RC5CodeColor) -> _CommandSender:
    return lambda state: state.send_color(code)


def _toggle(code: RC5CodeToggle) -> _CommandSender:
    return lambda state: state.send_toggle(code)


def _playback(code: RC5CodePlayback) -> _CommandSender:
    return lambda state: state.send_playback(code)


def _menu_access(code: RC5CodeMenuAccess) -> _CommandSender:
    return lambda state: state.send_menu_access(code)


def _hdmi(output: HdmiOutput) -> _CommandSender:
    return lambda state: state.set_hdmi_output(output)


def _source(src: SourceCodes) -> _CommandSender:
    return lambda state: state.set_source(src)


def _decode_2ch(mode: DecodeMode2CH) -> _CommandSender:
    return lambda state: state.set_decode_mode_2ch(mode)


def _decode_mch(mode: DecodeModeMCH) -> _CommandSender:
    return lambda state: state.set_decode_mode_mch(mode)


def _display(level: DisplayBrightness) -> _CommandSender:
    return lambda state: state.set_display_brightness(level)


def _numeric(digit: int) -> _CommandSender:
    return lambda state: state.send_numeric(digit)


COMMANDS: dict[str, _CommandSender] = {
    **{code.name.lower(): _navigation(code) for code in RC5CodeNavigation},
    **{str(digit): _numeric(digit) for digit in range(10)},
    **{code.name.lower(): _color(code) for code in RC5CodeColor},
    **{code.name.lower(): _toggle(code) for code in RC5CodeToggle},
    **{code.name.lower(): _playback(code) for code in RC5CodePlayback},
    **{code.name.lower(): _menu_access(code) for code in RC5CodeMenuAccess},
    "hdmi_out_1": _hdmi(HdmiOutput.OUT_1),
    "hdmi_out_2": _hdmi(HdmiOutput.OUT_2),
    "hdmi_out_1_2": _hdmi(HdmiOutput.OUT_1_2),
    "bass_up": lambda state: state.inc_bass_equalization(),
    "bass_down": lambda state: state.dec_bass_equalization(),
    "treble_up": lambda state: state.inc_treble_equalization(),
    "treble_down": lambda state: state.dec_treble_equalization(),
    "balance_right": lambda state: state.inc_balance(),
    "balance_left": lambda state: state.dec_balance(),
    "sub_trim_up": lambda state: state.inc_subwoofer_trim(),
    "sub_trim_down": lambda state: state.dec_subwoofer_trim(),
    "lipsync_up": lambda state: state.inc_lipsync_delay(),
    "lipsync_down": lambda state: state.dec_lipsync_delay(),
    "dolby_pliix_centre_width_up": lambda s: s.inc_dolby_pliix_centre_width(),
    "dolby_pliix_centre_width_down": lambda s: s.dec_dolby_pliix_centre_width(),
    "dolby_pliix_dimension_up": lambda s: s.inc_dolby_pliix_dimension(),
    "dolby_pliix_dimension_down": lambda s: s.dec_dolby_pliix_dimension(),
    # The commands below duplicate things already controllable through other
    # entities (media_player, select, switch). They exist so users who think
    # in terms of a physical Arcam remote can drive every button from
    # remote.send_command. The library picks the right transport (RC5 or a
    # direct command) per model under the hood.
    **{f"source_{src.name.lower()}": _source(src) for src in SourceCodes},
    **{f"decode_2ch_{m.name.lower()}": _decode_2ch(m) for m in DecodeMode2CH},
    **{f"decode_mch_{m.name.lower()}": _decode_mch(m) for m in DecodeModeMCH},
    **{
        f"display_brightness_{level.name.lower()}": _display(level)
        for level in DisplayBrightness
    },
    "power_on": lambda state: state.set_power(True),
    "power_off": lambda state: state.set_power(False),
    "mute_on": lambda state: state.set_mute(True),
    "mute_off": lambda state: state.set_mute(False),
    "volume_up": lambda state: state.inc_volume(),
    "volume_down": lambda state: state.dec_volume(),
    "direct_mode_on": lambda state: state.set_direct_mode(True),
    "direct_mode_off": lambda state: state.set_direct_mode(False),
    "dolby_pliix_panorama_on": lambda state: state.set_dolby_pliix_panorama(True),
    "dolby_pliix_panorama_off": lambda state: state.set_dolby_pliix_panorama(False),
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
    async_add_entities(
        ArcamFmjRemote(coordinator)
        for coordinator in config_entry.runtime_data.coordinators.values()
    )


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
                    raise unsupported_command_error(name) from err
