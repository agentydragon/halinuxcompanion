"""Unit conversion utilities using Pint."""

import pint

# Initialize the unit registry
ureg = pint.UnitRegistry()

# Home Assistant unit definitions
ureg.define("percent = 0.01 * dimensionless = %")


def format_quantity(quantity: pint.Quantity) -> str:
    """Format a Pint quantity for human-readable display."""
    if quantity.magnitude is None:
        return "N/A"

    # Special formatting for common unit types
    if quantity.dimensionality == ureg.get_dimensionality("[time]"):
        return _format_duration(quantity)
    elif (
        quantity.dimensionality == ureg.get_dimensionality("[length] ** 3 / [time]")
        or str(quantity.units) == "byte"
    ):
        return _format_data_size(quantity)
    else:
        # Default formatting
        return f"{quantity:~.1f}"


def _format_duration(quantity: pint.Quantity) -> str:
    """Format duration as human-readable time."""
    total_seconds = int(quantity.to("second").magnitude)
    if total_seconds <= 0:
        return "0s"

    remaining, seconds = divmod(total_seconds, 60)
    remaining, minutes = divmod(remaining, 60)
    days, hours = divmod(remaining, 24)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def _format_data_size(quantity: pint.Quantity) -> str:
    """Format data size with appropriate binary prefix."""
    # Try different binary units to find the best fit
    for unit_str in ["TiB", "GiB", "MiB", "KiB", "B"]:
        converted = quantity.to(unit_str)
        if converted.magnitude >= 1.0 or unit_str == "B":
            if unit_str == "B":
                return f"{converted.magnitude:.0f} {unit_str}"
            else:
                return f"{converted.magnitude:.1f} {unit_str}"

    # Should never reach here
    return f"{quantity:~.1f}"
