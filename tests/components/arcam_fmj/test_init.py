"""Tests for the arcam_fmj integration setup."""

from unittest.mock import AsyncMock, Mock, patch

from arcam.fmj import ConnectionFailed
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry


@pytest.mark.parametrize("side_effect", [ConnectionFailed(), TimeoutError()])
async def test_setup_retries_when_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    side_effect: Exception,
) -> None:
    """Setup should signal a retry instead of succeeding when the device is unreachable."""
    client = Mock()
    client.host = "127.0.0.1"
    client.port = 50000
    client.start = AsyncMock(side_effect=side_effect)
    client.stop = AsyncMock()

    with patch("homeassistant.components.arcam_fmj.Client", return_value=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.usefixtures("player_setup")
async def test_disconnect_marks_all_entities_unavailable(
    hass: HomeAssistant,
    client: Mock,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """All entities across platforms should become unavailable on disconnect."""
    entries = [
        entry
        for entry in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
        if entry.disabled_by is None
    ]
    assert {entry.entity_id.split(".", 1)[0] for entry in entries} == {
        "binary_sensor",
        "media_player",
        "sensor",
    }
    for entry in entries:
        state = hass.states.get(entry.entity_id)
        assert state is not None
        assert state.state != STATE_UNAVAILABLE

    client.notify_connection(ConnectionFailed())
    await hass.async_block_till_done()

    for entry in entries:
        state = hass.states.get(entry.entity_id)
        assert state is not None
        assert state.state == STATE_UNAVAILABLE
