"""Test for DBus utility functions."""

import pytest
from dbus_fast.signature import Variant

from halinuxcompanion.dbus_utils import unwrap_variant


def test_unwrap_variant_with_variant():
    """Test unwrapping actual Variant objects."""
    assert unwrap_variant(Variant("s", "hello"), str) == "hello"
    assert unwrap_variant(Variant("b", True), bool) is True
    assert unwrap_variant(Variant("i", 42), int) == 42


def test_unwrap_variant_with_plain_value():
    """Test that plain values pass through unchanged."""
    assert unwrap_variant("plain string", str) == "plain string"
    assert unwrap_variant(True, bool) is True
    assert unwrap_variant(123, int) == 123


def test_unwrap_variant_type_assertion():
    """Test that type mismatches raise AssertionError."""
    # Variant with wrong type
    string_variant = Variant("s", "hello")
    with pytest.raises(AssertionError, match="Expected int, got str: 'hello'"):
        unwrap_variant(string_variant, int)

    # Plain value with wrong type
    with pytest.raises(AssertionError, match="Expected str, got int: 42"):
        unwrap_variant(42, str)
