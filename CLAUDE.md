# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Most of this remains yet to be implemented, so please update this file as you design & implement.

## Development Commands

### Setup

This project requires a clean Python environment. Use pyenv and virtualenv to avoid conflicts with system-wide packages (particularly pytest-socket which can interfere with DBus tests).

```bash
# Using pyenv (recommended)
pyenv local 3.11.12  # or another Python 3.10+ version
python -m venv venv
source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

### Testing & Linting

```bash
# Run tests
source venv/bin/activate
pytest
```

## Important Notes

- Python 3.10+ required
- Work in the ./venv virtual environment to avoid interference with system Python
- Beware of packages like pytest-socket that can cause issues

## Code Style Guidelines

### Exception Handling
- Keep try-except blocks as minimal as possible - only wrap the specific operations that can throw the exception
- Never use broad exception catching without good reason
- Example:
  ```python
  # BAD - too broad
  try:
      with open(path, "r") as f:
          content = f.read()
      if "error" in content:
          return None
  except Exception:
      return None

  # GOOD - minimal scope
  try:
      with open(path, "r") as f:
          content = f.read()
  except (OSError, IOError) as e:
      logger.error(f"Failed to read {path}: {e}")
      return None

  if "error" in content:
      return None
  ```

### Logging Exceptions
- Use `logging.exception()` instead of `logging.error()` or others when logging exceptions inside an exception block
  - TRY400 Rule: When catching and logging exceptions, use `logger.exception()` to automatically include the full traceback

## Code Safety Guidelines

- Do not assemble URLs with plain string concat, e.g. `[f"{k}={v}" for k, v in params.items()]`. use some existing library that auto-wraps escaping etc.; apply *generally* for *all* formats that need escaping/similar.
