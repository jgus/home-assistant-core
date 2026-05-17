"""Tests for the arcam_fmj component."""

from asyncio import CancelledError, Queue
from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager
from unittest.mock import AsyncMock, Mock, patch

from arcam.fmj import AmxDuetResponse, SourceCodes
from arcam.fmj.client import Client, ResponsePacket
from arcam.fmj.state import State
import pytest

from homeassistant.components.arcam_fmj.const import DEFAULT_NAME
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

MOCK_HOST = "127.0.0.1"
MOCK_PORT = 50000
MOCK_TURN_ON = {
    "service": "switch.turn_on",
    "data": {"entity_id": "switch.test"},
}
MOCK_ENTITY_ID = "media_player.arcam_fmj_127_0_0_1"
MOCK_UUID = "456789abcdef"
MOCK_UDN = f"uuid:01234567-89ab-cdef-0123-{MOCK_UUID}"
MOCK_NAME = f"{DEFAULT_NAME} ({MOCK_HOST})"
MOCK_CONFIG_ENTRY = {CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT}
# AVR550 is in APIVERSION_860_SERIES → supports zone 2.
MOCK_MODEL = "AVR550"
MOCK_REVISION = "1.0"


@pytest.fixture(name="model")
def model_fixture(request: pytest.FixtureRequest) -> str | None:
    """Return the AMX Duet device_model used by the mocked client.

    Override per-test with @pytest.mark.parametrize("model", [...], indirect=True).
    """
    return getattr(request, "param", MOCK_MODEL)


@pytest.fixture(name="client")
def client_fixture(model: str | None) -> Generator[Mock]:
    """Get a mocked client."""
    client = Mock(Client)
    client.host = MOCK_HOST
    client.port = MOCK_PORT

    queue = Queue[BaseException | None]()
    listeners = set()

    amxduet = Mock(AmxDuetResponse)
    amxduet.device_model = model
    amxduet.device_revision = MOCK_REVISION

    async def _start():
        client.connected = True

    async def _process():
        result = await queue.get()
        client.connected = False
        if isinstance(result, BaseException):
            raise result

    async def _request_raw(request, priority=0):
        return amxduet

    @contextmanager
    def _listen(listener):
        listeners.add(listener)
        yield client
        listeners.remove(listener)

    @callback
    def _notify_data_updated(zn=1):
        packet = Mock(ResponsePacket)
        packet.zn = zn
        for listener in listeners:
            listener(packet)

    @callback
    def _notify_connection(exception: Exception | None = None):
        queue.put_nowait(exception)

    client.start.side_effect = _start
    client.process.side_effect = _process
    client.listen.side_effect = _listen
    client.request_raw.side_effect = _request_raw
    client.notify_data_updated = _notify_data_updated
    client.notify_connection = _notify_connection

    yield client

    queue.put_nowait(CancelledError())


def _build_state_mock(client: Mock, zone: int, model: str | None) -> Mock:
    """Build a mocked State for a given zone."""
    state = Mock(State)
    state.client = client
    state.zn = zone
    state.model = model
    state.revision = MOCK_REVISION
    state.get_power.return_value = True
    state.get_volume.return_value = 0.0
    state.get_source.return_value = None
    state.get_source_list.return_value = [
        SourceCodes.CD,
        SourceCodes.BD,
        SourceCodes.AV,
        SourceCodes.PVR,
        SourceCodes.FM,
        SourceCodes.DAB,
        SourceCodes.NET,
        SourceCodes.USB,
        SourceCodes.BT,
    ]
    state.get_incoming_audio_format.return_value = (None, None)
    state.get_incoming_video_parameters.return_value = None
    state.get_incoming_audio_sample_rate.return_value = 0
    state.get_mute.return_value = None
    state.get_decode_modes.return_value = []
    state.get_decode_mode.return_value = None
    state.get_network_playback_status.return_value = None
    state.get_now_playing.return_value = None
    state.get_bluetooth_status.return_value = (None, None)
    state.get_room_eq_names.return_value = None
    state.get_bass_equalization.return_value = None
    state.get_treble_equalization.return_value = None
    state.get_balance.return_value = None
    state.get_subwoofer_trim.return_value = None
    state.get_sub_stereo_trim.return_value = None
    state.get_lipsync_delay.return_value = None
    state.get_headphones.return_value = None
    state.get_software_version.return_value = None
    state.get_lifter_temperature.return_value = None
    state.get_output_temperature.return_value = None
    state.get_dc_offset.return_value = None
    state.get_short_circuit_status.return_value = None
    state.get_max_turn_on_volume.return_value = None
    state.get_max_volume.return_value = None
    state.get_max_streaming_volume.return_value = None
    state.get_dolby_pliix_dimension.return_value = None
    state.get_dolby_pliix_centre_width.return_value = None
    state.get_video_selection.return_value = None
    state.get_display_brightness.return_value = None
    state.get_direct_mode.return_value = None
    state.get_dolby_pliix_panorama.return_value = None
    state.to_dict.return_value = {
        "POWER": True,
        "VOLUME": 0.0,
        "SOURCE": None,
        "MUTE": None,
        "MENU": None,
        "INCOMING_VIDEO_PARAMETERS": None,
        "INCOMING_AUDIO_FORMAT": (None, None),
        "INCOMING_AUDIO_SAMPLE_RATE": 0,
        "DECODE_MODE_2CH": None,
        "DECODE_MODE_MCH": None,
        "DAB_STATION": None,
        "DLS_PDT": None,
        "RDS_INFORMATION": None,
        "TUNER_PRESET": None,
        "PRESET_DETAIL": None,
    }
    state.__aenter__ = AsyncMock()
    state.__aexit__ = AsyncMock()
    return state


@pytest.fixture(name="state_1")
def state_1_fixture(client: Mock, model: str | None) -> State:
    """Get a mocked state."""
    return _build_state_mock(client, 1, model)


@pytest.fixture(name="state_2")
def state_2_fixture(client: Mock, model: str | None) -> State:
    """Get a mocked state."""
    return _build_state_mock(client, 2, model)


@pytest.fixture(name="mock_config_entry")
def mock_config_entry_fixture(hass: HomeAssistant) -> MockConfigEntry:
    """Get a mock config entry."""
    config_entry = MockConfigEntry(
        domain="arcam_fmj",
        data=MOCK_CONFIG_ENTRY,
        title=MOCK_NAME,
        unique_id=MOCK_UUID,
    )
    config_entry.add_to_hass(hass)
    return config_entry


@pytest.fixture(name="player_setup")
async def player_setup_fixture(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    state_1: State,
    state_2: State,
    client: Mock,
) -> AsyncGenerator[None]:
    """Get standard player."""

    def state_mock(cli, zone):
        if zone == 1:
            return state_1
        if zone == 2:
            return state_2
        raise ValueError(f"Unknown player zone: {zone}")

    await async_setup_component(hass, "homeassistant", {})

    with (
        patch("homeassistant.components.arcam_fmj.Client", return_value=client),
        patch(
            "homeassistant.components.arcam_fmj.coordinator.State",
            side_effect=state_mock,
        ),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        yield
