"""Shared test utilities for halinuxcompanion."""

from dataclasses import dataclass, field

from halinuxcompanion.modules.base import SensorUpdate


@dataclass
class CaptureUpdates:
    """Helper class to capture sensor updates in tests."""

    updates: list[SensorUpdate] = field(default_factory=list)

    async def __call__(self, update: SensorUpdate):
        """Capture a sensor update."""
        self.updates.append(update)

    def __len__(self):
        """Return number of captured updates."""
        return len(self.updates)

    def __iter__(self):
        """Iterate over captured updates."""
        return iter(self.updates)

    def clear(self):
        """Clear all captured updates."""
        self.updates.clear()

    def get_by_id(self, unique_id: str) -> list[SensorUpdate]:
        """Get all updates for a specific sensor ID."""
        return [u for u in self.updates if u.unique_id == unique_id]

    def get_latest_by_id(self, unique_id: str) -> SensorUpdate | None:
        """Get the latest update for a specific sensor ID."""
        updates = self.get_by_id(unique_id)
        return updates[-1] if updates else None
