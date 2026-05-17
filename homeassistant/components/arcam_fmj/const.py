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
