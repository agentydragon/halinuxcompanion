# TODO

## Features to Implement

### URL Scheme Handler
- [ ] Implement URL scheme handler as described in `references/companion.home-assistant/docs/integrations/url-handler.md`
  - Support for `homeassistant://` URL scheme
  - [ ] **Navigate** - `homeassistant://navigate/path` to update frontend page location
    - Example: `homeassistant://navigate/dashboard-mobile/my-subview`
    - Support `?server=` query param for multiple servers
  - [ ] **Call service** - `homeassistant://call_service/service_name?param=value`
    - Example: `homeassistant://call_service/device_tracker.see?entity_id=device_tracker.entity`
    - Query parameters passed as dictionary to the service call
  - [ ] **Fire event** - `homeassistant://fire_event/event_name?param=value`
    - Example: `homeassistant://fire_event/custom_event?entity_id=MY_CUSTOM_EVENT`
    - Query parameters passed as event data
  - [ ] **Send location** - `homeassistant://send_location/`
    - Update device location to Home Assistant
  - [ ] Register the URL handler with the desktop environment (XDG on Linux)
    - Create `.desktop` file with `MimeType=x-scheme-handler/homeassistant;`
    - Register with `xdg-mime` or similar

### Notification Enhancements

#### URL Action Support
- [ ] Support additional URL types in notification actions
  - [ ] **Entity More Info** - `entityId:<entity_id>` to open entity details
    - Example: `entityId:sun.sun`
  - [x] **No Action** - `noAction` to explicitly do nothing when notification is clicked
  - [ ] ~~**App URLs** - `app://...` (Android specific, not implementing)~~

#### Notification Content
- [ ] **Subtitle/Subject Support** - Add support for notification subtitle/subject field
- [ ] **HTML Formatting** - Support HTML in notification messages
  - XDG/D-Bus notifications DO support a subset of HTML markup (per `references/freedesktop_notification_spec.md`)
  - Supported tags:
    - `<b>...</b>` - Bold
    - `<i>...</i>` - Italic
    - `<u>...</u>` - Underline
    - `<a href="...">...</a>` - Hyperlink
    - `<img src="..." alt="..."/>` - Image
  - Need to check server capability: `body-markup`
- [ ] **Custom Icon** - Support custom notification icons via `icon_url`
  - Support public URLs
  - Support relative paths like `/local/icon/icon.png`
  - Handle icon downloading/caching
- [ ] **Notification Attachments** - Support image/video attachments
  - See `references/companion.home-assistant/docs/notifications/notification-attachments.md`
  - Support image attachments (photos, screenshots, etc.)
  - Support video attachments
  - Handle local file paths
  - Handle remote URLs with authentication
  - Consider caching/temporary storage

#### Low Priority Features
- [ ] **Notification Sensitivity** - Support privacy/sensitivity levels for notifications
  - Check if XDG supports this feature
- [ ] **TTS Notifications** - Text-to-speech support for notifications
  - Integrate with system TTS engine
- [ ] **Progress Notifications** - Support progress bars in notifications
  - XDG/D-Bus notification spec does NOT have standard progress bar support
  - Could potentially implement via custom hints or notification updates
