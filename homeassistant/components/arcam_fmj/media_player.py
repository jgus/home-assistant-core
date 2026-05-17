"""Arcam media player."""

import logging
from typing import Any

from arcam.fmj import (
    BluetoothAudioStatus,
    CommandInvalidAtThisTime,
    NetworkPlaybackStatus,
    NowPlayingEncoder,
    RC5CodePlayback,
    SourceCodes,
)

from homeassistant.components.media_player import (
    BrowseError,
    BrowseMedia,
    MediaClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, EVENT_TURN_ON
from .coordinator import ArcamFmjConfigEntry, ArcamFmjCoordinator
from .entity import ArcamFmjEntity, convert_exception, unsupported_command_error

_LOGGER = logging.getLogger(__name__)

# arcam-fmj serializes commands on a single TCP writer at the library
# layer; serialize at HA's layer to match the device's contract.
PARALLEL_UPDATES = 1

TUNER_SOURCES = {SourceCodes.DAB, SourceCodes.FM}
NETWORK_SOURCES = {SourceCodes.NET, SourceCodes.USB, SourceCodes.NET_USB}
BLUETOOTH_SOURCES = {SourceCodes.BT}
PLAYBACK_SOURCES = NETWORK_SOURCES | BLUETOOTH_SOURCES
AUDIO_SOURCES = TUNER_SOURCES | PLAYBACK_SOURCES

NETWORK_PLAYBACK_STATE: dict[NetworkPlaybackStatus, MediaPlayerState] = {
    NetworkPlaybackStatus.STOPPED: MediaPlayerState.IDLE,
    NetworkPlaybackStatus.TRANSITIONING: MediaPlayerState.BUFFERING,
    NetworkPlaybackStatus.PLAYING: MediaPlayerState.PLAYING,
    NetworkPlaybackStatus.PAUSED: MediaPlayerState.PAUSED,
}

BLUETOOTH_CODEC: dict[BluetoothAudioStatus, str] = {
    BluetoothAudioStatus.PLAYING_SBC: "SBC",
    BluetoothAudioStatus.PLAYING_AAC: "AAC",
    BluetoothAudioStatus.PLAYING_APTX: "aptX",
    BluetoothAudioStatus.PLAYING_APTX_HD: "aptX HD",
}


def _bluetooth_state(status: BluetoothAudioStatus | None) -> MediaPlayerState | None:
    """Map a Bluetooth status to a media player state, if meaningful."""
    if status == BluetoothAudioStatus.PAUSED:
        return MediaPlayerState.PAUSED
    if status in BLUETOOTH_CODEC:
        return MediaPlayerState.PLAYING
    return None


def _parse_pin(pin: str) -> tuple[int, int, int, int]:
    """Convert a 4-digit string into the library's PIN tuple."""
    return (int(pin[0]), int(pin[1]), int(pin[2]), int(pin[3]))


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ArcamFmjConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the configuration entry."""
    async_add_entities(
        ArcamFmj(coordinator)
        for coordinator in config_entry.runtime_data.coordinators.values()
    )


class ArcamFmj(ArcamFmjEntity, MediaPlayerEntity):
    """Representation of a media device."""

    def __init__(self, coordinator: ArcamFmjCoordinator) -> None:
        """Initialize device."""
        super().__init__(coordinator)
        self._state = coordinator.state
        self._attr_supported_features = (
            MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.BROWSE_MEDIA
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.TURN_ON
        )
        if self._state.zn == 1:
            self._attr_supported_features |= (
                MediaPlayerEntityFeature.SELECT_SOUND_MODE
                | MediaPlayerEntityFeature.PLAY
                | MediaPlayerEntityFeature.PAUSE
                | MediaPlayerEntityFeature.STOP
                | MediaPlayerEntityFeature.NEXT_TRACK
                | MediaPlayerEntityFeature.PREVIOUS_TRACK
            )

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the state of the device.

        ``None`` is returned (surfaced as ``unknown``) when the device has
        not yet reported a power state; this is distinct from a real
        powered-off state and must not be collapsed to ``OFF``.
        """
        power = self._state.get_power()
        if power is None:
            return None
        if not power:
            return MediaPlayerState.OFF

        source = self._state.get_source()
        if (
            source in NETWORK_SOURCES
            and (status := self._state.get_network_playback_status()) is not None
        ):
            return NETWORK_PLAYBACK_STATE.get(status, MediaPlayerState.ON)
        if source in BLUETOOTH_SOURCES:
            bt_status, _ = self._state.get_bluetooth_status()
            if (bt_state := _bluetooth_state(bt_status)) is not None:
                return bt_state

        return MediaPlayerState.ON

    @convert_exception
    async def async_mute_volume(self, mute: bool) -> None:
        """Send mute command."""
        await self._state.set_mute(mute)
        self.async_write_ha_state()

    @convert_exception
    async def async_select_source(self, source: str) -> None:
        """Select a specific source."""
        try:
            value = SourceCodes[source]
        except KeyError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_source",
                translation_placeholders={"source": source},
            ) from err
        if value not in self._state.get_source_list():
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_source",
                translation_placeholders={"source": source},
            )

        await self._state.set_source(value)
        self.async_write_ha_state()

    @convert_exception
    async def async_select_sound_mode(self, sound_mode: str) -> None:
        """Select a specific source."""
        try:
            await self._state.set_decode_mode(sound_mode)
        except (KeyError, ValueError) as exception:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_sound_mode",
                translation_placeholders={"sound_mode": sound_mode},
            ) from exception

        self.async_write_ha_state()

    @convert_exception
    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        await self._state.set_volume(round(volume * 99.0))
        self.async_write_ha_state()

    @convert_exception
    async def async_volume_up(self) -> None:
        """Turn volume up for media player."""
        await self._state.inc_volume()
        self.async_write_ha_state()

    @convert_exception
    async def async_volume_down(self) -> None:
        """Turn volume up for media player."""
        await self._state.dec_volume()
        self.async_write_ha_state()

    @convert_exception
    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        if self._state.get_power() is not None:
            _LOGGER.debug("Turning on device using connection")
            await self._state.set_power(True)
        else:
            _LOGGER.debug("Firing event to turn on device")
            self.hass.bus.async_fire(EVENT_TURN_ON, {ATTR_ENTITY_ID: self.entity_id})

    @convert_exception
    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        await self._state.set_power(False)

    @convert_exception
    async def async_media_play(self) -> None:
        """Send play command."""
        await self._send_playback(RC5CodePlayback.PLAY)

    @convert_exception
    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self._send_playback(RC5CodePlayback.PAUSE)

    @convert_exception
    async def async_media_stop(self) -> None:
        """Send stop command."""
        await self._send_playback(RC5CodePlayback.STOP)

    @convert_exception
    async def async_media_next_track(self) -> None:
        """Send skip-forward command."""
        await self._send_playback(RC5CodePlayback.SKIP_FORWARD)

    @convert_exception
    async def async_media_previous_track(self) -> None:
        """Send skip-back command."""
        await self._send_playback(RC5CodePlayback.SKIP_BACK)

    async def _send_playback(self, code: RC5CodePlayback) -> None:
        """Forward a playback RC5 code, translating model-support errors."""
        try:
            await self._state.send_playback(code)
        except ValueError as err:
            raise unsupported_command_error(code.name.lower()) from err

    @convert_exception
    async def async_save_settings(self, pin: str | None = None) -> None:
        """Save the device's current settings to its secure backup slot."""
        try:
            if pin is None:
                await self._state.save_settings()
            else:
                await self._state.save_settings(_parse_pin(pin))
        except CommandInvalidAtThisTime as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="save_settings_failed",
            ) from err

    @convert_exception
    async def async_restore_settings(self, pin: str | None = None) -> None:
        """Restore the device's settings from its secure backup slot."""
        try:
            if pin is None:
                await self._state.restore_settings()
            else:
                await self._state.restore_settings(_parse_pin(pin))
        except CommandInvalidAtThisTime as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="restore_settings_failed",
            ) from err

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Implement the websocket media browsing helper."""
        if media_content_id not in (None, "root"):
            raise BrowseError(
                f"Media not found: {media_content_type} / {media_content_id}"
            )

        presets = self._state.get_preset_details()

        radio = [
            BrowseMedia(
                title=preset.name,
                media_class=MediaClass.MUSIC,
                media_content_id=f"preset:{preset.index}",
                media_content_type=MediaType.MUSIC,
                can_play=True,
                can_expand=False,
            )
            for preset in presets.values()
        ]

        return BrowseMedia(
            title=self.coordinator.device_name,
            media_class=MediaClass.DIRECTORY,
            media_content_id="root",
            media_content_type="library",
            can_play=False,
            can_expand=True,
            children=radio,
        )

    @convert_exception
    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play media."""
        if not media_id.startswith("preset:"):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_media",
                translation_placeholders={"media": media_id},
            )

        try:
            preset = int(media_id.removeprefix("preset:"))
        except ValueError as exception:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_preset",
                translation_placeholders={"media": media_id},
            ) from exception

        await self._state.set_tuner_preset(preset)

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        if (value := self._state.get_source()) is None:
            return None
        return value.name

    @property
    def source_list(self) -> list[str]:
        """List of available input sources."""
        return [src.name for src in self._state.get_source_list()]

    @property
    def sound_mode(self) -> str | None:
        """Name of the current sound mode."""
        if (value := self._state.get_decode_mode()) is None:
            return None
        return value.name

    @property
    def sound_mode_list(self) -> list[str] | None:
        """List of available sound modes."""
        if (values := self._state.get_decode_modes()) is None:
            return None
        return [x.name for x in values]

    @property
    def is_volume_muted(self) -> bool | None:
        """Boolean if volume is currently muted."""
        if (value := self._state.get_mute()) is None:
            return None
        return value

    @property
    def volume_level(self) -> float | None:
        """Volume level of device."""
        if (value := self._state.get_volume()) is None:
            return None
        return value / 99.0

    @property
    def media_content_type(self) -> MediaType | None:
        """Content type of current playing media."""
        if self._state.get_source() in AUDIO_SOURCES:
            return MediaType.MUSIC
        return None

    @property
    def media_content_id(self) -> str | None:
        """Content type of current playing media."""
        if self._state.get_source() not in TUNER_SOURCES:
            return None
        if preset := self._state.get_tuner_preset():
            return f"preset:{preset}"
        return None

    @property
    def media_channel(self) -> str | None:
        """Channel currently playing."""
        source = self._state.get_source()
        if source == SourceCodes.DAB:
            return self._state.get_dab_station()
        if source == SourceCodes.FM:
            return self._state.get_rds_information()
        return None

    @property
    def media_artist(self) -> str | None:
        """Artist of current playing media, music track only."""
        source = self._state.get_source()
        if source == SourceCodes.DAB:
            return self._state.get_dls_pdt()
        if source in PLAYBACK_SOURCES and (np := self._state.get_now_playing()):
            return np.artist
        return None

    @property
    def media_title(self) -> str | None:
        """Title of current playing media."""
        if (source := self._state.get_source()) is None:
            return None

        if source in PLAYBACK_SOURCES:
            if (np := self._state.get_now_playing()) and np.track:
                return np.track
            if source in BLUETOOTH_SOURCES:
                _, bt_track = self._state.get_bluetooth_status()
                if bt_track:
                    return bt_track

        if channel := self.media_channel:
            return f"{source.name} - {channel}"
        return self.source

    @property
    def media_album_name(self) -> str | None:
        """Album of current playing media."""
        if self._state.get_source() in PLAYBACK_SOURCES and (
            np := self._state.get_now_playing()
        ):
            return np.album
        return None

    @property
    def app_name(self) -> str | None:
        """Name of the network/streaming app supplying the current media."""
        if self._state.get_source() in NETWORK_SOURCES and (
            np := self._state.get_now_playing()
        ):
            return np.application
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes (BT codec, encoder, sample rate, FM genre)."""
        source = self._state.get_source()
        attrs: dict[str, Any] = {}

        if source in PLAYBACK_SOURCES and (np := self._state.get_now_playing()):
            if np.sample_rate:
                attrs["media_sample_rate"] = np.sample_rate
            encoder = np.encoder
            if encoder is not None and encoder != NowPlayingEncoder.UNKNOWN:
                attrs["media_encoder"] = encoder.name

        if source in BLUETOOTH_SOURCES:
            bt_status, _ = self._state.get_bluetooth_status()
            if bt_status is not None and (codec := BLUETOOTH_CODEC.get(bt_status)):
                attrs["bluetooth_codec"] = codec

        if source == SourceCodes.FM and (genre := self._state.get_fm_genre()):
            attrs["media_genre"] = genre

        return attrs or None
