"""Diagnostics support for arcam_fmj."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import ArcamFmjConfigEntry

TO_REDACT_ENTRY_DATA = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ArcamFmjConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT_ENTRY_DATA),
            "version": entry.version,
            "minor_version": entry.minor_version,
            "unique_id_set": entry.unique_id is not None,
        },
        "client": {
            "connected": runtime_data.client.connected,
        },
        "zones": {
            zone: {
                "model": coordinator.state.model,
                "revision": coordinator.state.revision,
                "last_update_success": coordinator.last_update_success,
                "last_exception": (
                    str(coordinator.last_exception)
                    if coordinator.last_exception
                    else None
                ),
                "state": coordinator.state.to_dict(),
            }
            for zone, coordinator in runtime_data.coordinators.items()
        },
    }
