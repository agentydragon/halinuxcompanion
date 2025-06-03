"""Utility functions for halinuxcompanion."""

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def validate_url_scheme(url: str, allowed_schemes: tuple[str, ...] = ("http", "https")) -> bool:
    """Validate that a URL uses an allowed scheme.

    Args:
        url: The URL to validate
        allowed_schemes: Tuple of allowed URL schemes (default: http, https)

    Returns:
        True if URL has an allowed scheme, False otherwise
    """
    try:
        parsed = urlparse(url)
    except ValueError as e:
        logger.warning(f"Failed to parse URL: {url} - {e}")
        return False

    if parsed.scheme not in allowed_schemes:
        logger.warning(f"URL has disallowed scheme '{parsed.scheme}': {url}")
        return False

    if not parsed.netloc:
        logger.warning(f"URL missing host/netloc: {url}")
        return False

    return True
