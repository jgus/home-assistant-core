"""Tests for the Arcam FMJ number platform."""

from collections.abc import Generator
from unittest.mock import Mock, patch

from arcam.fmj import ConnectionFailed
from arcam.fmj.state import State
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform

ENTITY_BASS = "number.arcam_fmj_127_0_0_1_bass_equalization"
ENTITY_TREBLE = "number.arcam_fmj_127_0_0_1_treble_equalization"
ENTITY_BALANCE = "number.arcam_fmj_127_0_0_1_balance"
ENTITY_SUB_TRIM = "number.arcam_fmj_127_0_0_1_subwoofer_trim"
ENTITY_SUB_STEREO_TRIM = "number.arcam_fmj_127_0_0_1_sub_stereo_trim"
ENTITY_LIPSYNC = "number.arcam_fmj_127_0_0_1_lip_sync_delay"


@pytest.fixture(autouse=True)
def number_only() -> Generator[None]:
    """Limit platform setup to number only."""
    with patch("homeassistant.components.arcam_fmj.PLATFORMS", [Platform.NUMBER]):
        yield


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "player_setup")
async def test_setup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Snapshot the registered number entities."""
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize("model", ["SA30"], indirect=True)
@pytest.mark.usefixtures("player_setup")
async def test_sa_series_only_balance(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """SA-series stereo amps only see balance; the AVR-only trims are skipped."""
    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    keys = {entry.unique_id.rsplit("-", 1)[-1] for entry in entries}
    assert "balance" in keys
    assert "bass_equalization" not in keys
    assert "subwoofer_trim" not in keys


@pytest.mark.usefixtures("player_setup")
async def test_sub_stereo_trim_zone_1_only(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """sub_stereo_trim has no ZONE_SUPPORT — only the zone-1 entity exists."""
    entries = [
        entry
        for entry in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
        if entry.unique_id.endswith("-sub_stereo_trim")
    ]
    assert len(entries) == 1
    assert "-1-sub_stereo_trim" in entries[0].unique_id


@pytest.mark.parametrize(
    ("entity_id", "method", "value"),
    [
        (ENTITY_BASS, "get_bass_equalization", 3.0),
        (ENTITY_TREBLE, "get_treble_equalization", -2.0),
        (ENTITY_BALANCE, "get_balance", 1.0),
        (ENTITY_SUB_TRIM, "get_subwoofer_trim", 0.5),
        (ENTITY_SUB_STEREO_TRIM, "get_sub_stereo_trim", -2.5),
        (ENTITY_LIPSYNC, "get_lipsync_delay", 40),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_native_value(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
    entity_id: str,
    method: str,
    value: float,
) -> None:
    """Each number reflects the library getter."""
    getattr(state_1, method).return_value = value
    client.notify_data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == value


@pytest.mark.parametrize(
    ("entity_id", "value", "method", "expected"),
    [
        (ENTITY_BASS, 5.0, "set_bass_equalization", 5.0),
        (ENTITY_TREBLE, -8.0, "set_treble_equalization", -8.0),
        (ENTITY_BALANCE, 2.0, "set_balance", 2.0),
        (ENTITY_SUB_TRIM, 1.5, "set_subwoofer_trim", 1.5),
        (ENTITY_SUB_STEREO_TRIM, -3.5, "set_sub_stereo_trim", -3.5),
        (ENTITY_LIPSYNC, 100, "set_lipsync_delay", 100),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_set_value(
    hass: HomeAssistant,
    state_1: State,
    entity_id: str,
    value: float,
    method: str,
    expected: float,
) -> None:
    """Picking a value forwards it to the library setter."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )
    getattr(state_1, method).assert_called_once_with(expected)


@pytest.mark.usefixtures("player_setup")
async def test_set_value_connection_failed(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """ConnectionFailed surfaces as HomeAssistantError."""
    state_1.set_bass_equalization.side_effect = ConnectionFailed()
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: ENTITY_BASS, ATTR_VALUE: 0},
            blocking=True,
        )


@pytest.mark.parametrize("model", ["SA30"], indirect=True)
@pytest.mark.parametrize(
    ("key", "method", "value"),
    [
        ("max_turn_on_volume", "set_max_turn_on_volume", 30),
        ("max_volume", "set_max_volume", 75),
        ("max_streaming_volume", "set_max_streaming_volume", 50),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_app_safety_volume_ceilings(
    hass: HomeAssistant,
    state_1: State,
    key: str,
    method: str,
    value: int,
) -> None:
    """Volume ceilings appear on app-safety models and accept int values."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: f"number.arcam_fmj_127_0_0_1_{key}", ATTR_VALUE: value},
        blocking=True,
    )
    getattr(state_1, method).assert_called_once_with(value)


@pytest.mark.parametrize("model", ["AVR450"], indirect=True)
@pytest.mark.parametrize(
    ("key", "method"),
    [
        ("dolby_plii_iix_music_dimension", "set_dolby_pliix_dimension"),
        ("dolby_plii_iix_music_centre_width", "set_dolby_pliix_centre_width"),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_dolby_pliix_number(
    hass: HomeAssistant,
    state_1: State,
    key: str,
    method: str,
) -> None:
    """Dolby PLII/IIx number entities appear on 450 series only."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: f"number.arcam_fmj_127_0_0_1_{key}", ATTR_VALUE: 3},
        blocking=True,
    )
    getattr(state_1, method).assert_called_once_with(3)


@pytest.mark.usefixtures("player_setup")
async def test_volume_ceilings_not_on_default_model(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The default test model (AVR550) isn't in APIVERSION_APP_SAFETY_SERIES."""
    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    keys = {entry.unique_id.rsplit("-", 1)[-1] for entry in entries}
    assert "max_volume" not in keys
    assert "max_turn_on_volume" not in keys
    assert "max_streaming_volume" not in keys
    assert "dolby_pliix_dimension" not in keys


