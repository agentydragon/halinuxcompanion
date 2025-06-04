# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Most of this remains yet to be implemented, so please update this file as you design & implement.

## Development Commands

### Setup

```bash
pip install -e .

# With dev dependencies
pip install -e ".[dev]"
```

### Testing & Linting

```bash
# Run tests
pytest
```

## Important Notes

- Python 3.10+ required

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
