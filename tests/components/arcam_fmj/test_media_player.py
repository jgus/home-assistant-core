"""Tests for arcam fmj receivers."""

from collections.abc import Generator
from math import isclose
from unittest.mock import Mock, PropertyMock, patch

from arcam.fmj import (
    BluetoothAudioStatus,
    CommandInvalidAtThisTime,
    ConnectionFailed,
    DecodeMode2CH,
    DecodeModeMCH,
    NetworkPlaybackStatus,
    NowPlayingEncoder,
    NowPlayingInfo,
    RC5CodePlayback,
    SourceCodes,
)
from arcam.fmj.state import State
import pytest
from syrupy.assertion import SnapshotAssertion
import voluptuous as vol

from homeassistant.components.arcam_fmj.media_player import ArcamFmj
from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE,
    ATTR_MEDIA_ALBUM_NAME,
    ATTR_MEDIA_ARTIST,
    ATTR_MEDIA_CHANNEL,
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    ATTR_SOUND_MODE,
    ATTR_SOUND_MODE_LIST,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_PREVIOUS_TRACK,
    SERVICE_MEDIA_STOP,
    SERVICE_PLAY_MEDIA,
    SERVICE_SELECT_SOUND_MODE,
    SERVICE_SELECT_SOURCE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_DOWN,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    SERVICE_VOLUME_UP,
    MediaPlayerState,
    MediaType,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, State as CoreState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .conftest import MOCK_ENTITY_ID

from tests.common import MockConfigEntry, snapshot_platform


@pytest.fixture(autouse=True)
def platform_fixture() -> Generator[None]:
    """Only test single platform."""
    with patch("homeassistant.components.arcam_fmj.PLATFORMS", [Platform.MEDIA_PLAYER]):
        yield


@pytest.mark.usefixtures("player_setup")
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_setup(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setup creates expected entities."""
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def update(hass: HomeAssistant, client: Mock, entity_id: str) -> CoreState:
    """Force a update of player and return current state data."""
    client.notify_data_updated()
    await hass.async_block_till_done()
    data = hass.states.get(entity_id)
    assert data
    return data


@pytest.mark.usefixtures("player_setup")
async def test_powered_off(hass: HomeAssistant, client: Mock, state_1: State) -> None:
    """Test properties in powered off state."""
    state_1.get_source.return_value = None
    state_1.get_power.return_value = False

    data = await update(hass, client, MOCK_ENTITY_ID)
    assert "source" not in data.attributes
    assert data.state == "off"


@pytest.mark.usefixtures("player_setup")
async def test_power_unknown(hass: HomeAssistant, client: Mock, state_1: State) -> None:
    """Test that an unreported power state surfaces as unknown, not off."""
    state_1.get_source.return_value = None
    state_1.get_power.return_value = None

    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.state == "unknown"


@pytest.mark.usefixtures("player_setup")
async def test_powered_on(hass: HomeAssistant, client: Mock, state_1: State) -> None:
    """Test properties in powered on state."""
    state_1.get_source.return_value = SourceCodes.PVR
    state_1.get_power.return_value = True

    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes["source"] == "PVR"
    assert data.state == "on"


@pytest.mark.usefixtures("player_setup")
async def test_turn_on(hass: HomeAssistant, state_1: State) -> None:
    """Test turn on service."""
    state_1.get_power.return_value = None
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_TURN_ON,
        service_data={ATTR_ENTITY_ID: MOCK_ENTITY_ID},
        blocking=True,
    )
    state_1.set_power.assert_not_called()

    state_1.get_power.return_value = False
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_TURN_ON,
        service_data={ATTR_ENTITY_ID: MOCK_ENTITY_ID},
        blocking=True,
    )
    state_1.set_power.assert_called_with(True)


@pytest.mark.usefixtures("player_setup")
async def test_turn_off(hass: HomeAssistant, state_1: State) -> None:
    """Test command to turn off."""
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_TURN_OFF,
        service_data={ATTR_ENTITY_ID: MOCK_ENTITY_ID},
        blocking=True,
    )
    state_1.set_power.assert_called_with(False)


@pytest.mark.parametrize("mute", [True, False])
@pytest.mark.usefixtures("player_setup")
async def test_mute_volume(hass: HomeAssistant, state_1: State, mute: bool) -> None:
    """Test mute functionality."""
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_VOLUME_MUTE,
        service_data={ATTR_ENTITY_ID: MOCK_ENTITY_ID, ATTR_MEDIA_VOLUME_MUTED: mute},
        blocking=True,
    )
    state_1.set_mute.assert_called_with(mute)


@pytest.mark.parametrize(
    ("source", "value"),
    [("PVR", SourceCodes.PVR), ("BD", SourceCodes.BD)],
)
@pytest.mark.usefixtures("player_setup")
async def test_select_valid_source(
    hass: HomeAssistant,
    state_1: State,
    source: str,
    value: SourceCodes,
) -> None:
    """Test selection of source."""
    await hass.services.async_call(
        "media_player",
        SERVICE_SELECT_SOURCE,
        service_data={ATTR_ENTITY_ID: MOCK_ENTITY_ID, ATTR_INPUT_SOURCE: source},
        blocking=True,
    )

    state_1.set_source.assert_called_with(value)


@pytest.mark.usefixtures("player_setup")
async def test_select_invalid_source(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """Test selection of source."""
    with pytest.raises(
        ServiceValidationError,
        check=lambda e: (
            e.translation_domain == "arcam_fmj"
            and e.translation_key == "unsupported_source"
        ),
    ):
        await hass.services.async_call(
            "media_player",
            SERVICE_SELECT_SOURCE,
            service_data={ATTR_ENTITY_ID: MOCK_ENTITY_ID, ATTR_INPUT_SOURCE: "INVALID"},
            blocking=True,
        )
    state_1.set_source.assert_not_called()


@pytest.mark.usefixtures("player_setup")
async def test_source_list(hass: HomeAssistant, client: Mock, state_1: State) -> None:
    """Test source list."""
    state_1.get_source_list.return_value = [SourceCodes.BD]
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes["source_list"] == ["BD"]


@pytest.mark.parametrize(
    "mode",
    [
        "STEREO",
        "DOLBY_PL",
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_select_sound_mode(
    hass: HomeAssistant, state_1: State, mode: str
) -> None:
    """Test selection sound mode."""
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_SELECT_SOUND_MODE,
        service_data={ATTR_ENTITY_ID: MOCK_ENTITY_ID, ATTR_SOUND_MODE: mode},
        blocking=True,
    )
    state_1.set_decode_mode.assert_called_with(mode)


@pytest.mark.usefixtures("player_setup")
async def test_select_invalid_sound_mode(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """Test selection of source."""
    state_1.set_decode_mode.side_effect = KeyError()
    with pytest.raises(
        ServiceValidationError,
        check=lambda e: (
            e.translation_domain == "arcam_fmj"
            and e.translation_key == "unsupported_sound_mode"
        ),
    ):
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_SELECT_SOUND_MODE,
            service_data={ATTR_ENTITY_ID: MOCK_ENTITY_ID, ATTR_SOUND_MODE: "INVALID"},
            blocking=True,
        )


@pytest.mark.usefixtures("player_setup")
async def test_volume_up(hass: HomeAssistant, state_1: State) -> None:
    """Test mute functionality."""
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_VOLUME_UP,
        service_data={ATTR_ENTITY_ID: MOCK_ENTITY_ID},
        blocking=True,
    )
    state_1.inc_volume.assert_called_with()


@pytest.mark.usefixtures("player_setup")
async def test_volume_down(hass: HomeAssistant, state_1: State) -> None:
    """Test mute functionality."""
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_VOLUME_DOWN,
        service_data={ATTR_ENTITY_ID: MOCK_ENTITY_ID},
        blocking=True,
    )
    state_1.dec_volume.assert_called_with()


@pytest.mark.usefixtures("player_setup")
async def test_play_media(hass: HomeAssistant, state_1: State) -> None:
    """Test mute functionality."""
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_PLAY_MEDIA,
        service_data={
            ATTR_ENTITY_ID: MOCK_ENTITY_ID,
            ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
            ATTR_MEDIA_CONTENT_ID: "preset:1",
        },
        blocking=True,
    )
    state_1.set_tuner_preset.assert_called_with(1)


@pytest.mark.usefixtures("player_setup")
async def test_play_media_invalid(hass: HomeAssistant, state_1: State) -> None:
    """Test mute functionality."""
    with pytest.raises(
        ServiceValidationError,
        check=lambda e: (
            e.translation_domain == "arcam_fmj"
            and e.translation_key == "unsupported_media"
        ),
    ):
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_PLAY_MEDIA,
            service_data={
                ATTR_ENTITY_ID: MOCK_ENTITY_ID,
                ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
                ATTR_MEDIA_CONTENT_ID: "invalid",
            },
            blocking=True,
        )
    state_1.set_tuner_preset.assert_not_called()


@pytest.mark.parametrize("media_id", ["preset:abc", "preset:"])
@pytest.mark.usefixtures("player_setup")
async def test_play_media_invalid_preset(
    hass: HomeAssistant,
    state_1: State,
    media_id: str,
) -> None:
    """Malformed preset payloads surface as a validation error, not a crash."""
    with pytest.raises(
        ServiceValidationError,
        check=lambda e: (
            e.translation_domain == "arcam_fmj"
            and e.translation_key == "invalid_preset"
        ),
    ):
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_PLAY_MEDIA,
            service_data={
                ATTR_ENTITY_ID: MOCK_ENTITY_ID,
                ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
                ATTR_MEDIA_CONTENT_ID: media_id,
            },
            blocking=True,
        )
    state_1.set_tuner_preset.assert_not_called()


@pytest.mark.parametrize(
    ("mode", "mode_enum"),
    [
        ("STEREO", DecodeMode2CH.STEREO),
        ("STEREO_DOWNMIX", DecodeModeMCH.STEREO_DOWNMIX),
        (None, None),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_sound_mode(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
    mode: str | None,
    mode_enum: DecodeMode2CH | DecodeModeMCH | None,
) -> None:
    """Test selection sound mode."""
    state_1.get_decode_mode.return_value = mode_enum
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes.get(ATTR_SOUND_MODE) == mode


@pytest.mark.parametrize(
    ("modes", "modes_enum"),
    [
        (["STEREO", "DOLBY_PL"], [DecodeMode2CH.STEREO, DecodeMode2CH.DOLBY_PL]),
        (["STEREO_DOWNMIX"], [DecodeModeMCH.STEREO_DOWNMIX]),
        (None, None),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_sound_mode_list(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
    modes: list[str] | None,
    modes_enum: list[DecodeMode2CH] | list[DecodeModeMCH] | None,
) -> None:
    """Test sound mode list."""
    state_1.get_decode_modes.return_value = modes_enum
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes.get(ATTR_SOUND_MODE_LIST) == modes


@pytest.mark.usefixtures("player_setup")
async def test_is_volume_muted(
    hass: HomeAssistant, client: Mock, state_1: State
) -> None:
    """Test muted."""
    state_1.get_mute.return_value = True
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes.get(ATTR_MEDIA_VOLUME_MUTED) is True

    state_1.get_mute.return_value = False
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes.get(ATTR_MEDIA_VOLUME_MUTED) is False

    state_1.get_mute.return_value = None
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes.get(ATTR_MEDIA_VOLUME_MUTED) is None


@pytest.mark.usefixtures("player_setup")
async def test_volume_level(hass: HomeAssistant, client: Mock, state_1: State) -> None:
    """Test volume."""
    state_1.get_volume.return_value = 0
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert isclose(data.attributes[ATTR_MEDIA_VOLUME_LEVEL], 0.0)

    state_1.get_volume.return_value = 50
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert isclose(data.attributes[ATTR_MEDIA_VOLUME_LEVEL], 50.0 / 99)

    state_1.get_volume.return_value = 99
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert isclose(data.attributes[ATTR_MEDIA_VOLUME_LEVEL], 1.0)

    state_1.get_volume.return_value = None
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert ATTR_MEDIA_VOLUME_LEVEL not in data.attributes


@pytest.mark.parametrize(("volume", "call"), [(0.0, 0), (0.5, 50), (1.0, 99)])
@pytest.mark.usefixtures("player_setup")
async def test_set_volume_level(
    hass: HomeAssistant, state_1: State, volume: float, call: int
) -> None:
    """Test setting volume."""
    await hass.services.async_call(
        "media_player",
        SERVICE_VOLUME_SET,
        service_data={ATTR_ENTITY_ID: MOCK_ENTITY_ID, ATTR_MEDIA_VOLUME_LEVEL: volume},
        blocking=True,
    )

    state_1.set_volume.assert_called_with(call)


@pytest.mark.usefixtures("player_setup")
async def test_set_volume_level_lost(hass: HomeAssistant, state_1: State) -> None:
    """Test setting volume, with a lost connection."""

    state_1.set_volume.side_effect = ConnectionFailed()

    with pytest.raises(
        HomeAssistantError,
        check=lambda e: (
            e.translation_domain == "arcam_fmj"
            and e.translation_key == "connection_failed"
        ),
    ):
        await hass.services.async_call(
            "media_player",
            SERVICE_VOLUME_SET,
            service_data={ATTR_ENTITY_ID: MOCK_ENTITY_ID, ATTR_MEDIA_VOLUME_LEVEL: 0.0},
            blocking=True,
        )


@pytest.mark.parametrize(
    ("source", "media_content_type"),
    [
        (SourceCodes.DAB, MediaType.MUSIC),
        (SourceCodes.FM, MediaType.MUSIC),
        (SourceCodes.NET, MediaType.MUSIC),
        (SourceCodes.USB, MediaType.MUSIC),
        (SourceCodes.BT, MediaType.MUSIC),
        (SourceCodes.PVR, None),
        (None, None),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_media_content_type(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
    source: SourceCodes | None,
    media_content_type: MediaType | None,
) -> None:
    """Test content type deduction."""
    state_1.get_source.return_value = source
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes.get(ATTR_MEDIA_CONTENT_TYPE) == media_content_type


@pytest.mark.parametrize(
    ("source", "dab", "rds", "channel"),
    [
        (SourceCodes.DAB, "dab", "rds", "dab"),
        (SourceCodes.DAB, None, None, None),
        (SourceCodes.FM, "dab", "rds", "rds"),
        (SourceCodes.FM, None, None, None),
        (SourceCodes.PVR, "dab", "rds", None),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_media_channel(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
    source: SourceCodes,
    dab: str | None,
    rds: str | None,
    channel: str | None,
) -> None:
    """Test media channel."""
    state_1.get_dab_station.return_value = dab
    state_1.get_rds_information.return_value = rds
    state_1.get_source.return_value = source
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes.get(ATTR_MEDIA_CHANNEL) == channel


@pytest.mark.parametrize(
    ("source", "dls", "artist"),
    [
        (SourceCodes.DAB, "dls", "dls"),
        (SourceCodes.FM, "dls", None),
        (SourceCodes.DAB, None, None),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_media_artist(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
    source: SourceCodes,
    dls: str | None,
    artist: str | None,
) -> None:
    """Test media artist."""
    state_1.get_dls_pdt.return_value = dls
    state_1.get_source.return_value = source
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes.get(ATTR_MEDIA_ARTIST) == artist


@pytest.mark.parametrize(
    ("source", "channel", "title"),
    [
        (SourceCodes.DAB, "channel", "DAB - channel"),
        (SourceCodes.DAB, None, "DAB"),
        (None, None, None),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_media_title(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
    source: SourceCodes | None,
    channel: str | None,
    title: str | None,
) -> None:
    """Test media title."""
    state_1.get_source.return_value = source
    with patch.object(
        ArcamFmj, "media_channel", new_callable=PropertyMock
    ) as media_channel:
        media_channel.return_value = channel
        data = await update(hass, client, MOCK_ENTITY_ID)
        assert data.attributes.get("media_title") == title


@pytest.mark.parametrize(
    ("source", "network_status", "expected"),
    [
        (SourceCodes.NET, NetworkPlaybackStatus.PLAYING, MediaPlayerState.PLAYING),
        (SourceCodes.NET, NetworkPlaybackStatus.PAUSED, MediaPlayerState.PAUSED),
        (SourceCodes.NET, NetworkPlaybackStatus.STOPPED, MediaPlayerState.IDLE),
        (
            SourceCodes.NET,
            NetworkPlaybackStatus.TRANSITIONING,
            MediaPlayerState.BUFFERING,
        ),
        (SourceCodes.USB, NetworkPlaybackStatus.PLAYING, MediaPlayerState.PLAYING),
        (SourceCodes.NET, None, MediaPlayerState.ON),
        (SourceCodes.BD, NetworkPlaybackStatus.PLAYING, MediaPlayerState.ON),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_state_for_network_playback(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
    source: SourceCodes,
    network_status: NetworkPlaybackStatus | None,
    expected: MediaPlayerState,
) -> None:
    """Network playback status drives state for NET/USB sources only."""
    state_1.get_source.return_value = source
    state_1.get_network_playback_status.return_value = network_status
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.state == expected


@pytest.mark.parametrize(
    ("bt_status", "expected"),
    [
        (BluetoothAudioStatus.PLAYING_SBC, MediaPlayerState.PLAYING),
        (BluetoothAudioStatus.PLAYING_APTX_HD, MediaPlayerState.PLAYING),
        (BluetoothAudioStatus.PAUSED, MediaPlayerState.PAUSED),
        (BluetoothAudioStatus.NO_CONNECTION, MediaPlayerState.ON),
        (None, MediaPlayerState.ON),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_state_for_bluetooth(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
    bt_status: BluetoothAudioStatus | None,
    expected: MediaPlayerState,
) -> None:
    """Bluetooth audio status drives state for the BT source."""
    state_1.get_source.return_value = SourceCodes.BT
    state_1.get_bluetooth_status.return_value = (bt_status, "")
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.state == expected


@pytest.mark.parametrize(
    ("service", "code"),
    [
        (SERVICE_MEDIA_PLAY, RC5CodePlayback.PLAY),
        (SERVICE_MEDIA_PAUSE, RC5CodePlayback.PAUSE),
        (SERVICE_MEDIA_STOP, RC5CodePlayback.STOP),
        (SERVICE_MEDIA_NEXT_TRACK, RC5CodePlayback.SKIP_FORWARD),
        (SERVICE_MEDIA_PREVIOUS_TRACK, RC5CodePlayback.SKIP_BACK),
    ],
)
@pytest.mark.usefixtures("player_setup")
async def test_playback_controls(
    hass: HomeAssistant,
    state_1: State,
    service: str,
    code: RC5CodePlayback,
) -> None:
    """Each playback service forwards the matching RC5 playback code."""
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        service,
        {ATTR_ENTITY_ID: MOCK_ENTITY_ID},
        blocking=True,
    )
    state_1.send_playback.assert_called_once_with(code)


@pytest.mark.usefixtures("player_setup")
async def test_playback_unsupported_on_model(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """Library ValueError on send_playback surfaces as HomeAssistantError."""
    state_1.send_playback.side_effect = ValueError("not supported")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_MEDIA_PLAY,
            {ATTR_ENTITY_ID: MOCK_ENTITY_ID},
            blocking=True,
        )


@pytest.mark.usefixtures("player_setup")
async def test_playback_connection_failed(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """ConnectionFailed on send_playback surfaces as HomeAssistantError."""
    state_1.send_playback.side_effect = ConnectionFailed()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_MEDIA_PLAY,
            {ATTR_ENTITY_ID: MOCK_ENTITY_ID},
            blocking=True,
        )


@pytest.mark.usefixtures("player_setup")
async def test_now_playing_metadata(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
) -> None:
    """NowPlayingInfo populates title/artist/album/app_name for network sources."""
    state_1.get_source.return_value = SourceCodes.NET
    state_1.get_now_playing.return_value = NowPlayingInfo(
        track="Song",
        artist="Artist",
        album="Album",
        application="Spotify",
        sample_rate=48000,
        encoder=NowPlayingEncoder.FLAC,
    )
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes.get("media_title") == "Song"
    assert data.attributes.get(ATTR_MEDIA_ARTIST) == "Artist"
    assert data.attributes.get(ATTR_MEDIA_ALBUM_NAME) == "Album"
    assert data.attributes.get("app_name") == "Spotify"
    assert data.attributes.get("media_sample_rate") == 48000
    assert data.attributes.get("media_encoder") == "FLAC"


@pytest.mark.usefixtures("player_setup")
async def test_bluetooth_track_as_title(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
) -> None:
    """When there's no NowPlayingInfo, BT AVRCP track text becomes the title."""
    state_1.get_source.return_value = SourceCodes.BT
    state_1.get_bluetooth_status.return_value = (
        BluetoothAudioStatus.PLAYING_APTX_HD,
        "From my phone",
    )
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes.get("media_title") == "From my phone"
    assert data.attributes.get("bluetooth_codec") == "aptX HD"


@pytest.mark.usefixtures("player_setup")
async def test_select_source_unsupported_raises(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """Selecting a source not in the model's source list raises validation error."""
    state_1.get_source_list.return_value = [SourceCodes.CD]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_SELECT_SOURCE,
            {ATTR_ENTITY_ID: MOCK_ENTITY_ID, ATTR_INPUT_SOURCE: "BD"},
            blocking=True,
        )
    state_1.set_source.assert_not_called()


@pytest.mark.usefixtures("player_setup")
async def test_fm_genre_in_attributes(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
) -> None:
    """FM genre shows up as a media_genre attribute when the source is FM."""
    state_1.get_source.return_value = SourceCodes.FM
    state_1.get_fm_genre.return_value = "Classic Rock"
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert data.attributes.get("media_genre") == "Classic Rock"


@pytest.mark.usefixtures("player_setup")
async def test_fm_genre_only_for_fm(
    hass: HomeAssistant,
    client: Mock,
    state_1: State,
) -> None:
    """FM genre doesn't leak into other source's attributes."""
    state_1.get_source.return_value = SourceCodes.BD
    state_1.get_fm_genre.return_value = "Classic Rock"
    data = await update(hass, client, MOCK_ENTITY_ID)
    assert "media_genre" not in data.attributes


@pytest.mark.usefixtures("player_setup")
async def test_save_settings_default_pin(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """save_settings without a PIN uses the library default."""
    await hass.services.async_call(
        "arcam_fmj",
        "save_settings",
        {ATTR_ENTITY_ID: MOCK_ENTITY_ID},
        blocking=True,
    )
    state_1.save_settings.assert_called_once_with()


@pytest.mark.usefixtures("player_setup")
async def test_save_settings_explicit_pin(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """save_settings passes a 4-digit PIN through as a tuple of ints."""
    await hass.services.async_call(
        "arcam_fmj",
        "save_settings",
        {ATTR_ENTITY_ID: MOCK_ENTITY_ID, "pin": "5678"},
        blocking=True,
    )
    state_1.save_settings.assert_called_once_with((5, 6, 7, 8))


@pytest.mark.usefixtures("player_setup")
async def test_restore_settings_default_pin(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """restore_settings without a PIN uses the library default."""
    await hass.services.async_call(
        "arcam_fmj",
        "restore_settings",
        {ATTR_ENTITY_ID: MOCK_ENTITY_ID},
        blocking=True,
    )
    state_1.restore_settings.assert_called_once_with()


@pytest.mark.usefixtures("player_setup")
async def test_restore_settings_no_backup(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """CommandInvalidAtThisTime surfaces as HomeAssistantError on restore."""
    state_1.restore_settings.side_effect = CommandInvalidAtThisTime()
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "arcam_fmj",
            "restore_settings",
            {ATTR_ENTITY_ID: MOCK_ENTITY_ID},
            blocking=True,
        )


@pytest.mark.usefixtures("player_setup")
async def test_save_settings_invalid_pin(
    hass: HomeAssistant,
    state_1: State,
) -> None:
    """A non-4-digit PIN fails schema validation before reaching the library."""
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            "arcam_fmj",
            "save_settings",
            {ATTR_ENTITY_ID: MOCK_ENTITY_ID, "pin": "abc"},
            blocking=True,
        )
    state_1.save_settings.assert_not_called()


@pytest.mark.parametrize(
    ("service", "method"),
    [("fm_scan", "fm_scan"), ("dab_scan", "dab_scan")],
)
@pytest.mark.usefixtures("player_setup")
async def test_tuner_scans(
    hass: HomeAssistant,
    state_1: State,
    service: str,
    method: str,
) -> None:
    """fm_scan / dab_scan actions trigger the matching library send."""
    await hass.services.async_call(
        "arcam_fmj",
        service,
        {ATTR_ENTITY_ID: MOCK_ENTITY_ID},
        blocking=True,
    )
    getattr(state_1, method).assert_called_once_with()
