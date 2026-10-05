# Teleco T-Mate for Home Assistant

An unofficial Home Assistant custom integration for the **Teleco Automation T-Mate**
Bluetooth box, which controls motorised awnings, roofs, shutters and gates from the
T-Mate phone app. This integration talks to the box directly over Bluetooth Low Energy
using Home Assistant's own Bluetooth stack, so you don't need the phone app.

Built and tested on a Stratco Allure Pavilion (louvre roof) controlled by a T-Mate box.

> **Unofficial.** Not affiliated with or endorsed by Teleco Automation. The protocol was
> worked out from the publicly distributed T-Mate Android app and from testing against a
> real box. Use at your own risk, and keep people and objects clear of anything that moves.

## T-Mate or Daisy?

Teleco makes two different boxes, and they need different integrations:

| | This integration | [hass_teleco_daisy](https://github.com/andreasnuesslein/hass_teleco_daisy) |
|---|---|---|
| Box | **T-Mate** (Bluetooth) | **Daisy** (Wi-Fi) |
| Connection | Direct Bluetooth, local, no cloud or account | Teleco's cloud, with your Teleco login |
| App | T-Mate | Daisy |

If you control your devices with the **T-Mate** app, use this one. If you use the
**Daisy** app, use the Daisy integration instead.

## Features

- **Cover entity** (device class: awning) with **open, close, stop** and a **position slider**.
- **Time-based position estimate.** The box does not report position, so Home Assistant
  estimates it from the travel time you configure.
- **"Set as fully open / fully closed" buttons** to correct the estimate after the remote
  or app has been used. They send nothing to the motor.
- **Unavailable** when no connectable Bluetooth adapter or proxy can hear the box.
- **One automatic retry** if a command fails.
- **Last-command attributes** (`last_command`, `last_command_at`, `last_command_ok`,
  `last_error`) for easy troubleshooting.
- Connects only while sending a command, then disconnects, so the phone app keeps working.
- Position is restored across restarts.

## Requirements

- Home Assistant with the **Bluetooth** integration, and a **connectable** adapter or
  proxy within range of the box. A USB adapter on the HA host or an
  [ESPHome Bluetooth proxy](https://esphome.github.io/bluetooth-proxies/) with active
  connections will work.
  **Shelly devices' Bluetooth scanners cannot connect** (listen-only), so they will not work.
- Close the T-Mate phone app while using Home Assistant: the box accepts one connection at a time.
- No pairing or PIN is needed. (The 4-digit code in the app is only used by the app to
  recognise your box; it is never sent to it.)

## Installation

### HACS (custom repository)
1. HACS → ⋮ → **Custom repositories** → add `https://github.com/BeauGiles/ha-teleco-tmate`
   as an **Integration**.
2. Install **Teleco T-Mate**, then restart Home Assistant.

### Manual
Copy `custom_components/tmate` into your Home Assistant `config/custom_components/`
folder and restart.

## Setup

1. Close the T-Mate app. The box should be auto-discovered
   (**Settings → Devices & services**). If not, **Add integration → Teleco T-Mate**.
2. Give it a name, and set the **receiver number**: the device index the T-Mate app assigns
   (usually `1`).
3. Open **Configure** on the integration and set the **open time** and **close time**: the
   seconds from when the roof *starts moving* to when it *stops*. Time it with the Home
   Assistant buttons. Default is 18 s each.
4. Fully open or close it once (or press one of the "Set as fully…" buttons) so Home
   Assistant knows where it is. Partial positions work after that.

## Limitations

- **No real position or state feedback.** Position is an estimate and drifts if the roof is
  moved by the remote, the app, or a built-in rain/wind sensor. Use the reset buttons or
  fully open/close to resync. (The T-Mate app only reports state for two-way "Blue Series"
  receivers in feedback mode; this integration does not enable that.)
- Partial positions rely on the stop command arriving at the right moment, so they are
  accurate to a few percent at best.
- Only the open / stop / close channels (5 / 6 / 7) are implemented. Other T-Mate device
  types (lights, fans, audio, etc.) are not.
- Firmware and hardware version are not available over Bluetooth.

## Protocol notes

- Service `0000cbba-0000-1000-8000-00805f9b34fb`; commands are 16-byte writes to
  characteristic `0000cbb0-…`.
- Press frame: `[01, rc, channel, time_hi, time_lo, 01, 00 …]`. The app resends it every
  350 ms while a button is held and then sends the same frame with `rc | 0xC0` to release.
  Channels: `5` open, `6` stop, `7` close.

## Disclaimer

Provided as is, without warranty. Automating motorised equipment can cause injury or damage.
