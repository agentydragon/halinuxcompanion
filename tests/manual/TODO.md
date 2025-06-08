# Manual Testing Framework TODO

## In Progress
- [ ] Test the framework with actual Home Assistant instance

## TODO

### Test Scenarios (postponed for now)
- "dev" = whitelisted device
- "HA" = Home Assistant web frontend

- [ ] Bluetooth: On → Off → On
  - [ ] `halinuxcompanion` **not running**
  - [ ] Bluetooth: turn **on**
  - [ ] Dev: **connect**
  - [ ] **`halinuxcompanion run`**
  - [ ] HA: shows dev *connected*, battery *available*
  - [ ] Bluetooth: turn **off**
  - [ ] HA: shows dev *not connected*, battery *unavailable*
  - [ ] Bluetooth: turn **on**
  - [ ] Dev: **connect**
  - [ ] HA: shows dev *connected*, battery *available*
- [ ] Bluetooth: Connected → Disconnected → Connected
  - [ ] `halinuxcompanion` **not running**
  - [ ] Bluetooth: turn **on**
  - [ ] Dev: **connect**
  - [ ] **`halinuxcompanion run`**
  - [ ] HA: shows dev *connected*, battery *available*
  - [ ] Bluetooth: on
  - [ ] Dev: **disconnect**
  - [ ] HA: shows dev *not connected*, *visible*, battery *possibly unavailable*
  - [ ] Dev: **connect**
  - [ ] HA: shows dev *connected*, battery *available*
- [ ] Bluetooth: Disconnected → Connected
  - [ ] `halinuxcompanion` **not running**
  - [ ] Bluetooth: turn **on**
  - [ ] Dev: **disconnect**
  - [ ] **`halinuxcompanion run`**
  - [ ] HA: shows dev *not connected*, *visible*, battery *possibly unavailable*
  - [ ] Dev: **connect**
  - [ ] HA: shows dev *connected*, battery *available*
- [ ] Battery: Basic Functionality
- [ ] General: Sensor Updates
- [ ] General: Graceful Shutdown

### Framework Improvements
- [ ] Add WebSocket support for real-time HA state monitoring
- [ ] Create HTML report generation (in addition to Markdown)
- [ ] Add video recording support for test sessions
- [ ] Create test result comparison tool
- [ ] Add automated pre-flight checks (HA available, DBus accessible, etc.)
- [ ] Support for multiple HA instances
- [ ] Add test data anonymization for sharing

### Integration
- [ ] CI/CD integration for automated manual test scheduling
- [ ] Slack/Discord notifications for test results
- [ ] Integration with existing test management tools
- [ ] Create dashboard for historical test results

### Documentation
- [ ] Create user guide for running manual tests
- [ ] Document how to add new test scenarios
- [ ] Create troubleshooting guide
- [ ] Add examples of good test notes

## Notes

### Dependencies Status
- Robot Framework: ✓ Installed via requirements
- Docker support: ✓ Optional, falls back to existing HA
- DBus access: Required for real testing
- HA access token: Required for sensor collection (prompted during test)

### Architecture Decisions
- Using Robot Framework for flexibility and reporting
- String enum for verification status (not bool | str)
- Jinja2 for report templating
- Docker optional but recommended for isolation
- All diagnostics collected automatically
