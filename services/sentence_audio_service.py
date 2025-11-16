"""
Sentence audio generation service.

Service for generating audio files for individual sentences using Edge TTS.
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

logger = logging.getLogger(__name__)


class SentenceAudioServiceError(Exception):
    """Custom exception for sentence audio service errors"""
    pass


class SentenceAudioService:
    """
    Service for generating audio files from sentences.

    Uses Edge TTS to generate MP3 audio files for English sentences.
    """

    def __init__(self, voice: str = "en-US-AriaNeural", output_dir: str = "audio/sentences"):
        """
        Initialize the sentence audio service.

        Args:
            voice: Edge TTS voice to use (default: en-US-AriaNeural)
            output_dir: Directory to store generated audio files

        Raises:
            SentenceAudioServiceError: If Edge TTS is not available
        """
        if not EDGE_TTS_AVAILABLE:
            raise SentenceAudioServiceError(
                "edge-tts package is not installed. Install with: pip install edge-tts"
            )

        self.voice = voice
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized SentenceAudioService with voice: {voice}")

    def generate_sentence_hash(self, text: str, length: int = 8) -> str:
        """
        Generate a hash for a sentence text.

        Args:
            text: Sentence text to hash
            length: Length of the hash (default: 8)

        Returns:
            Hash string
        """
        return hashlib.md5(text.encode()).hexdigest()[:length]

    async def _generate_audio_async(self, text: str, output_path: Path) -> bool:
        """
        Generate audio file asynchronously using Edge TTS.

        Args:
            text: Text to convert to speech
            output_path: Path where to save the MP3 file

        Returns:
            True if successful, False otherwise
        """
        try:
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(str(output_path))
            return True
        except Exception as e:
            logger.error(f"Failed to generate audio: {e}")
            return False

    def generate_audio(self, text: str, output_path: Path) -> bool:
        """
        Generate audio file synchronously (wrapper around async method).

        Args:
            text: Text to convert to speech
            output_path: Path where to save the MP3 file

        Returns:
            True if successful, False otherwise
        """
        try:
            return asyncio.run(self._generate_audio_async(text, output_path))
        except Exception as e:
            logger.error(f"Error in generate_audio: {e}")
            return False

    def process_sentence(self, sentence_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single sentence: generate hash and audio file.

        Args:
            sentence_data: Dictionary containing sentence data with 'en' field

        Returns:
            Dictionary with processing results
        """
        sentence_text = sentence_data.get('en', '').strip()

        if not sentence_text:
            logger.warning("Empty sentence text, skipping")
            return {
                **sentence_data,
                'sentence_hash': '',
                'audio_generated': False,
                'error': 'Empty sentence text'
            }

        # Generate hash
        sentence_hash = self.generate_sentence_hash(sentence_text)

        # Create audio file path
        audio_filename = f"{sentence_hash}.mp3"
        audio_path = self.output_dir / audio_filename

        # Check if audio file already exists
        if audio_path.exists():
            logger.info(f"Audio already exists: {audio_filename}")
            return {
                **sentence_data,
                'sentence_hash': sentence_hash,
                'audio_path': str(audio_path),
                'audio_generated': True,
                'existed': True
            }

        # Generate new audio file
        logger.info(f"Generating audio for: {sentence_text[:50]}...")
        success = self.generate_audio(sentence_text, audio_path)

        if success:
            logger.info(f"✅ Generated: {audio_filename}")
            return {
                **sentence_data,
                'sentence_hash': sentence_hash,
                'audio_path': str(audio_path),
                'audio_generated': True,
                'existed': False
            }
        else:
            logger.warning(f"❌ Failed to generate audio for: {sentence_text[:30]}...")
            return {
                **sentence_data,
                'sentence_hash': sentence_hash,
                'audio_generated': False,
                'error': 'Audio generation failed'
            }

    def process_sentences(self, sentences: List[Dict[str, Any]], max_workers: int = 4) -> List[Dict[str, Any]]:
        """
        Process multiple sentences in parallel.

        Args:
            sentences: List of sentence dictionaries with 'en' field
            max_workers: Maximum number of parallel workers

        Returns:
            List of processed sentence dictionaries with audio info
        """
        if not sentences:
            logger.warning("No sentences to process")
            return []

        logger.info(f"Processing {len(sentences)} sentences with {max_workers} workers...")

        processed_sentences = []

        # Process in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.process_sentence, sentence): idx
                for idx, sentence in enumerate(sentences)
            }

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    result = future.result()
                    processed_sentences.append((idx, result))
                except Exception as e:
                    logger.error(f"Error processing sentence {idx}: {e}")
                    processed_sentences.append((idx, {
                        **sentences[idx],
                        'audio_generated': False,
                        'error': str(e)
                    }))

        # Sort by original index to maintain order
        processed_sentences.sort(key=lambda x: x[0])

        logger.info(f"✅ Processed {len(processed_sentences)} sentences")

        return [result for _, result in processed_sentences]

    def collect_audio_files(self, processed_sentences: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        Collect audio file paths for upload.

        Args:
            processed_sentences: List of processed sentence dictionaries

        Returns:
            List of dictionaries with file_path and object_key for upload
        """
        upload_tasks = []

        for sentence in processed_sentences:
            if not sentence.get('audio_generated', False):
                continue

            audio_path = sentence.get('audio_path', '')
            sentence_hash = sentence.get('sentence_hash', '')

            if not audio_path or not sentence_hash:
                continue

            if not Path(audio_path).exists():
                logger.warning(f"Audio file not found: {audio_path}")
                continue

            # Object key: audio/sentences/{hash}.mp3
            object_key = f"audio/sentences/{sentence_hash}.mp3"
            upload_tasks.append({
                'file_path': audio_path,
                'object_key': object_key,
                'sentence_hash': sentence_hash
            })

        logger.info(f"📁 Collected {len(upload_tasks)} audio files for upload")
        return upload_tasks

    def get_statistics(self, processed_sentences: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get processing statistics.

        Args:
            processed_sentences: List of processed sentence dictionaries

        Returns:
            Dictionary with statistics
        """
        total = len(processed_sentences)
        generated = sum(1 for s in processed_sentences if s.get('audio_generated', False))
        existed = sum(1 for s in processed_sentences if s.get('existed', False))
        failed = total - generated
        success_rate = generated / total if total > 0 else 0

        stats = {
            'total_sentences': total,
            'audio_generated': generated,
            'already_existed': existed,
            'newly_generated': generated - existed,
            'failed': failed,
            'success_rate': success_rate
        }

        logger.info(f"📊 Processing statistics: {stats}")
        return stats


__all__ = [
    'SentenceAudioService',
    'SentenceAudioServiceError'
]
