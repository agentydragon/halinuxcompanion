"""Tests for utility functions."""

from halinuxcompanion.utils import validate_url_scheme


def test_validate_url_scheme_valid():
    """Test validation of valid URLs."""
    assert validate_url_scheme("http://example.com")
    assert validate_url_scheme("https://example.com:8123")
    assert validate_url_scheme("https://192.168.1.100")
    assert validate_url_scheme("http://localhost:8123/api")


def test_validate_url_scheme_invalid():
    """Test validation of invalid URLs."""
    # Invalid schemes
    assert not validate_url_scheme("file:///etc/passwd")
    assert not validate_url_scheme("ftp://example.com")
    assert not validate_url_scheme("javascript:alert('xss')")

    # Missing host
    assert not validate_url_scheme("http://")
    assert not validate_url_scheme("https://")

    # Malformed URLs
    assert not validate_url_scheme("not a url")
    assert not validate_url_scheme("")


def test_validate_url_scheme_custom_schemes():
    """Test validation with custom allowed schemes."""
    assert validate_url_scheme("ftp://example.com", allowed_schemes=("ftp", "ftps"))
    assert not validate_url_scheme("http://example.com", allowed_schemes=("ftp", "ftps"))
