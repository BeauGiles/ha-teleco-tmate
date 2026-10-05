# Changelog

## 0.1.0

First release.

- Cover entity (awning) for the Teleco T-Mate Bluetooth box: open, stop, close.
- Time-based position estimate with a settable position; configurable open/close travel times.
- "Set as fully open" / "Set as fully closed" buttons to resync the estimate without moving the motor.
- Entity shows unavailable when no connectable Bluetooth adapter or proxy can reach the box.
- One automatic retry on a failed command; last-command attributes for troubleshooting.
- Position is restored across Home Assistant restarts.
