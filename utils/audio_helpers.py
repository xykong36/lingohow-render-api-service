"""
Audio generation utilities (DEPRECATED - Use utils/audio_generator.py instead).

⚠️ DEPRECATED: This module uses subprocess to call edge-tts CLI.
The new async implementation in utils/audio_generator.py is recommended for:
- Better performance (uses edge-tts Python API directly)
- Proper async/await support
- Timeout and retry mechanisms
- Better error handling

Functions for checking TTS availability and generating audio files using edge-tts.
"""

import warnings

warnings.warn(
    "utils/audio_helpers.py is deprecated. Use utils/audio_generator.py instead.",
    DeprecationWarning,
    stacklevel=2
)

import subprocess
from pathlib import Path

from .text_helpers import format_text_for_tts


def check_edge_tts_available() -> bool:
    """
    Check if edge-tts is available in the system.

    Returns:
        True if edge-tts command is available, False otherwise

    Examples:
        >>> check_edge_tts_available()
        True  # if edge-tts is installed
    """
    try:
        result = subprocess.run(
            ['edge-tts', '--help'],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def generate_audio_with_edge_tts(
    text: str,
    output_path: Path,
    voice: str = "en-US-AvaMultilingualNeural"
) -> bool:
    """
    Generate audio using edge-tts command line tool.

    Args:
        text: Text to convert to speech
        output_path: Output file path
        voice: Voice model to use (default: en-US-AvaMultilingualNeural)

    Returns:
        True if successful, False otherwise

    Examples:
        >>> from pathlib import Path
        >>> output = Path("/tmp/test.mp3")
        >>> generate_audio_with_edge_tts("Hello World", output)
        True  # if edge-tts is available and generation succeeds
    """
    try:
        # Format text for better TTS pronunciation
        formatted_text = format_text_for_tts(text)

        command = [
            'edge-tts',
            '--text', formatted_text,
            '--voice', voice,
            '--write-media', str(output_path)
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0:
            return True

        return False

    except Exception:
        return False


__all__ = ['check_edge_tts_available', 'generate_audio_with_edge_tts']
