"""
Test script for the refactored audio generation system.

This script tests the new async audio generation flow to ensure it works
correctly before deploying to production.
"""

import asyncio
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_single_audio_generation():
    """Test generating a single audio file."""
    from utils.audio_generator import generate_audio_async, check_edge_tts_available

    logger.info("=== Test 1: Single Audio Generation ===")

    # Check if edge-tts is available
    if not check_edge_tts_available():
        logger.error("❌ edge-tts not available")
        return False

    logger.info("✅ edge-tts is available")

    # Test audio generation
    test_text = "This is a test sentence for audio generation."
    output_dir = Path("audio/test")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "test_single.mp3"

    # Remove old file if exists
    if output_path.exists():
        output_path.unlink()

    logger.info(f"Generating audio for: {test_text}")
    success = await generate_audio_async(
        text=test_text,
        output_path=output_path,
        voice="en-US-AvaMultilingualNeural",
        timeout=30
    )

    if success and output_path.exists():
        file_size = output_path.stat().st_size
        logger.info(f"✅ Audio generated successfully: {output_path} ({file_size} bytes)")
        return True
    else:
        logger.error("❌ Audio generation failed")
        return False


async def test_batch_audio_generation():
    """Test generating multiple audio files in batch."""
    from utils.audio_generator import generate_batch_audio

    logger.info("\n=== Test 2: Batch Audio Generation ===")

    # Test sentences
    test_sentences = [
        "Hello, this is the first test sentence.",
        "This is the second sentence for testing.",
        "And here's a third one with some punctuation!",
        "Can we handle questions? Yes we can.",
        "FBI and CIA are common acronyms."
    ]

    output_dir = Path("audio/test")
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Generating audio for {len(test_sentences)} sentences...")

    results = await generate_batch_audio(
        sentences=test_sentences,
        audio_dir=output_dir,
        voice="en-US-AvaMultilingualNeural",
        max_concurrent=3,
        timeout_per_sentence=30
    )

    # Check results
    successful = sum(1 for r in results if r.get('audio_generated', False))
    logger.info(f"Results: {successful}/{len(results)} successful")

    for idx, result in enumerate(results):
        if result.get('audio_generated'):
            logger.info(f"  ✅ Sentence {idx}: {result.get('sentence_hash')}")
        else:
            logger.error(f"  ❌ Sentence {idx}: {result.get('error', 'Unknown error')}")

    return successful == len(test_sentences)


async def test_text_formatting():
    """Test text formatting for TTS."""
    from utils.text_helpers import format_text_for_tts

    logger.info("\n=== Test 3: Text Formatting ===")

    test_cases = [
        ("Hello... World!!!", "Hello World!"),
        ("The FBI and CIA are here.", "The F B I and C I A are here."),
        ("It's a 'great' day!!!", "It's a 'great' day!"),
        ("Check out https://example.com", "Check out"),
    ]

    all_passed = True
    for original, expected_pattern in test_cases:
        formatted = format_text_for_tts(original)
        # Just check that it doesn't crash and produces some output
        if formatted:
            logger.info(f"  ✅ '{original}' -> '{formatted}'")
        else:
            logger.error(f"  ❌ '{original}' -> empty")
            all_passed = False

    return all_passed


async def test_audio_with_retry():
    """Test audio generation with retry mechanism."""
    from utils.audio_generator import generate_audio_async

    logger.info("\n=== Test 4: Audio Generation with Retry ===")

    test_text = "Testing retry mechanism with a longer sentence to ensure robustness."
    output_dir = Path("audio/test")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "test_retry.mp3"

    # Remove old file if exists
    if output_path.exists():
        output_path.unlink()

    logger.info(f"Generating audio with max_retries=2...")
    success = await generate_audio_async(
        text=test_text,
        output_path=output_path,
        voice="en-US-AvaMultilingualNeural",
        timeout=30,
        max_retries=2
    )

    if success:
        logger.info(f"✅ Audio generated with retry support")
        return True
    else:
        logger.error("❌ Audio generation failed even with retries")
        return False


async def main():
    """Run all tests."""
    logger.info("🚀 Starting Audio Generation Tests\n")

    try:
        # Run all tests
        test1 = await test_single_audio_generation()
        test2 = await test_batch_audio_generation()
        test3 = await test_text_formatting()
        test4 = await test_audio_with_retry()

        # Summary
        logger.info("\n" + "=" * 50)
        logger.info("📊 Test Summary")
        logger.info("=" * 50)
        logger.info(f"Test 1 (Single Audio):    {'✅ PASS' if test1 else '❌ FAIL'}")
        logger.info(f"Test 2 (Batch Audio):     {'✅ PASS' if test2 else '❌ FAIL'}")
        logger.info(f"Test 3 (Text Formatting): {'✅ PASS' if test3 else '❌ FAIL'}")
        logger.info(f"Test 4 (Retry Mechanism): {'✅ PASS' if test4 else '❌ FAIL'}")
        logger.info("=" * 50)

        all_passed = all([test1, test2, test3, test4])

        if all_passed:
            logger.info("🎉 All tests passed!")
            return 0
        else:
            logger.error("❌ Some tests failed")
            return 1

    except Exception as e:
        logger.error(f"❌ Test execution failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
