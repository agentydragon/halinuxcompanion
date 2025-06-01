"""Unit conversion utilities using Pint."""

import pint

# Initialize the unit registry
ureg = pint.UnitRegistry()

# Home Assistant unit definitions
ureg.define("percent = 0.01 * dimensionless = %")
