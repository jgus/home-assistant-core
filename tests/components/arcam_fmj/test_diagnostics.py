"""Tests for the arcam_fmj diagnostics platform."""

from syrupy.assertion import SnapshotAssertion
from syrupy.filters import props

from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry
from tests.components.diagnostics import get_diagnostics_for_config_entry
from tests.typing import ClientSessionGenerator


async def test_entry_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
    player_setup: None,
) -> None:
    """Snapshot the diagnostic payload for a configured entry."""
    result = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )

    assert result == snapshot(
        exclude=props("created_at", "modified_at", "entry_id", "discovery_keys")
    )
