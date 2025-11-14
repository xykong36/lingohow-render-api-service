"""
YouTube Transcript Service

Service for fetching YouTube video transcripts using youtube-transcript-api.
Based on the logic from get_video_transcript-v3.py.
Includes R2 upload functionality for storing transcript JSON files.
"""

import json
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import boto3
from botocore.exceptions import ClientError, BotoCoreError

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


class TranscriptServiceError(Exception):
    """Base exception for transcript service errors."""
    pass


class TranscriptNotAvailableError(TranscriptServiceError):
    """Raised when transcript is not available for a video."""
    pass


class InvalidVideoIdError(TranscriptServiceError):
    """Raised when video ID is invalid."""
    pass


class TranscriptService:
    """YouTube transcript fetching service with R2 storage integration."""

    def __init__(self) -> None:
        """Initialize the transcript service."""
        self.logger = logging.getLogger(__name__)

        if not TRANSCRIPT_API_AVAILABLE:
            raise RuntimeError("youtube_transcript_api not available. Install with: pip install youtube-transcript-api==1.2.2")

        self.ytt_api = YouTubeTranscriptApi()

        # Load R2 configuration
        self.r2_config = self._load_r2_config()

        self.logger.info("TranscriptService initialized")

    def _load_r2_config(self) -> Optional[Dict[str, str]]:
        """
        Load R2 configuration from environment variables.

        Returns:
            Dictionary with R2 config or None if not configured
        """
        required_vars = [
            'R2_TRANSCRIPT_BUCKET_NAME',
            'R2_ACCESS_KEY_ID',
            'R2_SECRET_ACCESS_KEY',
            'R2_ENDPOINT_URL'
        ]

        optional_vars = ['R2_ACCOUNT_ID']

        config = {}
        missing_vars = []

        for var in required_vars:
            value = os.getenv(var)
            if not value:
                missing_vars.append(var)
            else:
                config[var] = value

        if missing_vars:
            self.logger.warning(
                f"R2 upload disabled. Missing environment variables: {', '.join(missing_vars)}"
            )
            return None

        # Load optional variables
        for var in optional_vars:
            value = os.getenv(var)
            if value:
                config[var] = value

        self.logger.info(f"R2 configuration loaded. Bucket: {config['R2_TRANSCRIPT_BUCKET_NAME']}")
        return config

    def _create_r2_client(self) -> Optional[boto3.client]:
        """
        Create boto3 S3 client configured for Cloudflare R2.

        Returns:
            Configured boto3 S3 client or None if R2 not configured
        """
        if not self.r2_config:
            return None

        try:
            s3_client = boto3.client(
                service_name='s3',
                endpoint_url=self.r2_config['R2_ENDPOINT_URL'],
                aws_access_key_id=self.r2_config['R2_ACCESS_KEY_ID'],
                aws_secret_access_key=self.r2_config['R2_SECRET_ACCESS_KEY'],
                region_name='auto'
            )
            return s3_client
        except Exception as e:
            self.logger.error(f"Failed to create R2 client: {e}")
            return None

    def _upload_to_r2(self, transcript_data: Dict[str, Any], video_id: str) -> Optional[str]:
        """
        Upload transcript JSON to R2 storage.

        Args:
            transcript_data: Complete transcript data dictionary
            video_id: YouTube video ID

        Returns:
            R2 object key if successful, None otherwise
        """
        if not self.r2_config:
            self.logger.warning("R2 upload skipped: R2 not configured")
            return None

        s3_client = self._create_r2_client()
        if not s3_client:
            self.logger.warning("R2 upload skipped: Failed to create R2 client")
            return None

        # Create temporary JSON file
        temp_file = None
        try:
            # Generate filename and object key
            filename = f"{video_id}-transcript.json"
            object_key = f"transcripts/{filename}"

            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                json.dump(transcript_data, f, indent=2, ensure_ascii=False)
                temp_file = f.name

            # Upload to R2
            bucket_name = self.r2_config['R2_TRANSCRIPT_BUCKET_NAME']

            s3_client.upload_file(
                Filename=temp_file,
                Bucket=bucket_name,
                Key=object_key,
                ExtraArgs={
                    'ContentType': 'application/json',
                    'CacheControl': 'public, max-age=3600'
                }
            )

            self.logger.info(f"✅ Uploaded transcript to R2: {object_key}")
            return object_key

        except (ClientError, BotoCoreError) as e:
            self.logger.error(f"R2 upload error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during R2 upload: {e}")
            return None
        finally:
            # Clean up temporary file
            if temp_file and Path(temp_file).exists():
                try:
                    Path(temp_file).unlink()
                except Exception as e:
                    self.logger.warning(f"Failed to delete temp file {temp_file}: {e}")

    def extract_video_id(self, text: str) -> Optional[str]:
        """
        Extract video ID from YouTube URL or return the text if it's already a video ID.

        Args:
            text: YouTube URL or video ID

        Returns:
            Video ID or None if invalid
        """
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

    def get_transcript(
        self,
        video_id: str,
        title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch transcript for a YouTube video.

        Args:
            video_id: YouTube video ID
            title: Optional video title

        Returns:
            Dictionary with transcript data matching VideoTranscriptResponse schema

        Raises:
            InvalidVideoIdError: If video ID is invalid
            TranscriptNotAvailableError: If transcript is not available
        """
        if not video_id or not isinstance(video_id, str):
            raise InvalidVideoIdError("video_id must be a non-empty string")

        self.logger.info(f"Fetching transcript for video ID: {video_id}")

        try:
            # Use the new fetch() method from API v1.2.2
            fetched_transcript = self.ytt_api.fetch(video_id)

            # Extract metadata from FetchedTranscript
            language = getattr(fetched_transcript, 'language', 'Unknown')
            language_code = getattr(fetched_transcript, 'language_code', 'N/A')
            is_generated = getattr(fetched_transcript, 'is_generated', False)

            # Convert FetchedTranscript to list of dictionaries
            transcript_list = fetched_transcript.to_raw_data()

            self.logger.info(
                f"Successfully fetched transcript with {len(transcript_list)} entries "
                f"(Language: {language}, Code: {language_code}, Generated: {is_generated})"
            )

            # Process transcript data
            transcript_data = self._process_transcript_data(
                transcript_list=transcript_list,
                video_id=video_id,
                title=title,
                language=language,
                language_code=language_code,
                is_generated=is_generated
            )

            # Upload to R2 (non-blocking - failure won't affect API response)
            r2_object_key = self._upload_to_r2(transcript_data, video_id)

            # Add R2 metadata to response
            if r2_object_key:
                transcript_data['metadata']['r2_object_key'] = r2_object_key
                # Construct R2 public URL if available
                if self.r2_config:
                    account_id = self.r2_config.get('R2_ACCOUNT_ID')
                    bucket_name = self.r2_config['R2_TRANSCRIPT_BUCKET_NAME']
                    if account_id:
                        transcript_data['r2_url'] = f"https://{bucket_name}.{account_id}.r2.cloudflarestorage.com/{r2_object_key}"

            return transcript_data

        except TranscriptsDisabled:
            error_msg = f"Transcripts are disabled for video {video_id}"
            self.logger.error(error_msg)
            raise TranscriptNotAvailableError(error_msg)

        except NoTranscriptFound:
            error_msg = f"No transcript found for video {video_id}"
            self.logger.error(error_msg)
            raise TranscriptNotAvailableError(error_msg)

        except VideoUnavailable:
            error_msg = f"Video {video_id} is unavailable"
            self.logger.error(error_msg)
            raise TranscriptNotAvailableError(error_msg)

        except Exception as e:
            error_msg = f"Unexpected error fetching transcript: {e}"
            self.logger.error(error_msg)
            raise TranscriptServiceError(error_msg)

    def _process_transcript_data(
        self,
        transcript_list: List[Dict[str, Any]],
        video_id: str,
        title: Optional[str],
        language: str,
        language_code: str,
        is_generated: bool
    ) -> Dict[str, Any]:
        """
        Process transcript data into API response format.

        Args:
            transcript_list: Raw transcript data from API
            video_id: YouTube video ID
            title: Video title
            language: Transcript language
            language_code: Language code
            is_generated: Whether transcript is auto-generated

        Returns:
            Dictionary matching VideoTranscriptResponse schema
        """
        if not title:
            title = f"Video-{video_id}"

        # Calculate full transcript text
        full_text = " ".join(
            segment.get("text", "").strip()
            for segment in transcript_list
            if segment.get("text", "").strip()
        )

        # Calculate total duration
        total_duration = None
        total_duration_formatted = None
        if transcript_list:
            last_segment = transcript_list[-1]
            total_duration = last_segment.get('start', 0) + last_segment.get('duration', 0)
            total_duration_formatted = self._format_duration(total_duration)

        # Build metadata
        metadata = {
            'total_segments': len(transcript_list),
            'fetch_timestamp': datetime.now().isoformat(),
            'api_version': '1.2.2',
            'language': language,
            'language_code': language_code,
            'is_generated': is_generated,
            'character_count': len(full_text),
            'word_count': len(full_text.split()) if full_text else 0,
            'total_duration_seconds': round(total_duration, 2) if total_duration else None,
            'total_duration_formatted': total_duration_formatted
        }

        # Build response
        return {
            'video_id': video_id,
            'title': title,
            'video_url': f"https://www.youtube.com/watch?v={video_id}",
            'transcript': transcript_list,
            'full_transcript': full_text,
            'metadata': metadata
        }

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to HH:MM:SS or MM:SS format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
