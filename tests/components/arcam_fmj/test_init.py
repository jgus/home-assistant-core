"""Tests for the arcam_fmj integration setup."""

import asyncio
from collections.abc import Generator
import logging
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


@pytest.fixture
def arcam_caplog(
    caplog: pytest.LogCaptureFixture,
) -> Generator[pytest.LogCaptureFixture]:
    """Attach caplog's handler to the arcam_fmj logger.

    The integration's logger does not propagate records to pytest's caplog by
    default in this test environment, so we explicitly attach the handler and
    disable propagation while it is active to avoid duplicate records.
    """
    arcam_log = logging.getLogger("homeassistant.components.arcam_fmj")
    arcam_log.addHandler(caplog.handler)
    previous_level = arcam_log.level
    previous_propagate = arcam_log.propagate
    arcam_log.setLevel(logging.INFO)
    arcam_log.propagate = False
    try:
        yield caplog
    finally:
        arcam_log.removeHandler(caplog.handler)
        arcam_log.setLevel(previous_level)
        arcam_log.propagate = previous_propagate


@pytest.fixture
def short_sleep() -> Generator[None]:
    """Replace only the run-loop's sleep with a fast yield so retries are quick.

    Patching ``asyncio.sleep`` globally would break ``await asyncio.sleep(0)``
    in the test itself, so we keep the original behaviour for zero-delay sleeps
    and short-circuit the long backoff used by the integration.
    """

    original_sleep = asyncio.sleep

    async def _fast_sleep(delay: float) -> None:
        if delay <= 0:
            await original_sleep(0)
            return
        await original_sleep(0)

    with patch("homeassistant.components.arcam_fmj.asyncio") as fake_asyncio:
        fake_asyncio.sleep = _fast_sleep
        # Keep all other asyncio attributes pointing at the real module.
        fake_asyncio.timeout = asyncio.timeout
        yield


@pytest.mark.usefixtures("player_setup", "short_sleep")
async def test_run_client_logs_disconnect_and_reconnect(
    hass: HomeAssistant,
    client: Mock,
    arcam_caplog: pytest.LogCaptureFixture,
) -> None:
    """A dropped connection should warn once and the recovery should log at info."""
    client.notify_connection(ConnectionFailed())
    # Give the background task several cycles to disconnect, reconnect, and log.
    for _ in range(20):
        await asyncio.sleep(0)

    messages = [
        record.getMessage()
        for record in arcam_caplog.records
        if record.name == "homeassistant.components.arcam_fmj"
    ]
    assert any("Lost connection to Arcam FMJ" in m for m in messages)
    assert any("Reconnected to Arcam FMJ" in m for m in messages)


@pytest.mark.usefixtures("player_setup", "short_sleep")
async def test_run_client_does_not_spam_on_repeated_failures(
    hass: HomeAssistant,
    client: Mock,
    arcam_caplog: pytest.LogCaptureFixture,
) -> None:
    """Subsequent failures while still disconnected should not log additional warnings."""
    # Force subsequent start() attempts to fail before the current connection
    # drops, so retries after the initial disconnect exercise the silent path.
    client.start.side_effect = ConnectionFailed()
    client.notify_connection(ConnectionFailed())
    for _ in range(20):
        await asyncio.sleep(0)

    messages = [
        record.getMessage()
        for record in arcam_caplog.records
        if record.name == "homeassistant.components.arcam_fmj"
    ]
    assert sum("Lost connection to Arcam FMJ" in m for m in messages) == 1
    assert not any("Reconnected" in m for m in messages)
