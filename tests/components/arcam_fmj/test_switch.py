"""Tests for the Arcam FMJ switch platform."""

from collections.abc import Generator
from unittest.mock import Mock, patch

from arcam.fmj import ConnectionFailed
from arcam.fmj.state import State
import pytest
from syrupy.assertion import SnapshotAssertion

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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform

ENTITY_DIRECT_MODE = "switch.arcam_fmj_127_0_0_1_direct_mode"
ENTITY_PANORAMA = "switch.arcam_fmj_127_0_0_1_dolby_plii_iix_music_panorama"


@pytest.fixture(autouse=True)
def switch_only() -> Generator[None]:
    """Limit platform setup to switch only."""
    with patch("homeassistant.components.arcam_fmj.PLATFORMS", [Platform.SWITCH]):
        yield


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "player_setup")
async def test_setup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Snapshot the registered switch entities."""
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, STATE_ON), (False, STATE_OFF), (None, STATE_UNKNOWN)],
)
@pytest.mark.usefixtures("player_setup")
async def test_direct_mode_state(
    hass: HomeAssistant,
    state_1: State,
    client: Mock,
    value: bool | None,
    expected: str,
) -> None:
    """Direct mode switch reflects state.get_direct_mode()."""
    state_1.get_direct_mode.return_value = value
    client.notify_data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_DIRECT_MODE)
    assert state is not None
    assert state.state == expected


@pytest.mark.parametrize(
    ("service", "expected"),
    [(SERVICE_TURN_ON, True), (SERVICE_TURN_OFF, False)],
)
@pytest.mark.usefixtures("player_setup")
async def test_direct_mode_set(
    hass: HomeAssistant,
    state_1: State,
    service: str,
    expected: bool,
) -> None:
    """Turning the direct-mode switch on/off forwards to set_direct_mode()."""
    await hass.services.async_call(
        "switch",
        service,
        {ATTR_ENTITY_ID: ENTITY_DIRECT_MODE},
        blocking=True,
    )
    state_1.set_direct_mode.assert_called_once_with(expected)


@pytest.mark.parametrize("model", ["AVR450"], indirect=True)
@pytest.mark.usefixtures("player_setup")
async def test_panorama_set(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """Panorama switch appears only on 450 series and forwards correctly."""
    await hass.services.async_call(
        "switch",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_PANORAMA},
        blocking=True,
    )
    state_1.set_dolby_pliix_panorama.assert_called_once_with(True)


@pytest.mark.usefixtures("player_setup")
async def test_panorama_not_on_avr550(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """AVR550 (860 series) doesn't expose the Dolby PLII/IIx panorama switch."""
    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    keys = {entry.unique_id.rsplit("-", 1)[-1] for entry in entries}
    assert "dolby_pliix_panorama" not in keys


@pytest.mark.usefixtures("player_setup")
async def test_direct_mode_connection_failed(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """ConnectionFailed surfaces as HomeAssistantError."""
    state_1.set_direct_mode.side_effect = ConnectionFailed()
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch",
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: ENTITY_DIRECT_MODE},
            blocking=True,
        )
