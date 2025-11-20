"""
Async phrase audio generation using edge-tts with special formatting.

This module provides async functions for generating audio files from phrases
using Microsoft Edge TTS with phrase-specific formatting rules (e.g., acronyms).
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

from utils.phrase_helpers import format_phrase_for_tts, clean_phrase_filename

logger = logging.getLogger(__name__)


class PhraseAudioGenerationError(Exception):
    """Custom exception for phrase audio generation errors."""
    pass


async def generate_phrase_audio_async(
    phrase: str,
    output_path: Path,
    voice: str = "en-US-AvaMultilingualNeural",
    timeout: int = 30,
    max_retries: int = 2
) -> bool:
    """
    Generate audio file for a phrase asynchronously using edge-tts Python API.

    This function applies phrase-specific formatting (like spacing acronyms)
    before generating audio with edge-tts.

    Args:
        phrase: Phrase text to convert to speech
        output_path: Path where to save the MP3 file
        voice: Edge TTS voice model (default: en-US-AvaMultilingualNeural)
        timeout: Timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts (default: 2)

    Returns:
        True if successful, False otherwise

    Examples:
        >>> import asyncio
        >>> from pathlib import Path
        >>> output = Path("/tmp/phrase.mp3")
        >>> asyncio.run(generate_phrase_audio_async("break the ice", output))
        True
    """
    if not EDGE_TTS_AVAILABLE:
        logger.error("edge-tts library is not installed")
        return False

    if not phrase or not phrase.strip():
        logger.warning("Empty phrase provided, skipping audio generation")
        return False

    phrase = phrase.strip()

    # Format phrase for TTS (apply special rules for acronyms, etc.)
    formatted_phrase = format_phrase_for_tts(phrase)

    # Log if formatting changed the phrase
    if formatted_phrase != phrase:
        logger.info(f"Phrase formatted for TTS: '{phrase}' -> '{formatted_phrase}'")

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Retry loop
    for attempt in range(max_retries + 1):
        try:
            # Create communicate object
            communicate = edge_tts.Communicate(formatted_phrase, voice)

            # Generate audio with timeout
            await asyncio.wait_for(
                communicate.save(str(output_path)),
                timeout=timeout
            )

            # Verify file was created and has content
            if output_path.exists() and output_path.stat().st_size > 0:
                logger.debug(f"Phrase audio generated successfully: {output_path.name}")
                return True
            else:
                logger.warning(f"Audio file created but empty: {output_path}")
                return False

        except asyncio.TimeoutError:
            logger.warning(
                f"Phrase audio generation timeout (attempt {attempt + 1}/{max_retries + 1}): "
                f"{phrase[:50]}..."
            )
            if attempt < max_retries:
                await asyncio.sleep(1)  # Brief delay before retry
                continue
            else:
                logger.error(f"Phrase audio generation failed after {max_retries + 1} attempts (timeout)")
                return False

        except Exception as e:
            logger.error(
                f"Phrase audio generation error (attempt {attempt + 1}/{max_retries + 1}): "
                f"{type(e).__name__}: {str(e)} - Phrase: {phrase[:50]}..."
            )
            if attempt < max_retries:
                await asyncio.sleep(1)
                continue
            else:
                logger.error(f"Phrase audio generation failed after {max_retries + 1} attempts: {e}")
                return False

    return False


async def generate_and_upload_phrase_audio(
    phrase: str,
    voice: str = "en-US-AvaMultilingualNeural",
    check_existing: bool = True
) -> Dict[str, Any]:
    """
    Generate audio for a phrase and upload to R2 and COS.

    This is the main function that:
    1. Generates phrase hash
    2. Checks if audio exists in R2/COS (optional)
    3. Generates audio file if needed
    4. Uploads to both R2 and COS

    Args:
        phrase: Phrase text to generate audio for
        voice: Edge TTS voice model
        check_existing: Whether to check if audio already exists before generating

    Returns:
        Dict with detailed results including upload status

    Examples:
        >>> import asyncio
        >>> result = asyncio.run(generate_and_upload_phrase_audio("break the ice"))
        >>> result['audio_generated']
        True
    """
    from services.storage_service import upload_audio_files

    # Validate phrase
    if not phrase or not phrase.strip():
        return {
            'phrase': phrase,
            'clean_filename': '',
            'formatted_for_tts': '',
            'audio_generated': False,
            'error': 'Empty phrase text'
        }

    phrase = phrase.strip()

    # Generate clean filename from phrase
    clean_filename = clean_phrase_filename(phrase)

    # Format for TTS
    formatted_for_tts = format_phrase_for_tts(phrase)

    # Create audio directory
    audio_dir = Path("audio/expressionss")
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Audio file path
    audio_filename = f"{clean_filename}.mp3"
    audio_path = audio_dir / audio_filename

    # Object key for cloud storage
    object_key = f"audio/expressionss/{clean_filename}.mp3"

    # Check if audio exists in R2/COS
    r2_existed = False
    cos_existed = False

    if check_existing:
        logger.info(f"Checking if phrase audio already exists in R2/COS: {phrase}")

        # Import check functions
        try:
            from utils.storage_check import check_audio_exists_in_storage

            r2_existed, cos_existed = await check_audio_exists_in_storage(object_key)

            logger.info(f"Phrase audio exists - R2: {r2_existed}, COS: {cos_existed}")

            # If exists in both, no need to generate or upload
            if r2_existed and cos_existed:
                logger.info(f"Phrase audio already exists in both R2 and COS, skipping generation")
                return {
                    'phrase': phrase,
                    'clean_filename': clean_filename,
                    'formatted_for_tts': formatted_for_tts,
                    'audio_generated': False,
                    'audio_existed': True,
                    'uploaded_r2': False,
                    'uploaded_cos': False,
                    'r2_existed': r2_existed,
                    'cos_existed': cos_existed,
                    'r2_object_key': object_key,
                    'cos_object_key': object_key,
                    'audio_file_path': None
                }
        except Exception as e:
            logger.warning(f"Failed to check existing audio: {e}, will proceed with generation")

    # Check if audio file already exists locally
    audio_existed_locally = False
    if audio_path.exists() and audio_path.stat().st_size > 0:
        logger.info(f"Phrase audio already exists locally: {audio_filename}")
        audio_existed_locally = True
        audio_generated = True
    else:
        # Generate audio file
        logger.info(f"Generating phrase audio: {phrase}")
        audio_generated = await generate_phrase_audio_async(
            phrase=phrase,
            output_path=audio_path,
            voice=voice,
            timeout=30
        )

        if not audio_generated:
            return {
                'phrase': phrase,
                'clean_filename': clean_filename,
                'formatted_for_tts': formatted_for_tts,
                'audio_generated': False,
                'error': 'Audio generation failed'
            }

    # Prepare for upload
    upload_files = [{
        'file_path': str(audio_path),
        'object_key': object_key,
        'sentence_hash': clean_filename  # Use clean filename instead of hash
    }]

    # Upload to R2 and COS
    logger.info(f"Uploading phrase audio to R2 and COS: {clean_filename}.mp3")

    cos_results, r2_results, cos_stats, r2_stats = await upload_audio_files(
        upload_files=upload_files,
        upload_to_cos=True,
        upload_to_r2=True,
        max_concurrent_r2=1,
        max_workers_cos=1
    )

    # Extract upload results
    uploaded_r2 = r2_stats.get('successful_uploads', 0) > 0
    uploaded_cos = cos_stats.get('successful_uploads', 0) > 0

    return {
        'phrase': phrase,
        'clean_filename': clean_filename,
        'formatted_for_tts': formatted_for_tts,
        'audio_generated': audio_generated,
        'audio_existed': audio_existed_locally,
        'uploaded_r2': uploaded_r2,
        'uploaded_cos': uploaded_cos,
        'r2_existed': r2_existed,
        'cos_existed': cos_existed,
        'r2_object_key': object_key if uploaded_r2 or r2_existed else None,
        'cos_object_key': object_key if uploaded_cos or cos_existed else None,
        'audio_file_path': str(audio_path) if audio_path.exists() else None
    }


def check_edge_tts_available() -> bool:
    """
    Check if edge-tts Python library is available.

    Returns:
        True if edge-tts is installed, False otherwise
    """
    return EDGE_TTS_AVAILABLE


__all__ = [
    'generate_phrase_audio_async',
    'generate_and_upload_phrase_audio',
    'check_edge_tts_available',
    'PhraseAudioGenerationError'
]
