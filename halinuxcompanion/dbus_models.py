"""Pydantic models for D-Bus notification format."""

from enum import IntEnum
from typing import List, Optional

from pydantic import BaseModel, Field


class UrgencyLevel(IntEnum):
    """Notification urgency levels."""

    LOW = 0
    NORMAL = 1
    CRITICAL = 2


class NotificationHints(BaseModel):
    """Typed notification hints based on the freedesktop spec.

    Standard hints from Table 4:
    https://specifications.freedesktop.org/notification-spec/1.3/hints.html
    """

    # Currently implemented
    urgency: Optional[UrgencyLevel] = Field(
        default=None, description="Urgency level (0=low, 1=normal, 2=critical)"
    )

    # Not yet implemented but defined in spec
    action_icons: Optional[bool] = Field(
        default=None, description="Use icon names in actions instead of text"
    )
    category: Optional[str] = Field(
        default=None,
        description="Notification category (e.g., 'email.arrived', 'im.received')",
    )
    desktop_entry: Optional[str] = Field(
        default=None, description="Desktop filename without .desktop suffix"
    )
    image_path: Optional[str] = Field(
        default=None, description="Alternative image location"
    )
    # image_data would be: Tuple[int, int, int, bool, int, int, bytes]
    # (width, height, rowstride, has_alpha, bits_per_sample, n_channels, data)
    # Not implementing the complex image data structures for now

    resident: Optional[bool] = Field(
        default=None, description="Keep notification after action invoked"
    )
    sound_file: Optional[str] = Field(
        default=None, description="Sound file path to play"
    )
    sound_name: Optional[str] = Field(
        default=None,
        description="Sound theme name from freedesktop.org sound naming spec",
    )
    suppress_sound: Optional[bool] = Field(
        default=None, description="Suppress sound playback"
    )
    transient: Optional[bool] = Field(
        default=None, description="Hint for transient notifications"
    )
    x: Optional[int] = Field(default=None, description="X position hint")
    y: Optional[int] = Field(default=None, description="Y position hint")

    # Vendor-specific hints can be added with "x-vendor-name." prefix

    def to_dbus_dict(self):
        """Convert to D-Bus hints dictionary with Variant types.

        Returns dict suitable for D-Bus with only non-None values.
        """
        from dbus_next.signature import Variant

        hints = {}

        if self.urgency is not None:
            hints["urgency"] = Variant("y", self.urgency.value)  # BYTE type

        if self.action_icons is not None:
            hints["action-icons"] = Variant("b", self.action_icons)

        if self.category is not None:
            hints["category"] = Variant("s", self.category)

        if self.desktop_entry is not None:
            hints["desktop-entry"] = Variant("s", self.desktop_entry)

        if self.image_path is not None:
            hints["image-path"] = Variant("s", self.image_path)

        if self.resident is not None:
            hints["resident"] = Variant("b", self.resident)

        if self.sound_file is not None:
            hints["sound-file"] = Variant("s", self.sound_file)

        if self.sound_name is not None:
            hints["sound-name"] = Variant("s", self.sound_name)

        if self.suppress_sound is not None:
            hints["suppress-sound"] = Variant("b", self.suppress_sound)

        if self.transient is not None:
            hints["transient"] = Variant("b", self.transient)

        if self.x is not None:
            hints["x"] = Variant("i", self.x)  # INT32

        if self.y is not None:
            hints["y"] = Variant("i", self.y)  # INT32

        return hints


class DBusNotification(BaseModel):
    """D-Bus notification format for org.freedesktop.Notifications.Notify.

    Based on the Desktop Notifications Specification:
    https://specifications.freedesktop.org/notification-spec/1.3/protocol.html
    """

    # Required parameters for Notify method
    app_name: str = Field(
        description="The optional name of the application sending the notification. Can be blank."
    )
    replaces_id: int = Field(
        default=0,
        ge=0,
        description="The optional notification ID that this notification replaces. "
        "0 means this notification won't replace any existing notifications.",
    )
    app_icon: str = Field(
        description="The optional program icon. Can be empty string for no icon."
    )
    summary: str = Field(
        description="The summary text briefly describing the notification."
    )
    body: str = Field(
        default="", description="The optional detailed body text. Can be empty."
    )
    actions: List[str] = Field(
        default_factory=lambda: ["default", "Default"],
        description="Actions as pairs [id, label, id, label, ...]. "
        "Even elements are action identifiers, odd elements are localized labels.",
    )
    hints: NotificationHints = Field(
        default_factory=NotificationHints, description="Structured notification hints"
    )
    expire_timeout: int = Field(
        default=-1,
        description="Timeout in milliseconds. -1 uses server default, 0 never expires.",
    )
