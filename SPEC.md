# halinuxcompanion

Write a Python client for the Home Assistant mobile app API.

# References

Under `/references`, you can find the following resources:

* `.../companion.home-assistant`: documentation of existing Home Assistant mobile apps.
* `.../android`: source code of the Home Assistant Android app.
* `.../developers.home-assistant`: Home Assistant developer documentation, particularly:
  * `.../docs/api/native-app-integration.md`, `.../docs/api/native-app-integration`:
    documentation of the native app API.
* `.../core`: Home Assistant core source code, particularly:
  * `.../homeassistant/components/mobile_app`: source code of the mobile app integration.
  * `.../homeassistant/components/binary_sensor`: source code of the binary_sensor component.
  * `.../homeassistant/components/notify`: source code of the notify component.
  * `.../homeassistant/components/notify_events`
* `.../freedesktop_notification_spec.md`: FreeDesktop.org notification spec, which we'll use to display notifications.
* `.../bluez`: BlueZ documentation, which we'll use to query Bluetooth devices,
   particularly `.../doc/org.bluez.Device.rst` and `.../doc/org.bluez.Adapter.rst`.
* `.../upower`: UPower documentation, which we'll use to query battery status,
   particularly `.../dbus/org.freedesktop.UPower.xml`, `.../dbus/org.freedesktop.UPower.xml`, `.../dbus/org.freedesktop.UPower.Device.xml`.
* `.../geoclue`: Geoclue documentation, which we'll use to query location,
    particularly `.../interface/*.xml`.
* Some possible DBus libraries we may use (but we can also use others):
    * `.../dbus-fast`
    * `.../dasbus`

# Overview

Home Assistant mobile apps communicate with the Home Assistant server using a specific API,
different from the standard Home Assistant REST API.

The app must first *register* with the Home Assistant server. This will be done by commandline.

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
  * *Unlike* sensor disable function as specified in the mobile app API
    (<https://developers.home-assistant.io/docs/api/native-app-integration/sensors#keeping-sensors-in-sync-with-home-assistant>),
    force-disabled sensors will not be even registered with the server.
    This is because even their names might be privacy-sensitive.
    * (TODO for later: deleting sensors we no longer expose)
* Sensors will have nice appropriate icons, correct units of measurement,
  entity categories (e.g., for diagnostics etc.), state classes, device classes.
* Sensors will properly report unavailable states as appropriate.

### Battery

Battery info will be read from UPower, probably via DBus interface.

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

Battery level can be read via the [org.bluez.Battery1](references/bluez/doc/org.bluez.Battery.rst) interface.

### Network interfaces

* For each interface specified in config
  * IP address - possible to enable/disable
  * MAC address - possible to enable/disable
  * Connection state (connected/disconnected)
  * Signal strength (if available, e.g., Wi-Fi)
  * TX/RX counters - possible to enable/disable
* By default: all interfaces except obvious loopback/virtual/Docker/...

### Location

Use geoclue.

Will be exposed through the separate *non-sensor* shared location+battery
API call: https://developers.home-assistant.io/docs/api/native-app-integration/sending-data#update-device-location

Of course possible to disable with config.

### Other sensors

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

## Notifications

Home Assistant may send notifications to the app's embedded HTTP server - i.e.,
app will register itself as `push_url` in registration `app_data` (
<https://developers.home-assistant.io/docs/api/native-app-integration/notifications#enabling-cloud-push-notifications>).

Notifications will be displayed using DBus + FreeDesktop.org notification spec.
We will support the maximum set of features enabled by the intersection of it and Home Assistant notification features
including but not limited to:

* Executing actions sent by Home Assistant server
  * User may configure specific whitelisted commands - e.g. if Home Assistant
    sends a notification with `message=command_shutdown`, then the app will execute
    the `shutdown` command and run `systemctl poweroff`.
* Executing actions in response to user actions on notifications
  * Including default action and one-of-several-actions buttons
  * Actions supported include at least:
    * Opening URLs,
    * Sending events to Home Assistant
      * See: [Android app's NotificationActionReceiver.kt](references/android/app/src/main/kotlin/io/homeassistant/companion/android/notifications/NotificationActionReceiver.kt)
  * URL opening will be validated to avoid risky URLs
* Notify Home Assistant server of notification dismissal
* Custom icons on notifications
* Basic HTML formatting
* Notification replacing

### Notification references in Companion app docs

Refer to companion app documentation for more details on features to support to the fullest extent possible:

* <references/companion.home-assistant/docs/notifications/basic.md>
  * Basic structure (parameters, ...)
  * Opening URLs: relative to HA instance, full URLs, noop (`noAction`)
  * Replacing notifications
  * Clearing a past notification
  * Notification timeouts
  * HTML formatting
  * Icons
  * (Can we support sticky notifications? Persistent? Progress? Fine to skip in V1.)
  * Likely not supported by DBus: grouping, chronometer, various obviously-mobile-specific, ...
  * TODO, mark for later (not in V1): TTS
* [Actionable notifications](references/companion.home-assistant/docs/notifications/actionable.md)
  * Action: URL
    * Validate schema etc.
  * Not sure: can we support text input?
* Attachments
  * [Standard](references/companion.home-assistant/docs/notifications/attachments.md)
    * Images, audio, video (as we can support)
    * Not sure if we can support images and videos in notifications - maybe only in the app UI?
  * [Dynamic](references/companion.home-assistant/docs/notifications/dynamic-content.md)
    * Maps, camera streams, ... - not sure if supportable
  * [Critical](references/companion.home-assistant/docs/notifications/critical.md)
    * Let's leave out for now, should be easy to potentially add things like loud blaring etc.
* [Notification Cleared](references/companion.home-assistant/docs/notifications/cleared.md) event reporting to Home Assistant server
  * I think we should be able to support this
* [Notification Commands](references/companion.home-assistant/docs/notifications/commands.md)
  * Definitely not (includes ios/android-specific):
    * clear_badge
    * update_complications
    * update_widgets
    * command_activity
    * command_app_lock
    * command_auto_screen_brightness
    * command_broadcast_intent
    * command_ringer_mode
    * remove_channel
  * Not now:
    * command_ble_transmitter
    * command_beacon_monitor
    * command_flashlight
    * command_high_accuracy_mode
    * command_launch_app
    * command_screen_brightness_level
    * command_screen_off_timeout
    * command_screen_on
    * command_stop_tts
    * command_persistent_connection
    * command_webview
  * Yes:
    * clear_notification
    * request_location_update (if it makes sense with geoclue)
    * command_update_sensors
  * Not now but would be nice later:
    * command_volume_level
    * command_media
    * command_dnd
    * command_bluetooth
* [Sounds](references/companion.home-assistant/docs/notifications/sounds.md)
  * Let's not do in V1 but cool
* [Local Push](references/companion.home-assistant/docs/notifications/local.md)
  * Let's not use for now - this is "use local IP/host if on hom wifi" feature. It's cool but not needed for V1.
* [Notification Received](references/companion.home-assistant/docs/notifications/received.md)
  * Let's support

# Configuration

Readable TOML file in XDG standard directories.

# Models / libraries / general

Implementation will have closed enums for sensor types. Boolean sensors / non-boolean sensors will be checked against their allowed sensor types
(e.g.: "boolean - opening" = OK, "boolean - battery" = NOT OK).

Sensors updated lazily via getting state change notification (e.g., through DBus) if possible rather than poll.

* Optional dependencies:
  * If notification feature is enabled (i.e., displaying them), then FreeDesktop.org notification service.
  * Optional sensors talking to DBus services - iff sensor is enabled, dependency is hard:
    * Battery: UPower
    * Bluetooth: BlueZ
    * Location: geoclue
    * Session state:
      * `org.freedesktop.login1` - see `references/systemd/man/org.freedesktop.login1.xml`
      * `org.freedesktop.ScreenSaver`
      * `org.gnome.ScreenSaver`

* Hard dependencies:
  * Some kind of HTTP server for embedded server.
  * DBus via `dbus-fast` other library.
  * Authentication tokens (e.g., webhook ID) stored securely - i.e., Python `keyring` library.
  * `xdg-base-dirs` library for paths.
  * TOML library
  * Library for querying system information - e.g., `psutil` or similar.
  * Validated structures with Pydantic - minimal (if any) raw dicts etc.

Other dependencies may be added as needed - feel free to suggest/ask.

# Versions

## v1: Initial version

* No support for libsodium encryption (as the mobile app API specifies it) - https://developers.home-assistant.io/docs/api/native-app-integration/sending-data#implementing-encryption
* No location updates / GPS
* No zeroconf discovery
* No support for dynamic enabled/disabled sensors negotiation via mobile app API
  (<https://developers.home-assistant.io/docs/api/native-app-integration/sensors#keeping-sensors-in-sync-with-home-assistant>)
   -- only static configuration via config file which disables registering them altogether
* No need to support special-case behavior when on home wifi: https://developers.home-assistant.io/docs/api/native-app-integration/sending-data#short-note-on-instance-urls

# TODO

Maybe later:

* Calling HA service actions: <https://developers.home-assistant.io/docs/api/native-app-integration/sending-data#call-a-service-action>
  * Only useful if we give user some way to trigger them - e.g., CLI, HTML UI or topbar icon.
* User-fireable events: <https://developers.home-assistant.io/docs/api/native-app-integration/sending-data#fire-an-event>

# Notes

Rendering templates: not sure if useful for anything (<https://developers.home-assistant.io/docs/api/native-app-integration/sending-data#render-templates>).

Not sure what `get_zones` is for: <https://developers.home-assistant.io/docs/api/native-app-integration/sending-data#get-zones>

Camera streaming: <https://developers.home-assistant.io/docs/api/native-app-integration/sending-data#stream-camera>

Process conversation: <https://developers.home-assistant.io/docs/api/native-app-integration/sending-data#process-conversation>

Let's not support external authentication (<https://developers.home-assistant.io/docs/frontend/external-authentication>)
or external bus (<https://developers.home-assistant.io/docs/frontend/external-bus>) for now.

Might be interesting to connect more Bluetooth interfaces e.g. `org.bluez.MediaControl1` or `org.bluez.MediaPlayer1`.

Let's not use websockets for now.
