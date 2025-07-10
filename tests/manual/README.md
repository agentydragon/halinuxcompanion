# Home Assistant Linux Companion Manual Testing

This directory contains manual test scenarios for Home Assistant Linux Companion using Robot Framework.

## Prerequisites

1. Python 3.10+ with virtual environment
2. Home Assistant instance (local or Docker)
3. Linux desktop with DBus access
4. Bluetooth hardware (for Bluetooth tests)

## Setup

**⚠️ IMPORTANT: Always use a virtual environment to avoid conflicts with system packages (especially pytest-socket)!**

```bash
# Create virtual environment (if not already created)
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Linux/Mac
# or
venv\Scripts\activate     # On Windows

# Install dependencies
pip install -r requirements.txt
```

**Note**: The test runner will warn you if you're not in a virtual environment.

## Running Tests

### Quick Start

```bash
# Run all tests
./run_manual_tests.py

# Run only Bluetooth tests
./run_manual_tests.py --test bluetooth

# Run only smoke tests
./run_manual_tests.py --tag smoke

# With HA token for sensor collection
./run_manual_tests.py --ha-token YOUR_LONG_LIVED_TOKEN
```

### Using Robot Framework Directly

```bash
# Run specific test file
robot bluetooth_scenarios.robot

# Run with custom output directory
robot --outputdir results_$(date +%Y%m%d_%H%M%S) bluetooth_scenarios.robot

# Run specific test case
robot --test "Bluetooth OFF to ON Transition" bluetooth_scenarios.robot
```

## Test Scenarios

### Bluetooth Tests (`bluetooth_scenarios.robot`)
- **Bluetooth OFF to ON Transition**: Tests enabling Bluetooth and connecting devices
- **Bluetooth ON to OFF Transition**: Tests disabling Bluetooth and disconnection handling

### Battery Tests (`battery_scenarios.robot`)
- **Battery State Monitoring**: Tests power state tracking and updates
- **Low Battery Alert Test**: Tests low battery threshold notifications (laptop only)

## Test Structure

```
manual/
├── HALinuxCompanionLibrary.robot    # Shared Robot keywords and resources
├── bluetooth_scenarios.robot         # Bluetooth test cases
├── battery_scenarios.robot          # Battery/power test cases
├── run_manual_tests.py             # Convenience runner script
├── python_implementation/          # Original Python implementation (reference)
│   ├── HACompanionLibrary.py      # Python library used by Robot
│   └── ...
└── manual_test_results/           # Test execution results
```

## Adding New Tests

1. Create a new `.robot` file for your test suite
2. Import the resource file: `Resource    HALinuxCompanionLibrary.robot`
3. Define test cases using Robot Framework syntax
4. Use the provided keywords for common operations:
   - `Start HALinuxCompanion`
   - `Get User Verification`
   - `Collect DBus Diagnostics`
   - `Take Screenshot`
   - `Collect HA Sensor Data`

## Test Reports

After running tests, Robot Framework generates:
- `report.html` - High-level test report
- `log.html` - Detailed execution log
- `output.xml` - Machine-readable results

Additional artifacts in the results directory:
- DBus diagnostics
- Screenshots
- Home Assistant sensor data
- halinuxcompanion logs

## Manual Test Guidelines

1. **Be Clear**: Test steps should be explicit and unambiguous
2. **Be Patient**: Allow time for sensor updates to propagate
3. **Document Issues**: Use the notes feature to record any problems
4. **Collect Evidence**: Screenshots and diagnostics help debug issues
5. **Verify Everything**: Don't assume - verify each state change

## Troubleshooting

### Home Assistant Connection
- Ensure HA is running at http://localhost:8123
- For sensor collection, create a long-lived access token in HA
- Check if halinuxcompanion is registered as a Mobile App integration

### DBus Access
- Run tests as your regular user (not root)
- Ensure DBus session is available
- Check Bluetooth service status: `systemctl status bluetooth`
