# Home Assistant Linux Companion

Application to run on Linux desktop computer to provide sensor data to Home Assistant, and get notifications as if it was a mobile device.

## How To

### Requirements

Python 3.10+ and the related `dev` dependencies (usually `python3-dev` or `python3-devel` on your package manager)

### Authentication Methods

halinuxcompanion supports two authentication methods:

#### 1. OAuth Authentication (Recommended)
- Run `halinuxcompanion --oauth` to authenticate via OAuth
- Tokens are automatically refreshed when they expire
- Stored securely in `~/.local/state/halinuxcompanion/oauth_tokens.json`

#### 2. Long-Lived Access Token
- Add `ha_token` to your config file
- Get token from: [Home Assistant Profile](https://www.home-assistant.io/docs/authentication/#your-account-profile)
- Required for:
  - **Initial device registration** with Home Assistant (one-time)
  - **Sending notification events** (ongoing, only if notifications are enabled)

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
   # Or for JSON format:
   curl -o ~/.config/halinuxcompanion/config.json https://raw.githubusercontent.com/benleb/halinuxcompanion/master/config.example.json
   ```
   
1. Edit the configuration file to match your setup and desired options.
1. Configure authentication using one of these methods:
   
   **Option A: OAuth (Recommended)**
   ```shell
   halinuxcompanion --oauth
   ```
   
   **Option B: Long-lived token**
   - [Get a token from your Home Assistant user profile](https://www.home-assistant.io/docs/authentication/#your-account-profile)
   - Add `"ha_token": "your-token-here"` to your config file

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

## [Example configuration file](config.example.json)

```json
{
  "ha_url": "http://homeassistant.local:8123/",
  "ha_token": "mysuperlongtoken_or_leave_empty_to_use_oauth",
  "device_id": "computername",
  "device_name": "whatever you want can be left empty",
  "manufacturer": "whatever you want can be left empty",
  "model": "Computer",
  "computer_ip": "192.168.1.15",
  "computer_port": 8400,
  "refresh_interval": 15,
  "loglevel": "INFO",
  "sensors": {
    "cpu": {
      "enabled": true,
      "name": "CPU"
    },
    "memory": {
      "enabled": true,
      "name": "Memory Load"
    },
    "uptime": {
      "enabled": true,
      "name": "Uptime"
    },
    "status": {
      "enabled": true,
      "name": "Status"
    },
    "battery_level": {
      "enabled": true,
      "name": "Battery Level"
    },
    "battery_state": {
      "enabled": true,
      "name": "Battery State"
    },
    "camera_state": {
      "enabled": true,
      "name": "Camera State"
    }
  },
  "services": {
    "notifications": {
      "enabled": true,
      "url_program": "xdg-open",
      "commands": {
        "command_suspend": {
          "name": "Suspend",
          "command": ["systemctl", "suspend"]
        },
        "command_poweroff": {
          "name": "Power off",
          "command": ["systemctl", "poweroff"]
        },
        "command_reboot": {
          "name": "Reboot",
          "command": ["systemctl", "reboot"]
        },
        "command_hibernate": {
          "name": "Hibernate",
          "command": ["systemctl", "hibernate"]
        },
        "command_open_ha": {
          "name": "Open Home Assistant",
          "command": ["xdg-open", "http://homeassistant.local:8123/"]
        },
        "command_open_spotify": {
          "name": "Open Spotify Flatpak",
          "command": ["flatpak", "run", "com.spotify.Client"]
        }
      }
    }
  }
}
```

## Technical

- [Home Assistant Native App Integration](https://developers.home-assistant.io/docs/api/native-app-integration)
- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest)
- Asynchronous (because why not :smile:)
  - HTTP Server ([aiohttp](https://docs.aiohttp.org/en/stable/)): Listen to POST notification service call from Home Assistant
  - Client ([aiohttp](https://docs.aiohttp.org/en/stable/)): POST to Home Assistant api, sensors, events, etc
  - [Dbus](https://www.freedesktop.org/wiki/Software/dbus/) interface ([dbus_next](https://python-dbus-next.readthedocs.io/en/latest/index.html)): Sending notifications and listening to notification actions from the desktop, also listens to sleep, shutdown to update the status sensor

## To-do

- [ ] [Implement encryption](https://developers.home-assistant.io/docs/api/native-app-integration/sending-data)
- [ ] Move sensors to MQTT  
    The reasoning for the change is the limitations of the API, naturally is expected that desktop and laptops would go offline and I would like for the sensors to reflect this new state. But if for some reason the application is unable to send this new state to Home Assistant the values of the sensors would be stuck. But if the app uses MQTT it can set will topics for the sensors to be updated when the client can't communicate with the server.
- [ ] One day make it work with remote and local instance, for laptops roaming networks
- [x] Status sensors that listens to sleep, wakeup, shutdown, power_on
- [ ] Add more sensors
- [ ] Finish notifications functionality
    - [x] Add notification commands
    - [x] [Notifications Clearing](https://companion.home-assistant.io/docs/notifications/notifications-basic/#clearing)
    - [ ] [Notification Icon](https://companion.home-assistant.io/docs/notifications/notifications-basic/#notification-icon)

## Features

- Sensors:
  - CPU
  - Memory
  - Uptime
  - Status: Computer status, reflects if the computer went to sleep, wakes up, shutdown, turned on. The sensor is updated right before any of these events happen by listening to dbus signals.
  - Battery Level
  - Batter State
- Notifications:
  - [Actionable Notifications](https://companion.home-assistant.io/docs/notifications/actionable-notifications#building-actionable-notifications) (Triggers event in Home Assistant)
      - [Local action handler using URI](https://companion.home-assistant.io/docs/notifications/actionable-notifications#uri-values): only relative style `/lovelace/myviwew` and `http(s)` uri supported so far.
  - [Notification cleared/dismissed](https://companion.home-assistant.io/docs/notifications/notification-cleared/) (Triggers event in Home Assistant)
  - [Timeout](https://companion.home-assistant.io/docs/notifications/notifications-basic#notification-timeout)
  - [Commands](https://companion.home-assistant.io/docs/notifications/notification-commands/)
  - [Replacing](https://companion.home-assistant.io/docs/notifications/notifications-basic/#replacing)
  - [Clearing](https://companion.home-assistant.io/docs/notifications/notifications-basic/#clearing)
  - [Icon](https://companion.home-assistant.io/docs/notifications/notifications-basic/#notification-icon) **TODO**
- Default commands (example config):
  - Suspend
  - Power off
  - Reboot
  - Hibernate
