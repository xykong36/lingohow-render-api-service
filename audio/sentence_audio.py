"""
Sentence audio generation tasks.

Prefect tasks for generating audio files for individual sentences.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from prefect import task, get_run_logger

from tasks.utils.types import MongoJSONEncoder, TranscriptProcessingError
from tasks.utils.text_helpers import hash_text
from tasks.utils.audio_helpers import generate_audio_with_edge_tts


@task(name="Setup Audio Environment", retries=1)
def setup_audio_environment_task(output_dir: str, video_id: str, generate_audio: bool) -> str:
    """
    Setup audio generation environment for sentences (in video ID subfolder).

    Args:
        output_dir: Base output directory
        video_id: YouTube video ID for subfolder
        generate_audio: Whether to create audio directory

    Returns:
        Path to sentence audio directory (audio/sentences)
    """
    logger = get_run_logger()

    # Create sentence audio directory inside video ID subfolder
    audio_dir = Path(output_dir) / video_id / "audio" / "sentences"

    if generate_audio:
        audio_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Sentence audio directory created: {audio_dir}")
    else:
        logger.info("📁 Audio generation disabled, no directory created")

    return str(audio_dir)


@task(name="Process Single Sentence Audio", retries=1)
def process_single_sentence_audio_task(
    sentence_data: Dict[str, Any],
    audio_dir: str,
    voice: str,
    generate_audio: bool = True
) -> Dict[str, Any]:
    """
    Process a single sentence for audio generation (Prefect parallel task).

    Args:
        sentence_data: Single sentence dictionary with 'en', 'start_ts', 'end_ts'
        audio_dir: Directory path for audio files
        voice: TTS voice model to use
        generate_audio: Whether to generate audio files

    Returns:
        Enhanced sentence data with sentence_hash
    """
    logger = get_run_logger()

    sentence_text = sentence_data.get('en', '').strip()

    if not sentence_text:
        logger.warning("Empty sentence text, skipping")
        return {
            **sentence_data,
            'sentence_hash': ""
        }

    # Generate hash for the sentence
    sentence_hash = hash_text(sentence_text, length=8)

    # Create enhanced sentence data
    enhanced_sentence = {
        **sentence_data,
        'sentence_hash': sentence_hash
    }

    if generate_audio:
        audio_dir_path = Path(audio_dir)
        audio_filename = f"{sentence_hash}.mp3"
        audio_path = audio_dir_path / audio_filename

        # Check if audio file already exists
        if audio_path.exists():
            logger.info(f"Audio exists: {audio_filename}")
        else:
            # Generate new audio file
            logger.info(f"Generating: {sentence_text[:50]}...")

            success = generate_audio_with_edge_tts(
                sentence_text,
                audio_path,
                voice
            )

            if success:
                logger.info(f"✅ Generated: {audio_filename}")
            else:
                logger.warning(f"❌ Failed: {sentence_text[:30]}...")

    return enhanced_sentence


@task(name="Collect Audio Statistics", retries=1)
def collect_audio_stats_task(
    enhanced_sentences: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Collect statistics from processed sentences.

    Args:
        enhanced_sentences: List of processed sentence dictionaries

    Returns:
        Dictionary with processing statistics
    """
    logger = get_run_logger()

    total = len(enhanced_sentences)
    with_hash = sum(1 for s in enhanced_sentences if s.get('sentence_hash'))
    failed = total - with_hash
    success_rate = with_hash / total if total > 0 else 0

    stats = {
        'total_sentences': total,
        'successful_audio': with_hash,
        'failed_audio': failed,
        'success_rate': success_rate
    }

    logger.info(f"📊 Processing statistics: {stats}")
    return stats


@task(name="Save Enhanced Sentences", retries=2)
def save_enhanced_sentences_task(
    enhanced_sentences: List[Dict[str, Any]],
    video_id: str,
    output_dir: str
) -> str:
    """
    Save enhanced sentences to JSON file (in video ID subfolder).

    Args:
        enhanced_sentences: List of processed sentence dictionaries
        video_id: YouTube video ID for filename
        output_dir: Base directory (video ID subfolder will be created)

    Returns:
        Path to the saved file

    Raises:
        TranscriptProcessingError: If file cannot be saved
    """
    logger = get_run_logger()

    # Create video ID subfolder
    video_dir = Path(output_dir) / video_id
    video_dir.mkdir(parents=True, exist_ok=True)

    enhanced_filename = f"{video_id}-sentences-with-audio.json"
    enhanced_file_path = video_dir / enhanced_filename

    try:
        with open(enhanced_file_path, 'w', encoding='utf-8') as f:
            json.dump(enhanced_sentences, f, ensure_ascii=False, indent=2, cls=MongoJSONEncoder)

        logger.info(f"💾 Saved enhanced sentences to: {enhanced_file_path}")
        return str(enhanced_file_path)

    except Exception as e:
        error_msg = f"Error saving enhanced sentences file: {e}"
        logger.error(error_msg)
        raise TranscriptProcessingError(error_msg)


__all__ = [
    'setup_audio_environment_task',
    'process_single_sentence_audio_task',
    'collect_audio_stats_task',
    'save_enhanced_sentences_task',
]
