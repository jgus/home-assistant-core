"""Tests for Arcam FMJ sensor entities."""

from collections.abc import Generator
from unittest.mock import Mock, patch

from arcam.fmj import IncomingVideoAspectRatio, IncomingVideoColorspace
from arcam.fmj.state import IncomingAudioConfig, IncomingAudioFormat, State
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform


@pytest.fixture(autouse=True)
def sensor_only() -> Generator[None]:
    """Limit platform setup to sensor only."""
    with patch("homeassistant.components.arcam_fmj.PLATFORMS", [Platform.SENSOR]):
        yield


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "player_setup")
async def test_setup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test snapshot of the sensor platform."""
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.usefixtures("player_setup")
async def test_sensor_video_parameters(
    hass: HomeAssistant,
    state_1: State,
    client: Mock,
) -> None:
    """Test video parameter sensors with actual data."""
    video_params = Mock()
    video_params.horizontal_resolution = 1920
    video_params.vertical_resolution = 1080
    video_params.refresh_rate = 60.0
    video_params.aspect_ratio = IncomingVideoAspectRatio.ASPECT_16_9
    video_params.colorspace = IncomingVideoColorspace.HDR10

    state_1.get_incoming_video_parameters.return_value = video_params
    client.notify_data_updated()
    await hass.async_block_till_done()

    expected = {
        "incoming_video_horizontal_resolution": "1920",
        "incoming_video_vertical_resolution": "1080",
        "incoming_video_refresh_rate": "60.0",
        "incoming_video_aspect_ratio": "aspect_16_9",
        "incoming_video_colorspace": "hdr10",
    }
    for key, value in expected.items():
        state = hass.states.get(f"sensor.arcam_fmj_127_0_0_1_{key}")
        assert state is not None, f"State missing for {key}"
        assert state.state == value, f"Expected {value} for {key}, got {state.state}"


@pytest.mark.usefixtures("player_setup")
async def test_sensor_audio_parameters(
    hass: HomeAssistant,
    state_1: State,
    client: Mock,
) -> None:
    """Test audio parameter sensors with actual data."""
    state_1.get_incoming_audio_format.return_value = (
        IncomingAudioFormat.PCM,
        IncomingAudioConfig.STEREO_ONLY,
    )
    state_1.get_incoming_audio_sample_rate.return_value = 48000

    client.notify_data_updated()
    await hass.async_block_till_done()

    assert (
        hass.states.get("sensor.arcam_fmj_127_0_0_1_incoming_audio_format").state
        == "pcm"
    )
    assert (
        hass.states.get("sensor.arcam_fmj_127_0_0_1_incoming_audio_configuration").state
        == "stereo_only"
    )
    assert (
        hass.states.get("sensor.arcam_fmj_127_0_0_1_incoming_audio_sample_rate").state
        == "48000"
    )


@pytest.mark.usefixtures("player_setup")
async def test_sensor_enum_unknown(
    hass: HomeAssistant,
    state_1: State,
    client: Mock,
) -> None:
    """Test parameter sensors with unknown data."""
    video_params = Mock()
    video_params.horizontal_resolution = 0
    video_params.vertical_resolution = 0
    video_params.refresh_rate = 0
    video_params.aspect_ratio = IncomingVideoAspectRatio.from_int(0x99)
    video_params.colorspace = IncomingVideoColorspace.from_int(0x99)

    state_1.get_incoming_video_parameters.return_value = video_params
    state_1.get_incoming_audio_format.return_value = (
        None,
        IncomingAudioConfig.from_int(0x99),
    )

    client.notify_data_updated()
    await hass.async_block_till_done()

    def _get(key: str) -> str:
        state = hass.states.get(f"sensor.arcam_fmj_127_0_0_1_{key}")
        assert state
        return state.state

    assert _get("incoming_audio_format") == "unknown"
    assert _get("incoming_audio_configuration") == "unknown"
    assert _get("incoming_video_aspect_ratio") == "unknown"
    assert _get("incoming_video_colorspace") == "unknown"


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "player_setup")
async def test_software_version(
    hass: HomeAssistant,
    state_1: State,
    client: Mock,
) -> None:
    """Software version sensor reflects the library value."""
    state_1.get_software_version.return_value = "1.23"
    client.notify_data_updated()
    await hass.async_block_till_done()

    state = hass.states.get("sensor.arcam_fmj_127_0_0_1_software_version")
    assert state is not None
    assert state.state == "1.23"


@pytest.mark.parametrize("model", ["SA30"], indirect=True)
@pytest.mark.parametrize(
    ("key", "method", "value"),
    [
        ("lifter_temperature", "get_lifter_temperature", 42),
        ("output_temperature", "get_output_temperature", 55),
        ("dc_offset", "get_dc_offset", 12),
        ("short_circuit_status", "get_short_circuit_status", 0),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "player_setup")
async def test_amp_diagnostics(
    hass: HomeAssistant,
    state_1: State,
    client: Mock,
    key: str,
    method: str,
    value: int,
) -> None:
    """Amp-diagnostic sensors appear on Class-G models and read live values."""
    getattr(state_1, method).return_value = value
    client.notify_data_updated()
    await hass.async_block_till_done()

    state = hass.states.get(f"sensor.arcam_fmj_127_0_0_1_{key}")
    assert state is not None
    assert state.state == str(value)


@pytest.mark.parametrize("model", ["AVR550"], indirect=True)
@pytest.mark.usefixtures("player_setup")
async def test_amp_diagnostics_not_on_avr(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Amp diagnostics don't show up on plain AVR models."""
    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    keys = {entry.unique_id.rsplit("-", 1)[-1] for entry in entries}
    assert "lifter_temperature" not in keys
    assert "output_temperature" not in keys
    assert "dc_offset" not in keys
    assert "short_circuit_status" not in keys
    # Software version is universal — it does show up.
    assert "software_version" in keys
