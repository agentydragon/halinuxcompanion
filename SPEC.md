Write a Python implementation of the Home Assistant mobile app API.

# References

* `/references/companion.home-assistant`: documentation of existing Home Assistant mobile apps.
* `/references/android`: source code of the Home Assistant Android app.
* `/references/developers.home-assistant`: Home Assistant developer documentation, particularly:
  * `.../docs/api/native-app-integration.md`, `.../docs/api/native-app-integration`:
    documentation of the native app API.
* `/references/core`: Home Assistant core source code, particularly:
  * `.../homeassistant/components/mobile_app`: source code of the mobile app integration.
  * `.../homeassistant/components/binary_sensor`: source code of the binary_sensor component.
  * `.../homeassistant/components/notify`: source code of the notify component.
  * `.../homeassistant/components/notify_events`
* `/references/freedesktop_notification_spec.md`: FreeDesktop.org notification spec, which we'll use to display notifications.
* `/references/bluez`: BlueZ documentation, which we'll use to query Bluetooth devices,
   particularly `.../doc/device-api.txt` and `.../doc/adapter-api.txt`.
* `/references/upower`: UPower documentation, which we'll use to query battery status,
   particularly `.../dbus/org.freedesktop.UPower.xml`, `.../dbus/org.freedesktop.UPower.xml`, `.../dbus/org.freedesktop.UPower.Device.xml`.

# Overview

Home Assistant mobile apps communicate with the Home Assistant server using a specific API,
different from the standard Home Assistant REST API.

The app must first *register* with the Home Assistant server.
This will be done by commandline.

User will provide the URL of their instance and the app will initiate an OAuth flow to obtain an access token.
App will then use the token to issue the authenticated registration call. Henceforth, it will communicate only
using the mobile-app-specific webhook (which authenticates it to the server).

After the initial registration, the app WILL NOT retain the OAuth access token.
If the registration is lost, user will have to re-register again through a new OAuth flow.

When run, app will:

* If needed and running from a terminal, ask user to complete the OAuth registration flow.
  * (If not running from terminal and no registration is found, exit with an error.)
* Register sensors, do any other needed handshakes, start the embedded server.
* Send initial state of all sensors.
* Send sensor updates either on change (if possible) or periodically (for sensors that have to be polled).
* Listen for notifications from the Home Assistant server and display them using the FreeDesktop.org notification spec.
  (Or execute associated commands.)
* Listen for notification actions from DBus and act on them (e.g., execute commands, open URLs, notify Home Assistant server).

# Features to support

## Sensors

* Each sensor can be force-disabled in app settings for privacy
  * e.g.: "do not expose any disk sensors"
  * Force-disabled sensors will not be even registered with the server
    * (TODO for later: deleting sensors we no longer expose)

### Battery

Read via UPower DBus interface.

* General state (charging, discharging, full, empty)
* Power consumption / charge speed, if available
* Battery level in %
* Time until full / empty, if available

### Bluetooth

Bluetooth devices will be queried using BlueZ D-Bus API.

* Boolean: bluetooth (on computer) enabled/disabled
* For each Bluetooth device whitelisted in app config (by MAC):
  * Name
  * MAC
  * Is connected (boolean)
  * RSSI (signal strength)
  * Battery level (if available)

### Other sensors

* Location (GNOME location service)
  * Exposed through the separate non-sensor shared location+battery API call
  * Of course possible to disable with config
* Temperature sensors (e.g., CPU, GPU, ...)
  * Individual sensors possible to turn on/off
* RAM usage
  * Including swap
* CPU usage
  * Frequency
  * Utilization 0..100%
  * Load average
* Disk usage
  * Per-partition possible to enable/disable
  * Space used / total
* Lid status (open/closed)
* Activity (locked screen / inactive / active)

## Network interfaces

* For each interface specified in config
  * IP address - possible to enable/disable
  * MAC address - possible to enable/disable
  * Connection state (connected/disconnected)
  * Signal strength (if available, e.g., Wi-Fi)
  * TX/RX counters - possible to enable/disable
* By default: all interfaces except obvious loopback/virtual/Docker/...

## Notifications

Home Assistant may send notifications to the app's embedded HTTP server.

Notifications will be displayed using DBus + FreeDesktop.org notification spec.
We will support the maximum set of features enabled by the intersection of it and Home Assistant notification features
including but not limited to:

* Executing actions sent by Home Assistant server
  * User may configure specific whitelisted commands - e.g. if Home Assistant
    sends a notification with `message=command_shutdown`, then the app will execute
    the `shutdown` command and run `systemctl poweroff`.
* Executing actions in response to user actions on notifications
  * Including default action and one-of-several-actions buttons
  * Actions supported include at least: opening URLs, sending events to Home Assistant
  * URL opening will be validated to avoid risky URLs
* Notify Home Assistant server of notification dismissal
* Custom icons on notifications
* Basic HTML formatting
* Notification replacing

## Other features

* Sending location updates
  * Including battery, if present
  * Possible to enable/disable

# Configuration

Readable TOML file in XDG standard directories. Using `xdg-base-dirs` library for paths.

# Models / libraries / general

Implementation will have closed enums for sensor types. Boolean sensors / non-boolean sensors will be checked against their allowed sensor types
(e.g.: "boolean - opening" = OK, "boolean - battery" = NOT OK).

Authentication tokens (e.g., webhook ID) stored securely - i.e., Python `keyring` library.

Sensors updated lazily via getting state change notification (e.g., through DBus)
if possible rather than poll.

* DBus will use `dbus-next`.
* Validated structures with Pydantic - minimal (if any) raw dicts etc.
* One possible library we can use for querying system information is `psutil`.

# Versions

## v1: Initial version

* No support for libsodium encryption (as the mobile app API specifies it)
* No location updates / GPS
* No zeroconf discovery
* No support for dynamic enabled/disabled sensors negotiation via mobile app API --
  only static configuration via config file which disables registering them altogether
