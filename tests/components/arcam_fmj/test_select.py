"""Tests for the Arcam FMJ select platform."""

from collections.abc import Generator
from unittest.mock import Mock, patch

from arcam.fmj import (
    CompressionMode,
    ConnectionFailed,
    DecodeMode2CH,
    DecodeModeMCH,
    DolbyAudioMode,
    ImaxEnhancedMode,
    RoomEqMode,
)
from arcam.fmj.state import State
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform

ENTITY_DECODE_2CH = "select.arcam_fmj_127_0_0_1_2_channel_decode_mode"
ENTITY_DECODE_MCH = "select.arcam_fmj_127_0_0_1_multi_channel_decode_mode"
ENTITY_DOLBY = "select.arcam_fmj_127_0_0_1_dolby_audio"
ENTITY_COMPRESSION = "select.arcam_fmj_127_0_0_1_dynamic_range_compression"
ENTITY_ROOM_EQ = "select.arcam_fmj_127_0_0_1_room_eq"
ENTITY_IMAX = "select.arcam_fmj_127_0_0_1_imax_enhanced"


@pytest.fixture(autouse=True)
def select_only() -> Generator[None]:
    """Limit platform setup to select only."""
    with patch("homeassistant.components.arcam_fmj.PLATFORMS", [Platform.SELECT]):
        yield


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "player_setup")
async def test_setup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Snapshot the registered select entities."""
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize("model", ["SA30"], indirect=True)
@pytest.mark.usefixtures("player_setup")
async def test_setup_filters_by_model(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Selects gated by API version don't appear on unsupported models.

    SA30 is APIVERSION_SA_SERIES (no decode modes, no Dolby Audio, no IMAX),
    but is in APIVERSION_DIRECT_MODE_SERIES so Room EQ shows up.
    """
    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    keys = {entry.unique_id.rsplit("-", 1)[-1] for entry in entries}
    assert "room_eq" in keys
    assert "decode_mode_2ch" not in keys
    assert "decode_mode_mch" not in keys
    assert "dolby_audio" not in keys
    assert "imax_enhanced" not in keys


@pytest.mark.usefixtures("player_setup")
async def test_decode_2ch_options_filter_by_model(
    hass: HomeAssistant,
) -> None:
    """DTS Neural:X only exists on 860+ — verify it appears for AVR550."""
    state = hass.states.get(ENTITY_DECODE_2CH)
    assert state is not None
    options = state.attributes["options"]
    # AVR550 is 860 series → Dolby PLII/IIx not available, Neural:X available
    assert "dts_neural_x" in options
    assert "dolby_pl" not in options


@pytest.mark.parametrize("model", ["AVR450"], indirect=True)
@pytest.mark.usefixtures("player_setup")
async def test_decode_2ch_options_for_450_series(hass: HomeAssistant) -> None:
    """AVR450 supports Dolby PLII/IIx modes but not DTS Neural:X."""
    state = hass.states.get(ENTITY_DECODE_2CH)
    assert state is not None
    options = state.attributes["options"]
    assert "dolby_pl" in options
    assert "dolby_plii_iix_movie" in options
    assert "dts_neural_x" not in options


@pytest.mark.parametrize(
    ("entity_id", "value", "expected"),
    [
        (ENTITY_DECODE_2CH, DecodeMode2CH.STEREO, "stereo"),
        (ENTITY_DECODE_2CH, DecodeMode2CH.MCH_STEREO, "mch_stereo"),
        (ENTITY_DECODE_MCH, DecodeModeMCH.MULTI_CHANNEL, "multi_channel"),
        (ENTITY_DOLBY, DolbyAudioMode.MOVIE, "movie"),
        (ENTITY_COMPRESSION, CompressionMode.HIGH, "high"),
        (ENTITY_ROOM_EQ, RoomEqMode.EQ2, "eq2"),
        (ENTITY_IMAX, ImaxEnhancedMode.AUTO, "auto"),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_current_option(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
    entity_id: str,
    value: object,
    expected: str,
) -> None:
    """Each select reflects the current library value."""
    method = {
        ENTITY_DECODE_2CH: "get_decode_mode_2ch",
        ENTITY_DECODE_MCH: "get_decode_mode_mch",
        ENTITY_DOLBY: "get_dolby_audio",
        ENTITY_COMPRESSION: "get_compression",
        ENTITY_ROOM_EQ: "get_room_equalization",
        ENTITY_IMAX: "get_imax_enhanced",
    }[entity_id]
    getattr(state_1, method).return_value = value
    client.notify_data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == expected


@pytest.mark.usefixtures("player_setup")
async def test_room_eq_not_calculated_reports_unknown(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
) -> None:
    """NOT_CALCULATED is excluded from options and reads as unknown."""
    state_1.get_room_equalization.return_value = RoomEqMode.NOT_CALCULATED
    client.notify_data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ROOM_EQ)
    assert state is not None
    assert state.state == STATE_UNKNOWN
    assert "not_calculated" not in state.attributes["options"]


@pytest.mark.parametrize(
    ("entity_id", "option", "method", "expected"),
    [
        (ENTITY_DECODE_2CH, "stereo", "set_decode_mode_2ch", DecodeMode2CH.STEREO),
        (
            ENTITY_DECODE_MCH,
            "stereo_downmix",
            "set_decode_mode_mch",
            DecodeModeMCH.STEREO_DOWNMIX,
        ),
        (ENTITY_DOLBY, "movie", "set_dolby_audio", DolbyAudioMode.MOVIE),
        (ENTITY_COMPRESSION, "medium", "set_compression", CompressionMode.MEDIUM),
        (ENTITY_ROOM_EQ, "eq1", "set_room_equalization", RoomEqMode.EQ1),
        (ENTITY_IMAX, "auto", "set_imax_enhanced", ImaxEnhancedMode.AUTO),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_select_option(
    hass: HomeAssistant,
    state_1: State,
    entity_id: str,
    option: str,
    method: str,
    expected: object,
) -> None:
    """Picking an option forwards the right enum value to the library."""
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
        blocking=True,
    )
    getattr(state_1, method).assert_called_once_with(expected)


@pytest.mark.usefixtures("player_setup")
async def test_select_option_unsupported_on_model(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """ValueError from the library surfaces as HomeAssistantError."""
    state_1.set_decode_mode_2ch.side_effect = ValueError("nope")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: ENTITY_DECODE_2CH, ATTR_OPTION: "stereo"},
            blocking=True,
        )


@pytest.mark.usefixtures("player_setup")
async def test_select_option_connection_failed(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """ConnectionFailed surfaces as HomeAssistantError via convert_exception."""
    state_1.set_dolby_audio.side_effect = ConnectionFailed()
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: ENTITY_DOLBY, ATTR_OPTION: "movie"},
            blocking=True,
        )


@pytest.mark.usefixtures("player_setup")
async def test_select_option_invalid(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """Unknown options raise ServiceValidationError before any send."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: ENTITY_DOLBY, ATTR_OPTION: "not_a_mode"},
            blocking=True,
        )
    state_1.set_dolby_audio.assert_not_called()


@pytest.mark.usefixtures("player_setup")
async def test_room_eq_uses_dirac_names(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
) -> None:
    """When the device reports DIRAC profile names, they appear in the option list."""
    state_1.get_room_eq_names.return_value = ["Living Room", "Kitchen", "Studio"]
    state_1.get_room_equalization.return_value = RoomEqMode.EQ2
    client.notify_data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ROOM_EQ)
    assert state is not None
    assert state.attributes["options"] == ["off", "Living Room", "Kitchen", "Studio"]
    assert state.state == "Kitchen"


@pytest.mark.usefixtures("player_setup")
async def test_room_eq_partial_dirac_names_fall_back(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
) -> None:
    """Empty or missing slot names fall back to the canonical eq1/eq2/eq3 keys."""
    state_1.get_room_eq_names.return_value = ["Living Room", "", "Studio"]
    client.notify_data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ROOM_EQ)
    assert state is not None
    assert state.attributes["options"] == ["off", "Living Room", "eq2", "Studio"]


@pytest.mark.usefixtures("player_setup")
async def test_room_eq_select_by_dirac_name(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
) -> None:
    """Selecting by a DIRAC name resolves to the matching RoomEqMode slot."""
    state_1.get_room_eq_names.return_value = ["Living Room", "Kitchen", "Studio"]
    client.notify_data_updated()
    await hass.async_block_till_done()

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: ENTITY_ROOM_EQ, ATTR_OPTION: "Kitchen"},
        blocking=True,
    )
    state_1.set_room_equalization.assert_called_with(RoomEqMode.EQ2)


@pytest.mark.usefixtures("player_setup")
async def test_room_eq_select_off_with_dirac_names(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
) -> None:
    """`off` remains selectable regardless of DIRAC names."""
    state_1.get_room_eq_names.return_value = ["Living Room", "Kitchen", "Studio"]
    client.notify_data_updated()
    await hass.async_block_till_done()

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: ENTITY_ROOM_EQ, ATTR_OPTION: "off"},
        blocking=True,
    )
    state_1.set_room_equalization.assert_called_with(RoomEqMode.OFF)


@pytest.mark.usefixtures("player_setup")
async def test_room_eq_falls_back_to_eq_keys_without_names(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """When the device hasn't sent ROOM_EQ_NAMES, options use eq1/eq2/eq3."""
    state = hass.states.get(ENTITY_ROOM_EQ)
    assert state is not None
    assert state.attributes["options"] == ["off", "eq1", "eq2", "eq3"]

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: ENTITY_ROOM_EQ, ATTR_OPTION: "eq3"},
        blocking=True,
    )
    state_1.set_room_equalization.assert_called_with(RoomEqMode.EQ3)
