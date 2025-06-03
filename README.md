# Home Assistant Linux Companion

Application to run on Linux desktop computer to provide sensor data to Home Assistant, and get notifications as if it was a mobile device.

## How To

### Requirements

Python 3.10+ and the related `dev` dependencies (usually `python3-dev` or `python3-devel` on your package manager)

### Authentication Methods

halinuxcompanion supports two authentication methods:

#### 1. OAuth Authentication (Recommended)
- Run `halinuxcompanion --oauth` to authenticate via OAuth
- Opens a browser for authentication with Home Assistant
- Tokens are automatically refreshed when they expire
- Supports secret storage backends (see below)

#### 2. Long-Lived Access Token
- Get token from your Home Assistant user profile
- Token storage depends on your secret storage backend:
  - **With `libsecret` backend**: Use system keyring (e.g., `secret-tool store --label="Home Assistant Token" service halinuxcompanion username token`)
  - **With `file` backend**: Save to `~/.local/state/halinuxcompanion/long_lived_token` with 600 permissions

### Secret Storage

Secrets (i.e., OAuth tokens / long-lived access tokens) are stored
in either files subject to permission checks or in the system keyring.
They don't go directly into the configuration file.

Authentication tokens can be stored using different backends:

1. **System Keyring (libsecret)** - Recommended
   - Uses GNOME Keyring, KDE Wallet, or other system keyrings
   - Most secure option - tokens encrypted by system
   - Set `storage_backend: "libsecret"` in config

2. **File Storage** - Default fallback
   - Tokens stored in `~/.local/state/halinuxcompanion/`
   - Files have restricted permissions (600)
   - Set `storage_backend: "file"` in config

After initial registration, most operations (sensor updates) use webhook authentication. Registration data is saved to `~/.local/state/halinuxcompanion/registration.json`.

### Installation

1. Install the package:

   ```shell
   pip install git+https://github.com/benleb/halinuxcompanion.git
   ```

   Or for development:
   ```shell
   git clone https://github.com/benleb/halinuxcompanion.git
   cd halinuxcompanion
   pip install -e .
   ```

1. Create configuration directory and copy example config:

   ```shell
   mkdir -p ~/.config/halinuxcompanion
   # For TOML format (recommended):
   curl -o ~/.config/halinuxcompanion/config.toml https://raw.githubusercontent.com/benleb/halinuxcompanion/master/config.example.toml
   ```

1. Edit the configuration file to match your setup and desired options.
1. Configure authentication using one of these methods:

   **Option A: OAuth (Recommended)**
   ```shell
   halinuxcompanion oauth
   ```

   **Option B: Long-lived token**
   - Get a token from your Home Assistant user profile
   - Store it based on your `storage_backend` setting:

     For `file` backend (default):
     ```shell
     mkdir -p ~/.local/state/halinuxcompanion
     echo "YOUR_LONG_LIVED_TOKEN" > ~/.local/state/halinuxcompanion/long_lived_token
     chmod 600 ~/.local/state/halinuxcompanion/long_lived_token
     ```

     For `libsecret` backend:
     ```shell
     secret-tool store --label="Home Assistant Token" service halinuxcompanion username token
     # Then enter your token when prompted
     ```

1. Run the application:

   ```shell
   halinuxcompanion
   ```

   Or with a custom config location:
   ```shell
   halinuxcompanion --config /path/to/config.toml
   ```
### Systemd Service Setup

To run halinuxcompanion as a systemd service:

1. Create a systemd user service file:

   ```shell
   mkdir -p ~/.config/systemd/user/
   cat > ~/.config/systemd/user/halinuxcompanion.service << EOF
   [Unit]
   Description=Home Assistant Linux Companion
   Documentation=https://github.com/benleb/halinuxcompanion
   After=network-online.target

   [Service]
   Type=simple
   ExecStart=$(which halinuxcompanion)
   Restart=always
   RestartSec=30

   [Install]
   WantedBy=default.target
   EOF
   ```

2. Enable and start the service:

   ```shell
   systemctl --user daemon-reload
   systemctl --user enable --now halinuxcompanion
   ```

3. Check status and logs:

   ```shell
   systemctl --user status halinuxcompanion
   journalctl --user -u halinuxcompanion -f
   ```

Now in your Home Assistant you will see a new device in the **"mobile_app"** integration, and there will be a new service to notify your Linux desktop. Notification actions work and the expected events will be fired in Home Assistant.

### Command Line Options

- `oauth`: Run OAuth authentication flow and exit
- `--config <path>`: Specify custom config file location (default: `~/.config/halinuxcompanion/config.toml`)
- `--loglevel <level>`: Set logging level (DEBUG, INFO, WARNING, ERROR)
- `--version`: Show version information

## Technical

**Documentation Note**: This project includes a `references/` folder containing local copies of relevant Home Assistant documentation for offline reference. See `references/fetch.sh` to update these docs.

- Native App Integration (see `references/developers.home-assistant/docs/api/native-app-integration.md`)
- REST API (see `references/developers.home-assistant/docs/api/rest.md`)
- Asynchronous (because why not :smile:)
  - HTTP Server ([aiohttp](https://docs.aiohttp.org/en/stable/)): Listen to POST notification service call from Home Assistant
  - Client ([aiohttp](https://docs.aiohttp.org/en/stable/)): POST to Home Assistant api, sensors, events, etc
  - [Dbus](https://www.freedesktop.org/wiki/Software/dbus/) interface ([dbus_next](https://python-dbus-next.readthedocs.io/en/latest/index.html)): Sending notifications and listening to notification actions from the desktop, also listens to sleep, shutdown to update the status sensor

## To-do

- [ ] Implement encryption (see `references/developers.home-assistant/docs/api/native-app-integration/sending-data.md`)
- [ ] Move sensors to MQTT
      The reasoning for the change is the limitations of the API, naturally is expected that desktop and laptops would go offline and I would like
      for the sensors to reflect this new state. But if for some reason the application is unable to send this new state to Home Assistant the values of the sensors would be stuck. But if the app uses MQTT it can set will topics for the sensors to be updated when the client can't communicate with the server.
- [ ] One day make it work with remote and local instance, for laptops roaming networks
- [x] Status sensors that listens to sleep, wakeup, shutdown, power_on
- [ ] Add more sensors
- [ ] Finish notifications functionality
    - [x] Add notification commands
    - [x] Notifications Clearing (see `references/companion.home-assistant/docs/notifications/notifications-basic.md`)
    - [ ] Notification Icon (see `references/companion.home-assistant/docs/notifications/notifications-basic.md`)

## Features

### Sensors

halinuxcompanion exposes the following sensors to Home Assistant:

#### CPU (`cpu`)
- **State**: CPU usage percentage (0-100)
- **Attributes**:
  - `load_1m`, `load_5m`, `load_15m`: System load averages
  - `cpu_count`: Number of CPU cores

#### Memory (`memory`)
- **State**: Memory usage percentage (0-100)
- **Attributes**:
  - `used`: Used memory in bytes
  - `total`: Total memory in bytes
  - `available`: Available memory in bytes
  - `used_gb`: Used memory in GB
  - `total_gb`: Total memory in GB
  - `available_gb`: Available memory in GB

#### Uptime (`uptime`)
- **State**: System uptime in seconds
- **Attributes**:
  - `days`, `hours`, `minutes`, `seconds`: Uptime breakdown
  - `readable`: Human-readable uptime (e.g., "5d 3h 45m 12s")

#### Status (`status`)
- **State**: `True` when system is running, `False` when going to sleep/shutdown
- **Attributes**:
  - `reason`: Current state reason (`power_on`, `sleep`, `shutdown`, etc.)
  - `idle`: Idle state (`active`, `idle`, `locked`, `unknown`)
- **Note**: Updated via D-Bus signals before sleep/shutdown events

#### Battery Sensors

halinuxcompanion provides two battery sensor implementations. Choose one based on your needs:

##### Battery Sensor Comparison

| Attribute | Type | Unit | `battery_psutil` | `battery_upower` | Example |
|-----------|------|------|------------------|------------------|---------|
| **State** | float | % | ✓ | ✓ | `87.5` |
| `power_plugged` | bool | - | ✓ | ✓ | `true` |
| `battery_state` | string | - | ✓ | ✓ | `"Charging"` |
| **Time Information** | | | | | |
| `time_to_empty` | string | - | ✓¹ | ✓¹ | `"2h 15m 30s"` |
| `seconds_to_empty` | int | s | ✓¹ | ✓¹ | `8130` |
| `time_to_full` | string | - | ✗ | ✓² | `"1h 30m"` |
| `seconds_to_full` | int | s | ✗ | ✓² | `5400` |
| **Power/Energy** | | | | | |
| `charging_rate_w` | float | W | ✗ | ✓² | `45.2` |
| `discharge_rate_w` | float | W | ✗ | ✓¹ | `15.7` |
| `energy_wh` | float | Wh | ✗ | ✓ | `47.52` |
| `energy_full_wh` | float | Wh | ✗ | ✓ | `57.72` |
| `energy_empty_wh` | float | Wh | ✗ | ✓ | `0.0` |
| **Battery Health** | | | | | |
| `health_percent` | float | % | ✗ | ✓ | `92.3` |
| `capacity_percent` | float | % | ✗ | ✓ | `91.8` |
| `charge_cycles` | int | - | ✗ | ✓ | `127` |
| **Technical Info** | | | | | |
| `voltage_v` | float | V | ✗ | ✓ | `12.4` |
| `temperature_c` | float | °C | ✗ | ✓ | `32.5` |
| `technology` | string | - | ✗ | ✓ | `"Lithium polymer"` |
| **Device Info** | | | | | |
| `warning_level` | string | - | ✗ | ✓ | `"Low"` |
| `model` | string | - | ✗ | ✓ | `"DELL 0FDRT"` |
| `vendor` | string | - | ✗ | ✓ | `"SMP"` |
| `serial` | string | - | ✗ | ✓ | `"1234"` |

¹ Only when discharging
² Only when charging

##### Battery State Values

**Common values** (both implementations):
- `"Charging"` - Battery is charging
- `"Discharging"` - Battery is discharging
- `"Fully charged"` - Battery is full

**Additional values** (battery_upower only):
- `"Unknown"` - State cannot be determined
- `"Empty"` - Battery is empty
- `"Pending charge"` - Battery is waiting to charge
- `"Pending discharge"` - Battery is waiting to discharge

#### Camera State (`camera_state`)
- **State**: `on` or `off`
- **Attributes**:
  - `in_use`: Whether camera is currently in use
  - `path`: Camera device path (e.g., `/dev/video0`)

#### Lid State (`lid_state`)
- **State**: `on` (open) or `off` (closed)
- **Type**: Binary sensor
- **Device Class**: `opening`

#### Network Interfaces (`network_interface`)
- **State**: Total bytes transferred (sent + received)
- **Attributes**:
  - `interface`: Interface name
  - `is_up`: Whether interface is up
  - `speed`: Link speed in Mbps
  - `mtu`: Maximum transmission unit
  - `bytes_sent`, `bytes_recv`, `bytes_total`: Traffic counters
  - `bytes_sent_formatted`, `bytes_recv_formatted`, `bytes_total_formatted`: Human-readable formats
  - `packets_sent`, `packets_recv`: Packet counters
  - `errors_in`, `errors_out`: Error counters
  - `drop_in`, `drop_out`: Dropped packet counters
  - `ipv4_addresses`: IPv4 addresses (only if `show_ip_addresses` is enabled)
  - `ipv6_addresses`: IPv6 addresses (only if `show_ip_addresses` is enabled)
  - `mac_address`: MAC address (only if `show_mac_address` is enabled)

#### Network Interface Status (`network_interface_status`)
- **State**: `on` (up) or `off` (down)
- **Type**: Binary sensor
- **Attributes**: Same as network interface sensor

#### Temperature (`temperature`)
- **State**: Temperature in Celsius
- **Attributes**:
  - `sensor_name`: Internal sensor identifier
  - `sensor_label`: Human-readable sensor name
  - `max_threshold`: Maximum safe temperature (if available)
  - `max_threshold_reached`: Whether max threshold is exceeded
  - `critical_threshold`: Critical temperature (if available)
  - `critical_threshold_reached`: Whether critical threshold is exceeded
  - `status`: `normal`, `high`, `critical`, or `low`

#### Bluetooth Devices (`bluetooth_device`)
For each whitelisted Bluetooth device, the following sensors are created:

- **Battery Level**: Device battery percentage (if supported)
- **Connected Status**: Binary sensor for connection state
- **Visible Status**: Binary sensor for device visibility
- **Volume**: Audio volume percentage (if applicable)
- **Playback State**: `playing`, `paused`, `stopped`, or `unknown`
- **Debug Info**: JSON object with all available device information

### Notifications

- Actionable Notifications (see `references/companion.home-assistant/docs/notifications/actionable-notifications.md`) - Triggers event in Home Assistant
  - Local action handler using URI: only relative style `/lovelace/myview` and `http(s)` uri supported so far.
- Notification cleared/dismissed (see `references/companion.home-assistant/docs/notifications/notification-cleared.md`) - Triggers event in Home Assistant
- Timeout (see `references/companion.home-assistant/docs/notifications/notifications-basic.md`)
- Commands (see `references/companion.home-assistant/docs/notifications/notification-commands.md`)
- Replacing (see `references/companion.home-assistant/docs/notifications/notifications-basic.md`)
- Clearing (see `references/companion.home-assistant/docs/notifications/notifications-basic.md`)
- Icon (see `references/companion.home-assistant/docs/notifications/notifications-basic.md`) **TODO**

### Default Commands (example config)
  - Suspend
  - Power off
  - Reboot
  - Hibernate
