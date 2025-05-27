"""Common utility functions."""


def format_seconds_to_time(seconds: int) -> str:
    """Format seconds into a human-readable time format.

    Args:
        seconds: Number of seconds to format

    Returns:
        Formatted string like "2d 3h 45m" or "1h 23m 45s" or "45m 12s"
    """
    if seconds < 0:
        return "Unknown"

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{int(days)}d")
    if hours > 0:
        parts.append(f"{int(hours)}h")
    if minutes > 0:
        parts.append(f"{int(minutes)}m")
    if secs > 0 or not parts:  # Always show seconds if nothing else
        parts.append(f"{int(secs)}s")

    return " ".join(parts)


def format_bytes(num_bytes: int) -> str:
    """Format bytes into human-readable format.

    Args:
        num_bytes: Number of bytes

    Returns:
        Formatted string like "1.5 GB" or "750 MB"
    """
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} EB"


