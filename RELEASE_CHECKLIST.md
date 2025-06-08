# Pre-Release Checklist

## Code Quality

- [ ] `pre-commit` clean
- [ ] No security vulnerabilities in dependencies: `pip-audit`

## Testing

- [ ] Sufficient unit tests
- [ ] Manual testing `tests/manual/*`
  - [ ] Registration flow works: `halinuxcompanion register`
  - [ ] Battery module reports correct states
  - [ ] Bluetooth module
    - [ ] Off -> on
      - [ ] `halinuxcompanion` **not running**
      - [ ] Bluetooth: turn **off**
      - [ ] **`halinuxcompanion run`**
      - [ ] HA: shows dev *not connected*
      - [ ] Bluetooth: turn **on**
      - [ ] Dev: **connect**
      - [ ] HA: shows dev *connected*, battery *available*
  - [ ] Sensor updates are sent to Home Assistant
    - [ ] Leave running -> battery sensor, bluetooth battery sensor on connected device tick down
  - [ ] Graceful shutdown works (SIGTERM/SIGINT)
  - [ ] Device appears correctly in Home Assistant

## Documentation

- [ ] README.md is up to date
- [ ] DESIGN.md reflects current architecture
- [ ] SPEC.md matches implementation
- [ ] CLAUDE.md has current development guidelines
- [ ] Docstrings are complete and accurate
- [ ] Configuration options are documented
- [ ] Installation instructions are clear

## Version Management

- [ ] Version bumped in `pyproject.toml`
- [ ] CHANGELOG.md updated with all changes
- [ ] Migration notes added if breaking changes exist
- [ ] Git tag created for release: `git tag -a v0.X.Y -m "Release v0.X.Y"`

## Dependencies

- [ ] All dependencies are pinned in `pyproject.toml`
- [ ] No unnecessary dependencies
- [ ] Lock file updated

## Packaging

- [ ] Package builds successfully: `python -m build`
- [ ] Package installs correctly: `pip install dist/*.whl`
- [ ] Entry points work after installation
- [ ] systemd setup steps work

## Platform Testing

- [ ] Tested on <record OS, Python, Home Assistant version>

## Home Assistant Integration

- [ ] Mobile app integration works
- [ ] Webhook registration succeeds
- [ ] Sensors appear with correct:
  - [ ] Names and unique IDs
  - [ ] Icons
  - [ ] Device classes
  - [ ] Units of measurement
  - [ ] Entity categories

## Security

- [ ] No hardcoded credentials or secrets
- [ ] OAuth flow uses CSRF protection
- [ ] Sensitive data (e.g., webhook ID) stored in keyring
- [ ] No sensitive data in logs
- [ ] No root required

## Performance

- [ ] Memory usage is reasonable
- [ ] CPU usage is minimal when idle
- [ ] Sensor updates are batched efficiently
- [ ] DBus connections are properly managed
- [ ] No memory leaks during long runs

## Final Steps

- [ ] Create GitHub release with:
  - [ ] Release notes from CHANGELOG
  - [ ] Binary artifacts attached
  - [ ] Installation instructions
- [ ] Publish to PyPI: `python -m twine upload dist/*`
- [ ] Update any external documentation
- [ ] Announce release

## Post-Release

- [ ] Verify package is available on PyPI
- [ ] Test installation from PyPI on clean system
- [ ] Update development version in `pyproject.toml` for next release
