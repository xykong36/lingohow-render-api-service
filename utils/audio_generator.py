"""
Async audio generation using edge-tts Python API.

This module provides async functions for generating audio files from text
using Microsoft Edge TTS. It follows FastAPI best practices with proper
async/await, timeout handling, retry logic, and concurrency control.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
import time

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

logger = logging.getLogger(__name__)


class AudioGenerationError(Exception):
    """Custom exception for audio generation errors."""
    pass


async def generate_audio_async(
    text: str,
    output_path: Path,
    voice: str = "en-US-AvaMultilingualNeural",
    timeout: int = 30,
    max_retries: int = 2
) -> bool:
    """
    Generate audio file asynchronously using edge-tts Python API.

    This function uses the edge_tts library directly (not CLI) for better
    performance and error handling. It includes timeout and retry mechanisms.

    Args:
        text: Text to convert to speech
        output_path: Path where to save the MP3 file
        voice: Edge TTS voice model (default: en-US-AvaMultilingualNeural)
        timeout: Timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts (default: 2)

    Returns:
        True if successful, False otherwise

    Examples:
        >>> import asyncio
        >>> from pathlib import Path
        >>> output = Path("/tmp/test.mp3")
        >>> asyncio.run(generate_audio_async("Hello World", output))
        True
    """
    if not EDGE_TTS_AVAILABLE:
        logger.error("edge-tts library is not installed")
        return False

    if not text or not text.strip():
        logger.warning("Empty text provided, skipping audio generation")
        return False

    # Format text for better TTS
    from utils.text_helpers import format_text_for_tts
    formatted_text = format_text_for_tts(text)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Retry loop
    for attempt in range(max_retries + 1):
        try:
            # Create communicate object
            communicate = edge_tts.Communicate(formatted_text, voice)

            # Generate audio with timeout
            await asyncio.wait_for(
                communicate.save(str(output_path)),
                timeout=timeout
            )

            # Verify file was created and has content
            if output_path.exists() and output_path.stat().st_size > 0:
                logger.debug(f"Audio generated successfully: {output_path.name}")
                return True
            else:
                logger.warning(f"Audio file created but empty: {output_path}")
                return False

        except asyncio.TimeoutError:
            logger.warning(
                f"Audio generation timeout (attempt {attempt + 1}/{max_retries + 1}): "
                f"{text[:50]}..."
            )
            if attempt < max_retries:
                await asyncio.sleep(1)  # Brief delay before retry
                continue
            else:
                logger.error(f"Audio generation failed after {max_retries + 1} attempts (timeout)")
                return False

        except Exception as e:
            logger.error(
                f"Audio generation error (attempt {attempt + 1}/{max_retries + 1}): "
                f"{type(e).__name__}: {str(e)} - Text: {text[:50]}..."
            )
            if attempt < max_retries:
                await asyncio.sleep(1)
                continue
            else:
                logger.error(f"Audio generation failed after {max_retries + 1} attempts: {e}")
                return False

    return False


async def generate_batch_audio(
    sentences: List[str],
    audio_dir: Path,
    voice: str = "en-US-AvaMultilingualNeural",
    max_concurrent: int = 5,
    timeout_per_sentence: int = 30
) -> List[Dict[str, Any]]:
    """
    Generate audio files for multiple sentences concurrently with rate limiting.

    Uses asyncio.Semaphore to limit concurrent operations and prevent
    overwhelming the TTS service or system resources.

    Args:
        sentences: List of sentence texts
        audio_dir: Directory to save audio files
        voice: Edge TTS voice model
        max_concurrent: Maximum concurrent audio generations (default: 5)
        timeout_per_sentence: Timeout per sentence in seconds (default: 30)

    Returns:
        List of result dictionaries with generation status

    Examples:
        >>> import asyncio
        >>> from pathlib import Path
        >>> sentences = ["Hello", "World"]
        >>> audio_dir = Path("/tmp/audio")
        >>> results = asyncio.run(generate_batch_audio(sentences, audio_dir))
        >>> len(results)
        2
    """
    if not EDGE_TTS_AVAILABLE:
        raise AudioGenerationError("edge-tts library is not installed")

    from utils.text_helpers import hash_text

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_single_sentence(idx: int, sentence_text: str) -> Dict[str, Any]:
        """Process a single sentence with semaphore control."""
        async with semaphore:
            sentence_text = sentence_text.strip()

            if not sentence_text:
                logger.warning(f"Sentence {idx}: Empty text, skipping")
                return {
                    'index': idx,
                    'en': '',
                    'sentence_hash': '',
                    'audio_path': None,
                    'audio_generated': False,
                    'error': 'Empty sentence text'
                }

            # Generate hash
            sentence_hash = hash_text(sentence_text, length=8)

            # Create audio file path
            audio_filename = f"{sentence_hash}.mp3"
            audio_path = audio_dir / audio_filename

            # Check if audio file already exists
            if audio_path.exists() and audio_path.stat().st_size > 0:
                logger.info(f"Sentence {idx}: Audio already exists - {audio_filename}")
                return {
                    'index': idx,
                    'en': sentence_text,
                    'sentence_hash': sentence_hash,
                    'audio_path': str(audio_path),
                    'audio_generated': True,
                    'existed': True
                }

            # Generate new audio file
            logger.info(f"Sentence {idx}: Generating audio for: {sentence_text[:50]}...")
            start_time = time.time()

            success = await generate_audio_async(
                sentence_text,
                audio_path,
                voice,
                timeout=timeout_per_sentence
            )

            elapsed = time.time() - start_time

            if success:
                logger.info(
                    f"Sentence {idx}: ✅ Generated - {audio_filename} "
                    f"({elapsed:.2f}s)"
                )
                return {
                    'index': idx,
                    'en': sentence_text,
                    'sentence_hash': sentence_hash,
                    'audio_path': str(audio_path),
                    'audio_generated': True,
                    'existed': False,
                    'generation_time': elapsed
                }
            else:
                logger.warning(
                    f"Sentence {idx}: ❌ Failed to generate audio "
                    f"({elapsed:.2f}s)"
                )
                return {
                    'index': idx,
                    'en': sentence_text,
                    'sentence_hash': sentence_hash,
                    'audio_path': None,
                    'audio_generated': False,
                    'error': 'Audio generation failed',
                    'generation_time': elapsed
                }

    # Create tasks for all sentences
    tasks = [
        process_single_sentence(idx, sentence)
        for idx, sentence in enumerate(sentences)
    ]

    # Execute all tasks concurrently
    logger.info(
        f"Starting batch audio generation: {len(sentences)} sentences, "
        f"max {max_concurrent} concurrent"
    )
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions from gather
    processed_results = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Sentence {idx}: Exception during processing: {result}")
            processed_results.append({
                'index': idx,
                'en': sentences[idx] if idx < len(sentences) else '',
                'sentence_hash': '',
                'audio_generated': False,
                'error': str(result)
            })
        else:
            processed_results.append(result)

    # Sort by original index
    processed_results.sort(key=lambda x: x['index'])

    # Calculate statistics
    total = len(processed_results)
    generated = sum(1 for r in processed_results if r.get('audio_generated', False))
    existed = sum(1 for r in processed_results if r.get('existed', False))
    failed = total - generated

    logger.info(
        f"✅ Batch audio generation completed: {generated}/{total} successful "
        f"({existed} existed, {generated - existed} newly generated, {failed} failed)"
    )

    return processed_results


def check_edge_tts_available() -> bool:
    """
    Check if edge-tts Python library is available.

    Returns:
        True if edge-tts is installed, False otherwise

    Examples:
        >>> check_edge_tts_available()
        True  # if edge-tts is installed
    """
    return EDGE_TTS_AVAILABLE


__all__ = [
    'generate_audio_async',
    'generate_batch_audio',
    'check_edge_tts_available',
    'AudioGenerationError'
]
