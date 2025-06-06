"""Shared pytest fixtures for halinuxcompanion tests."""

import pytest

from halinuxcompanion.test_utils import CaptureUpdates


@pytest.fixture
def capture_updates():
    """Fixture to capture sensor updates."""
    return CaptureUpdates()
