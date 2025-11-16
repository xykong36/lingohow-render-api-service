"""
Timestamp formatting and parsing utilities.

Pure functions for converting between different time formats.
"""


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to HH:MM:SS format.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string (HH:MM:SS or MM:SS)

    Examples:
        >>> format_duration(3661.5)
        '01:01:01'
        >>> format_duration(125.0)
        '02:05'
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def parse_vtt_timestamp(timestamp_str: str) -> float:
    """
    Parse VTT timestamp to seconds.

    Supports formats:
    - HH:MM:SS.mmm
    - MM:SS.mmm

    Args:
        timestamp_str: VTT timestamp string

    Returns:
        Time in seconds as float

    Examples:
        >>> parse_vtt_timestamp("00:01:30.500")
        90.5
        >>> parse_vtt_timestamp("02:15.250")
        135.25
    """
    parts = timestamp_str.strip().split(':')

    if len(parts) == 3:
        # HH:MM:SS.mmm
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    elif len(parts) == 2:
        # MM:SS.mmm
        minutes = int(parts[0])
        seconds = float(parts[1])
        return minutes * 60 + seconds
    else:
        return 0.0


__all__ = ['format_duration', 'parse_vtt_timestamp']
