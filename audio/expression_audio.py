"""
Expression audio generation tasks.

Prefect tasks for generating audio files for extracted expressions.
Refactored to use flow-level .map() for proper parallel execution.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from prefect import task, get_run_logger

from tasks.utils.types import TranscriptProcessingError
from tasks.utils.text_helpers import clean_phrase_for_filename
from tasks.utils.audio_helpers import generate_audio_with_edge_tts


@task(name="Process Single Expression Audio", retries=1)
def process_single_expression_audio_task(
    highlight_slug: str,
    audio_dir: str,
    voice: str,
    generate_audio: bool = True
) -> str:
    """
    Process a single highlight slug for audio generation (Prefect parallel task).

    Args:
        highlight_slug: Slug from highlight_entries (e.g., 'take-out', 'awesome')
        audio_dir: Directory path for audio files
        voice: TTS voice model to use
        generate_audio: Whether to generate audio files

    Returns:
        Highlight slug (unchanged, for tracking)
    """
    logger = get_run_logger()

    if not highlight_slug:
        logger.warning("Empty slug, skipping audio generation")
        return highlight_slug

    if not generate_audio:
        return highlight_slug

    # Convert slug to phrase: 'take-out' -> 'take out'
    phrase = highlight_slug.replace('-', ' ')

    # Convert slug to filename: 'take-out' -> 'take_out.mp3'
    audio_filename = f"{highlight_slug.replace('-', '_')}.mp3"

    audio_dir_path = Path(audio_dir)
    audio_path = audio_dir_path / audio_filename

    # Check if audio file already exists
    if audio_path.exists():
        logger.info(f"Audio exists: {audio_filename}")
        return highlight_slug

    # Generate new audio file
    logger.info(f"Generating audio for: {phrase} -> {audio_filename}")

    success = generate_audio_with_edge_tts(
        phrase,
        audio_path,
        voice
    )

    if success:
        logger.info(f"✅ Generated: {audio_filename}")
    else:
        logger.warning(f"❌ Failed to generate audio for: {phrase}")

    return highlight_slug


@task(name="Extract Highlight Slugs from Sentences", retries=1)
def extract_highlight_slugs_from_sentences_task(sentences: List[Dict[str, Any]]) -> List[str]:
    """
    Extract unique highlight slugs from sentences data (in-memory).

    Args:
        sentences: List of sentence dictionaries with highlight_entries

    Returns:
        Sorted list of unique highlight slugs

    Raises:
        TranscriptProcessingError: If extraction fails
    """
    logger = get_run_logger()

    if not sentences:
        logger.warning("No sentences provided")
        return []

    try:
        # Extract unique highlight slugs from in-memory data
        highlight_slugs = set()
        for sentence in sentences:
            for entry in sentence.get('highlight_entries', []):
                slug = entry.get('slug', '').strip()
                if slug:
                    highlight_slugs.add(slug)

        slugs_list = sorted(highlight_slugs)
        logger.info(f"📚 Extracted {len(slugs_list)} unique highlight slugs from {len(sentences)} sentences")

        return slugs_list

    except Exception as e:
        logger.error(f"Failed to extract highlight slugs: {e}")
        raise TranscriptProcessingError(f"Highlight slug extraction failed: {e}")


@task(name="Extract Highlight Slugs from File", retries=1)
def extract_highlight_slugs_task(sentences_file_path: str) -> List[str]:
    """
    Extract unique highlight slugs from sentences file (for backward compatibility).

    Args:
        sentences_file_path: Path to sentences-with-audio.json file

    Returns:
        Sorted list of unique highlight slugs

    Raises:
        TranscriptProcessingError: If extraction fails
    """
    logger = get_run_logger()

    if not sentences_file_path or not Path(sentences_file_path).exists():
        logger.warning("Sentences file not found")
        return []

    try:
        with open(sentences_file_path, 'r', encoding='utf-8') as f:
            sentences = json.load(f)

        # Delegate to memory-based function
        return extract_highlight_slugs_from_sentences_task.fn(sentences)

    except Exception as e:
        logger.error(f"Failed to extract highlight slugs from file: {e}")
        raise TranscriptProcessingError(f"Highlight slug extraction failed: {e}")


@task(name="Setup Expression Audio Directory", retries=1)
def setup_expression_audio_dir_task(
    output_dir: str,
    video_id: str,
    generate_audio: bool
) -> str:
    """
    Setup expression audio directory.

    Args:
        output_dir: Base output directory
        video_id: Video ID
        generate_audio: Whether to create directory

    Returns:
        Path to expression audio directory
    """
    logger = get_run_logger()

    audio_dir = Path(output_dir) / video_id / "audio" / "expressions"

    if generate_audio:
        audio_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Expression audio directory: {audio_dir}")
    else:
        logger.info("📁 Expression audio generation disabled")

    return str(audio_dir)


@task(name="Collect Expression Audio Stats", retries=1)
def collect_expression_audio_stats_task(
    processed_slugs: List[str],
    audio_dir: str,
    generate_audio: bool
) -> Dict[str, Any]:
    """
    Collect statistics about expression audio generation.

    Args:
        processed_slugs: List of processed slugs (from .map() results)
        audio_dir: Audio directory path
        generate_audio: Whether audio was generated

    Returns:
        Statistics dictionary
    """
    logger = get_run_logger()

    # Count successful audio generations
    audio_generated = 0
    if generate_audio:
        audio_dir_path = Path(audio_dir)
        for slug in processed_slugs:
            audio_filename = f"{slug.replace('-', '_')}.mp3"
            audio_path = audio_dir_path / audio_filename
            if audio_path.exists():
                audio_generated += 1

    stats = {
        'total_highlights': len(processed_slugs),
        'unique_highlights': len(processed_slugs),
        'audio_generated': audio_generated,
        'audio_directory': audio_dir if generate_audio else None
    }

    if generate_audio:
        logger.info(f"✅ Expression audio generation completed:")
        logger.info(f"  - Unique highlights: {stats['unique_highlights']}")
        logger.info(f"  - Audio files generated: {stats['audio_generated']}")
        logger.info(f"  - Audio directory: {stats['audio_directory']}")
    else:
        logger.info(f"📝 Expression audio generation skipped (audio disabled)")

    return stats


__all__ = [
    'process_single_expression_audio_task',
    'extract_highlight_slugs_from_sentences_task',
    'extract_highlight_slugs_task',
    'setup_expression_audio_dir_task',
    'collect_expression_audio_stats_task',
]
