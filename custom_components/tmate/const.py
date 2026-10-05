"""Constants for the Teleco T-Mate integration."""

DOMAIN = "tmate"

CONF_RC = "rc"
DEFAULT_RC = 1

SERVICE_UUID = "0000cbba-0000-1000-8000-00805f9b34fb"
TX_CHAR = "0000cbb0-0000-1000-8000-00805f9b34fb"
SETTING_CHAR = "00005f9b-0000-1000-8000-00805f9b34fb"

CHANNEL_OPEN = 5
CHANNEL_STOP = 6
CHANNEL_CLOSE = 7

# The app holds the on-screen key down; a short hold is enough for the box.
HOLD_SECONDS = 0.8
KEEPALIVE_SECONDS = 0.35  # the app re-sends the press this often while held
RETRY_DELAY = 1.5

CONF_OPEN_TIME = "open_time"
CONF_CLOSE_TIME = "close_time"
DEFAULT_TRAVEL_SECONDS = 18
# Send "stop" this long before the estimated arrival, to cover connect + press latency.
STOP_LEAD_SECONDS = 1.5
