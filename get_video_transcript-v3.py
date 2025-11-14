#!/usr/bin/env python3
"""
YouTube Video Transcript Fetcher v3.1.0

Updated script using youtube-transcript-api 1.2.2 with the new fetch() method.
Fetches YouTube video transcripts and saves them in a single JSON file:
- Timestamped format with full_transcript field for the complete text

Features:
- Uses latest youtube-transcript-api 1.2.2 fetch() method
- Single JSON output with both timestamped data and full transcript
- Enhanced error handling and logging
- Batch processing support
- Extended metadata inclusion (language, language_code, is_generated)
- Progress tracking

Usage:
    python get_video_transcript.py video_id
    python get_video_transcript.py --file video_ids.txt
    
Author: Assistant
Date: 2025-08-12
Version: 3.1.0
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable
    )
    TRANSCRIPT_API_AVAILABLE = True
except ImportError:
    TRANSCRIPT_API_AVAILABLE = False
    print("Warning: youtube_transcript_api not installed.")
    print("Install with: pip install youtube-transcript-api==1.2.2")


class YouTubeTranscriptFetcher:
    """YouTube transcript fetcher using the latest API v1.2.2."""

    def __init__(self) -> None:
        """Initialize the transcript fetcher."""
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # Initialize the API client
        if TRANSCRIPT_API_AVAILABLE:
            self.ytt_api = YouTubeTranscriptApi()
        else:
            self.ytt_api = None

    def get_single_transcript(self, video_id: str) -> Optional[Tuple[List[Dict[str, Any]], Dict[str, Any]]]:
        """
        Fetch transcript for a single YouTube video using the new fetch() method.

        Args:
            video_id: YouTube video ID

        Returns:
            Tuple of (transcript_list, transcript_metadata) or None if failed
        """
        if not TRANSCRIPT_API_AVAILABLE or not self.ytt_api:
            self.logger.error("youtube_transcript_api not available")
            return None

        if not video_id or not isinstance(video_id, str):
            raise ValueError("video_id must be a non-empty string")

        self.logger.info(f"Fetching transcript for video ID: {video_id}")

        try:
            # Use the new fetch() method from API v1.2.2
            fetched_transcript = self.ytt_api.fetch(video_id)

            # Extract metadata from FetchedTranscript
            language = getattr(fetched_transcript, 'language', 'Unknown')
            language_code = getattr(fetched_transcript, 'language_code', 'N/A')
            is_generated = getattr(fetched_transcript, 'is_generated', False)

            # Create metadata dictionary
            transcript_metadata = {
                'language': language,
                'language_code': language_code,
                'is_generated': is_generated
            }

            # Convert FetchedTranscript to list of dictionaries using to_raw_data()
            transcript_list = fetched_transcript.to_raw_data()

            self.logger.info(
                f"Successfully fetched transcript with {len(transcript_list)} entries "
                f"(Language: {language}, Code: {language_code}, Generated: {is_generated})"
            )
            return transcript_list, transcript_metadata

        except TranscriptsDisabled:
            self.logger.error(f"Transcripts are disabled for video {video_id}")
            return None

        except NoTranscriptFound:
            self.logger.error(f"No transcript found for video {video_id}")
            return None

        except VideoUnavailable:
            self.logger.error(f"Video {video_id} is unavailable")
            return None

        except Exception as e:
            self.logger.error(f"Unexpected error fetching transcript: {e}")
            return None

    def process_transcript_data(self,
                                transcript_list: List[Dict[str, Any]],
                                transcript_metadata: Dict[str, Any],
                                video_id: str,
                                title: str = None) -> Dict[str, Any]:
        """
        Process transcript data into a single format with both timestamped and full transcript.

        Args:
            transcript_list: Raw transcript data from API
            transcript_metadata: Metadata from FetchedTranscript object
            video_id: YouTube video ID
            title: Video title (optional)

        Returns:
            Dictionary with timestamped data and full_transcript field
        """
        if not title:
            title = f"Video-{video_id}"

        # Calculate full transcript text
        full_text = " ".join(
            segment.get("text", "").strip()
            for segment in transcript_list
            if segment.get("text", "").strip()
        )

        # Base metadata
        base_metadata = {
            'total_segments': len(transcript_list),
            'fetch_timestamp': datetime.now().isoformat(),
            'api_version': '1.2.2',
            'language': transcript_metadata.get('language', 'Unknown'),
            'language_code': transcript_metadata.get('language_code', 'N/A'),
            'is_generated': transcript_metadata.get('is_generated', False),
            'character_count': len(full_text),
            'word_count': len(full_text.split()) if full_text else 0
        }

        # Calculate total duration
        if transcript_list:
            last_segment = transcript_list[-1]
            total_duration = last_segment.get('start', 0) + last_segment.get('duration', 0)
            base_metadata['total_duration_seconds'] = round(total_duration, 2)
            base_metadata['total_duration_formatted'] = self._format_duration(total_duration)

        # Combined format
        return {
            'video_id': video_id,
            'title': title,
            'video_url': f"https://www.youtube.com/watch?v={video_id}",
            'transcript': transcript_list,
            'full_transcript': full_text,
            'metadata': base_metadata
        }

    def save_transcript(self,
                        video_id: str,
                        title: str = None,
                        output_dir: str = "transcripts") -> Tuple[bool, str]:
        """
        Download and save transcript for a single video.

        Args:
            video_id: YouTube video ID
            title: Video title (optional)
            output_dir: Directory to save transcript files

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not TRANSCRIPT_API_AVAILABLE:
            return False, "youtube_transcript_api not available"

        # Create output directory
        Path(output_dir).mkdir(exist_ok=True)

        if not title:
            title = f"Video-{video_id}"

        try:
            # Fetch transcript using new API
            transcript_result = self.get_single_transcript(video_id)

            if not transcript_result:
                return False, "Failed to fetch transcript"

            transcript_list, transcript_metadata = transcript_result

            # Process into combined format
            transcript_data = self.process_transcript_data(
                transcript_list, transcript_metadata, video_id, title
            )

            # Save transcript: [videoid]-timestamp-transcript.json
            filename = f"{video_id}-transcript.json"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(transcript_data, f, indent=2, ensure_ascii=False)

            # Enhanced success message with metadata
            language_info = f"{transcript_metadata.get('language', 'Unknown')} ({transcript_metadata.get('language_code', 'N/A')})"
            generated_info = "Auto-generated" if transcript_metadata.get('is_generated', False) else "Manual"

            self.logger.info(f"✅ Saved transcript to: {filepath}")
            self.logger.info(f"📊 Language: {language_info}, Type: {generated_info}")

            success_message = f"Successfully processed {len(transcript_list)} segments ({language_info}, {generated_info})"
            return True, success_message

        except Exception as e:
            error_msg = f"Error processing video {video_id}: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    def batch_process(self,
                      video_data: List[Dict[str, str]],
                      output_dir: str = "transcripts") -> Dict[str, Any]:
        """
        Process multiple videos and save transcripts.

        Args:
            video_data: List of dictionaries with 'video_id' and 'title' keys
            output_dir: Directory to save transcript files

        Returns:
            Dictionary with processing results and statistics
        """
        if not TRANSCRIPT_API_AVAILABLE:
            return {
                'success': False,
                'error': 'youtube_transcript_api not available',
                'results': {}
            }

        # Create output directory
        Path(output_dir).mkdir(exist_ok=True)

        total_videos = len(video_data)
        results = {}
        successful = 0
        failed = 0
        language_stats = {}

        self.logger.info(f"Processing {total_videos} videos...")

        for i, video_info in enumerate(video_data, 1):
            video_id = video_info.get('video_id')
            title = video_info.get('title', f"Video-{video_id}")

            self.logger.info(f"[{i}/{total_videos}] Processing: {title}")

            try:
                success, message = self.save_transcript(
                    video_id, title, output_dir)

                # Track language statistics for batch processing
                if success:
                    # Extract language info from the success message
                    try:
                        transcript_result = self.get_single_transcript(
                            video_id)
                        if transcript_result:
                            _, transcript_metadata = transcript_result
                            lang = transcript_metadata.get(
                                'language', 'Unknown')
                            language_stats[lang] = language_stats.get(
                                lang, 0) + 1
                    except:
                        pass  # Don't fail batch processing due to stats collection

                results[video_id] = {
                    'success': success,
                    'message': message,
                    'title': title,
                    'processed_at': datetime.now().isoformat()
                }

                if success:
                    successful += 1
                    self.logger.info(f"✅ Success: {message}")
                else:
                    failed += 1
                    self.logger.warning(f"❌ Failed: {message}")

            except Exception as e:
                error_msg = str(e)
                results[video_id] = {
                    'success': False,
                    'message': error_msg,
                    'title': title,
                    'processed_at': datetime.now().isoformat()
                }
                failed += 1
                self.logger.error(f"❌ Error processing {title}: {error_msg}")

            # Brief pause between requests to be respectful
            if i < total_videos:
                time.sleep(0.5)

        # Print summary with language statistics
        print("\n" + "="*60)
        print("📊 BATCH PROCESSING SUMMARY")
        print("="*60)
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"📈 Success rate: {successful/total_videos*100:.1f}%")
        print(f"📁 Output directory: {output_dir}")

        if language_stats:
            print("\n🌍 Language Distribution:")
            for lang, count in sorted(language_stats.items()):
                print(f"  - {lang}: {count} video{'s' if count != 1 else ''}")

        return {
            'success': True,
            'total_processed': total_videos,
            'successful': successful,
            'failed': failed,
            'success_rate': successful/total_videos*100,
            'output_directory': output_dir,
            'language_stats': language_stats,
            'results': results
        }

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to HH:MM:SS format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"


def extract_video_id_from_url(text: str) -> Optional[str]:
    """Extract video ID from YouTube URL or return the text if it's already a video ID."""
    text = text.strip()

    # If it's already a video ID (11 characters, alphanumeric + - and _)
    if len(text) == 11 and text.replace('-', '').replace('_', '').isalnum():
        return text

    # Extract from various YouTube URL formats
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/.*[?&]v=([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return None


def parse_video_ids_from_file(filepath: str) -> List[Dict[str, str]]:
    """
    Parse video IDs from a text file and return as list of dictionaries.

    Args:
        filepath: Path to the file containing video IDs

    Returns:
        List of dictionaries with 'video_id' and 'title' keys
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        video_data = []
        for line_num, line in enumerate(lines, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Extract video ID
            video_id = extract_video_id_from_url(line)
            if video_id:
                video_data.append({
                    'video_id': video_id,
                    'title': f"Video-{video_id}"  # Default title
                })
            else:
                print(f"Warning: Invalid video ID at line {line_num}: {line}")

        if not video_data:
            raise ValueError("No valid video IDs found in the file")

        return video_data

    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {filepath}")
    except Exception as e:
        raise ValueError(f"Error parsing file {filepath}: {e}")


def setup_argument_parser() -> argparse.ArgumentParser:
    """Setup command line argument parser."""
    parser = argparse.ArgumentParser(
        description="YouTube Transcript Fetcher v3.1.0 - Using API v1.2.2 with Extended Metadata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single video
  python get_video_transcript.py rKMAKbsOgfM
  
  # Multiple videos from file
  python get_video_transcript.py --file video_ids.txt
  
  # Custom output directory
  python get_video_transcript.py --file videos.txt --output-dir results

Output files:
  - [videoid]-timestamp-transcript.json (with timing info and full_transcript field)
        """
    )

    # Positional argument for single video ID
    parser.add_argument(
        'video_id',
        nargs='?',
        help='Single YouTube video ID or URL'
    )

    # File input option
    parser.add_argument(
        '-f', '--file',
        type=str,
        help='Path to file containing video IDs (one per line)'
    )

    # Output directory
    parser.add_argument(
        '-o', '--output-dir',
        type=str,
        default='transcripts',
        help='Output directory for transcript files (default: transcripts)'
    )

    # Verbose logging
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    return parser


def main() -> None:
    """Main function with command line interface."""
    parser = setup_argument_parser()
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Check if API is available
    if not TRANSCRIPT_API_AVAILABLE:
        print("❌ Error: youtube_transcript_api not installed")
        print("Install with: pip install youtube-transcript-api==1.2.2")
        sys.exit(1)

    # Validate arguments
    if not args.video_id and not args.file:
        parser.error("Must provide either a video ID or a file with --file")

    if args.video_id and args.file:
        parser.error("Cannot use both video ID and file input simultaneously")

    # Initialize fetcher
    fetcher = YouTubeTranscriptFetcher()

    # Process single video or batch
    try:
        if args.video_id:
            # Single video processing
            video_id = extract_video_id_from_url(args.video_id)
            if not video_id:
                print(f"❌ Invalid video ID or URL: {args.video_id}")
                sys.exit(1)

            print(f"📹 Processing single video: {video_id}")
            success, message = fetcher.save_transcript(
                video_id, output_dir=args.output_dir)

            if success:
                print(f"🎉 Success: {message}")
            else:
                print(f"❌ Failed: {message}")
                sys.exit(1)

        else:
            # Batch processing
            print(f"📁 Reading video IDs from: {args.file}")
            video_data = parse_video_ids_from_file(args.file)
            print(f"📊 Found {len(video_data)} video IDs")

            result = fetcher.batch_process(video_data, args.output_dir)

            if result['success'] and result['successful'] > 0:
                print("\n🎉 Batch processing completed!")
            elif result['successful'] == 0:
                print("\n❌ No videos were processed successfully")
                sys.exit(1)

    except (FileNotFoundError, ValueError) as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
