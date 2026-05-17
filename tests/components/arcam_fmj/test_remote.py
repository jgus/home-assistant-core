"""Tests for the Arcam FMJ remote platform."""

from collections.abc import Generator
from unittest.mock import Mock, call, patch

from arcam.fmj import (
    ConnectionFailed,
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
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.remote import (
    ATTR_COMMAND,
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DOMAIN as REMOTE_DOMAIN,
    SERVICE_SEND_COMMAND,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform

REMOTE_ENTITY_ID = "remote.arcam_fmj_127_0_0_1"


@pytest.fixture(autouse=True)
def remote_only() -> Generator[None]:
    """Limit platform setup to remote only."""
    with patch("homeassistant.components.arcam_fmj.PLATFORMS", [Platform.REMOTE]):
        yield


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "player_setup")
async def test_setup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Snapshot the registered remote entities."""
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize(
    ("power", "expected"),
    [(True, STATE_ON), (False, STATE_OFF), (None, STATE_UNKNOWN)],
)
@pytest.mark.usefixtures("player_setup")
async def test_state_tracks_power(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
    power: bool | None,
    expected: str,
) -> None:
    """Power state should drive the remote on/off state."""
    state_1.get_power.return_value = power
    client.notify_data_updated()
    await hass.async_block_till_done()

    assert hass.states.get(REMOTE_ENTITY_ID).state == expected


@pytest.mark.parametrize(
    ("service", "power_arg"),
    [(SERVICE_TURN_ON, True), (SERVICE_TURN_OFF, False)],
)
@pytest.mark.usefixtures("player_setup")
async def test_turn_on_off(
    hass: HomeAssistant,
    state_1: State,
    service: str,
    power_arg: bool,
) -> None:
    """Turn on/off should call set_power with the corresponding boolean."""
    await hass.services.async_call(
        REMOTE_DOMAIN,
        service,
        {ATTR_ENTITY_ID: REMOTE_ENTITY_ID},
        blocking=True,
    )
    state_1.set_power.assert_called_once_with(power_arg)


@pytest.mark.parametrize(
    ("command", "method", "expected"),
    [
        ("up", "send_navigation", RC5CodeNavigation.UP),
        ("return", "send_navigation", RC5CodeNavigation.RETURN),
        ("red", "send_color", RC5CodeColor.RED),
        ("blue", "send_color", RC5CodeColor.BLUE),
        ("radio", "send_toggle", RC5CodeToggle.RADIO),
        ("display_brightness", "send_toggle", RC5CodeToggle.DISPLAY_BRIGHTNESS),
        ("play", "send_playback", RC5CodePlayback.PLAY),
        ("eject", "send_playback", RC5CodePlayback.EJECT),
        ("bass", "send_menu_access", RC5CodeMenuAccess.BASS),
        ("speaker_trim", "send_menu_access", RC5CodeMenuAccess.SPEAKER_TRIM),
        ("hdmi_out_1", "set_hdmi_output", HdmiOutput.OUT_1),
        ("hdmi_out_1_2", "set_hdmi_output", HdmiOutput.OUT_1_2),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_send_command_enum(
    hass: HomeAssistant,
    state_1: State,
    command: str,
    method: str,
    expected: object,
) -> None:
    """Each named command dispatches to the matching enum sender."""
    await hass.services.async_call(
        REMOTE_DOMAIN,
        SERVICE_SEND_COMMAND,
        {ATTR_ENTITY_ID: REMOTE_ENTITY_ID, ATTR_COMMAND: [command]},
        blocking=True,
    )
    getattr(state_1, method).assert_called_once_with(expected)


@pytest.mark.parametrize("digit", [0, 5, 9])
@pytest.mark.usefixtures("player_setup")
async def test_send_command_numeric(
    hass: HomeAssistant,
    state_1: State,
    digit: int,
) -> None:
    """Digit commands route to send_numeric with the digit as int."""
    await hass.services.async_call(
        REMOTE_DOMAIN,
        SERVICE_SEND_COMMAND,
        {ATTR_ENTITY_ID: REMOTE_ENTITY_ID, ATTR_COMMAND: [str(digit)]},
        blocking=True,
    )
    state_1.send_numeric.assert_called_once_with(digit)


@pytest.mark.parametrize(
    ("command", "method", "expected"),
    [
        ("source_cd", "set_source", SourceCodes.CD),
        ("source_bd", "set_source", SourceCodes.BD),
        ("source_net_usb", "set_source", SourceCodes.NET_USB),
        ("decode_2ch_stereo", "set_decode_mode_2ch", DecodeMode2CH.STEREO),
        (
            "decode_2ch_dolby_plii_iix_movie",
            "set_decode_mode_2ch",
            DecodeMode2CH.DOLBY_PLII_IIx_MOVIE,
        ),
        (
            "decode_mch_stereo_downmix",
            "set_decode_mode_mch",
            DecodeModeMCH.STEREO_DOWNMIX,
        ),
        ("display_brightness_off", "set_display_brightness", DisplayBrightness.OFF),
        ("display_brightness_l1", "set_display_brightness", DisplayBrightness.L1),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_send_command_redundant_enum(
    hass: HomeAssistant,
    state_1: State,
    command: str,
    method: str,
    expected: object,
) -> None:
    """The 'redundant' enum commands forward to the right library method."""
    await hass.services.async_call(
        REMOTE_DOMAIN,
        SERVICE_SEND_COMMAND,
        {ATTR_ENTITY_ID: REMOTE_ENTITY_ID, ATTR_COMMAND: [command]},
        blocking=True,
    )
    getattr(state_1, method).assert_called_once_with(expected)


@pytest.mark.parametrize(
    ("command", "method", "args"),
    [
        ("power_on", "set_power", (True,)),
        ("power_off", "set_power", (False,)),
        ("mute_on", "set_mute", (True,)),
        ("mute_off", "set_mute", (False,)),
        ("volume_up", "inc_volume", ()),
        ("volume_down", "dec_volume", ()),
        ("direct_mode_on", "set_direct_mode", (True,)),
        ("direct_mode_off", "set_direct_mode", (False,)),
        ("dolby_pliix_panorama_on", "set_dolby_pliix_panorama", (True,)),
        ("dolby_pliix_panorama_off", "set_dolby_pliix_panorama", (False,)),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_send_command_redundant_bool(
    hass: HomeAssistant,
    state_1: State,
    command: str,
    method: str,
    args: tuple,
) -> None:
    """The 'redundant' on/off and inc/dec commands route correctly."""
    await hass.services.async_call(
        REMOTE_DOMAIN,
        SERVICE_SEND_COMMAND,
        {ATTR_ENTITY_ID: REMOTE_ENTITY_ID, ATTR_COMMAND: [command]},
        blocking=True,
    )
    getattr(state_1, method).assert_called_once_with(*args)


@pytest.mark.parametrize(
    ("command", "method"),
    [
        ("bass_up", "inc_bass_equalization"),
        ("bass_down", "dec_bass_equalization"),
        ("treble_up", "inc_treble_equalization"),
        ("treble_down", "dec_treble_equalization"),
        ("balance_right", "inc_balance"),
        ("balance_left", "dec_balance"),
        ("sub_trim_up", "inc_subwoofer_trim"),
        ("sub_trim_down", "dec_subwoofer_trim"),
        ("lipsync_up", "inc_lipsync_delay"),
        ("lipsync_down", "dec_lipsync_delay"),
        ("dolby_pliix_centre_width_up", "inc_dolby_pliix_centre_width"),
        ("dolby_pliix_centre_width_down", "dec_dolby_pliix_centre_width"),
        ("dolby_pliix_dimension_up", "inc_dolby_pliix_dimension"),
        ("dolby_pliix_dimension_down", "dec_dolby_pliix_dimension"),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_send_command_inc_dec(
    hass: HomeAssistant,
    state_1: State,
    command: str,
    method: str,
) -> None:
    """Inc/dec command names route to the matching library method."""
    await hass.services.async_call(
        REMOTE_DOMAIN,
        SERVICE_SEND_COMMAND,
        {ATTR_ENTITY_ID: REMOTE_ENTITY_ID, ATTR_COMMAND: [command]},
        blocking=True,
    )
    getattr(state_1, method).assert_called_once_with()


@pytest.mark.usefixtures("player_setup")
async def test_send_command_case_insensitive(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """Command lookup ignores case."""
    await hass.services.async_call(
        REMOTE_DOMAIN,
        SERVICE_SEND_COMMAND,
        {ATTR_ENTITY_ID: REMOTE_ENTITY_ID, ATTR_COMMAND: ["UP"]},
        blocking=True,
    )
    state_1.send_navigation.assert_called_once_with(RC5CodeNavigation.UP)


@pytest.mark.usefixtures("player_setup")
async def test_send_command_sequence(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """Multi-command sequences dispatch each command in order."""
    await hass.services.async_call(
        REMOTE_DOMAIN,
        SERVICE_SEND_COMMAND,
        {
            ATTR_ENTITY_ID: REMOTE_ENTITY_ID,
            ATTR_COMMAND: ["menu", "down", "ok"],
            ATTR_DELAY_SECS: 0,
        },
        blocking=True,
    )
    assert state_1.send_navigation.await_args_list == [
        call(RC5CodeNavigation.MENU),
        call(RC5CodeNavigation.DOWN),
        call(RC5CodeNavigation.OK),
    ]


@pytest.mark.usefixtures("player_setup")
async def test_send_command_num_repeats(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """num_repeats causes the sequence to be sent multiple times."""
    await hass.services.async_call(
        REMOTE_DOMAIN,
        SERVICE_SEND_COMMAND,
        {
            ATTR_ENTITY_ID: REMOTE_ENTITY_ID,
            ATTR_COMMAND: ["up"],
            ATTR_NUM_REPEATS: 3,
            ATTR_DELAY_SECS: 0,
        },
        blocking=True,
    )
    assert state_1.send_navigation.await_count == 3


@pytest.mark.usefixtures("player_setup")
async def test_send_command_invalid_command(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """Unknown commands raise ServiceValidationError before any send is attempted."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            REMOTE_DOMAIN,
            SERVICE_SEND_COMMAND,
            {ATTR_ENTITY_ID: REMOTE_ENTITY_ID, ATTR_COMMAND: ["bogus"]},
            blocking=True,
        )

    state_1.send_navigation.assert_not_called()
    state_1.send_color.assert_not_called()
    state_1.send_toggle.assert_not_called()
    state_1.send_numeric.assert_not_called()


@pytest.mark.usefixtures("player_setup")
async def test_send_command_unsupported_on_model(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """A library ValueError (e.g. unsupported on model) surfaces as HomeAssistantError."""
    state_1.send_navigation.side_effect = ValueError("not supported")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            REMOTE_DOMAIN,
            SERVICE_SEND_COMMAND,
            {ATTR_ENTITY_ID: REMOTE_ENTITY_ID, ATTR_COMMAND: ["up"]},
            blocking=True,
        )


@pytest.mark.usefixtures("player_setup")
async def test_send_command_connection_failed(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """ConnectionFailed surfaces as HomeAssistantError via the shared decorator."""
    state_1.send_navigation.side_effect = ConnectionFailed()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            REMOTE_DOMAIN,
            SERVICE_SEND_COMMAND,
            {ATTR_ENTITY_ID: REMOTE_ENTITY_ID, ATTR_COMMAND: ["up"]},
            blocking=True,
        )


@pytest.mark.usefixtures("player_setup")
async def test_turn_on_connection_failed(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """ConnectionFailed during turn_on surfaces as HomeAssistantError."""
    state_1.set_power.side_effect = ConnectionFailed()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            REMOTE_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: REMOTE_ENTITY_ID},
            blocking=True,
        )
