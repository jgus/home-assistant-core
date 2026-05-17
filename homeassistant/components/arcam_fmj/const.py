"""Constants used for arcam."""

DOMAIN = "arcam_fmj"

EVENT_TURN_ON = "arcam_fmj.turn_on"

DEFAULT_PORT = 50000
DEFAULT_NAME = "Arcam FMJ"
DEFAULT_SCAN_INTERVAL = 5

# Outer timeout for the initial setup handshake (TCP connect + AMX Duet
# request/response, with internal retries) before retrying via
# ConfigEntryNotReady.
SETUP_TIMEOUT = 10

SERVICE_SAVE_SETTINGS = "save_settings"
SERVICE_RESTORE_SETTINGS = "restore_settings"
SERVICE_FM_SCAN = "fm_scan"
SERVICE_DAB_SCAN = "dab_scan"
ATTR_PIN = "pin"
