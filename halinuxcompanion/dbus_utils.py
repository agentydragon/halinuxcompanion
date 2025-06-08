"""DBus utility functions."""

from typing import Any, TypeVar

from dbus_fast.signature import Variant

T = TypeVar("T")


def unwrap_variant(variant: Any, expected_type: type[T]) -> T:
    """Unwrap a DBus Variant and assert its type.

    Args:
        variant: The variant to unwrap (or a plain value)
        expected_type: The expected type of the value

    Returns:
        The unwrapped value

    Raises:
        AssertionError: If the value is not of the expected type
    """
    value = variant.value if isinstance(variant, Variant) else variant
    assert isinstance(value, expected_type), f"Expected {expected_type.__name__}, got {type(value).__name__}: {value!r}"
    return value
